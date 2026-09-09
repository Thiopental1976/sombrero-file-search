#!/usr/bin/env python3
"""Vivo primeiro, snapshots só se faltar + dedup de resultados (09/09/2026).

Decisão do Rodrigo: "não incluir snapshots é bom para a performance mas não é
bom para o projeto — o SFS é um buscador de arquivos. Se o alvo do usuário
estiver nas pastas de snapshot ele vai receber nada. O dedup é parte integrante
da funcionalidade e deve se comportar da mesma maneira em diferentes
distribuições."

O que precisa valer, e vale aqui em árvore sintética (tempdir), nos backends
nativo (fd/rg) e Python, e no booleano:
  - vivo com achado -> a árvore podada NÃO é varrida (funil: snapshots_skipped)
  - vivo zero       -> a MESMA consulta é estendida às podadas; o achado vem
                       com `snapshot` = árvore de origem (funil: snapshots_searched)
  - --snapshots     -> estende sem esperar zero ("requested")
  - "zero" é por raiz DIGITADA: se um disco achou e outro não, estende só o
    que deu zero
  - dedup por identidade (st_dev, st_ino): hardlink vira 1 resultado +1 cópia
  - dedup por cópia idêntica (caminho vivo + tamanho + mtime) entre vivo e
    snapshot, com precedência do vivo; só-snapshot aparece com o caminho do
    snapshot; versão diferente NÃO colapsa
  - teto (max_results) e cancelamento na rodada viva: não estende
  - ostree/deploy e Timeshift passam pelo MESMO caminho; ostree/repo nunca
  - Mint sem snapshot: nada muda
  - --json: campos `snapshot` e `copies`, e evento `copy` para cópia absorvida
    depois de o dono ter sido impresso
"""
import json, os, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, boolean as B

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

def motivos(st):
    return [e["motivo"] for e in (st.get("incompleto") or [])]

def escreve(p, corpo="laudo\n", mtime=None):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(corpo)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p

def busca(q, **kw):
    out, st, evs = [], {}, []
    n, _ = E.search(q, out.append, stats=st, on_event=lambda e, i: evs.append((e, i)), **kw)
    return n, out, st, evs

def busca_bool(q, expr):
    out, st, evs = [], {}, []
    n, _ = B.search_boolean(q, expr, out.append, stats=st,
                            on_event=lambda e, i: evs.append((e, i)))
    return n, out, st, evs

def com_backend(nome, fn):
    fd, rg = E.FD, E.RG
    if nome == "python":
        E.FD, E.RG = None, None
    try:
        return fn()
    finally:
        E.FD, E.RG = fd, rg


# ---------------------------------------------------------------- tabela _caminho_vivo
T = E._caminho_vivo
casos = [
    ("/m/timeshift/snapshots/2026-09-08_17-00-01/localhost/etc/os-release",
     "/m/timeshift/snapshots", "timeshift/snapshots*", "/etc/os-release"),
    ("/m/timeshift/snapshots/2026-09-08/usr/x", "/m/timeshift/snapshots", "timeshift/snapshots*", None),
    ("/timeshift-btrfs/snapshots/2026-09-08/@/etc/fstab", "/timeshift-btrfs", "timeshift-btrfs", "/etc/fstab"),
    ("/timeshift-btrfs/snapshots/2026-09-08/@home/rodrigo/a.txt", "/timeshift-btrfs", "timeshift-btrfs",
     "/home/rodrigo/a.txt"),
    ("/.snapshots/5/snapshot/etc/fstab", "/.snapshots", ".snapshots", "/etc/fstab"),
    ("/home/.snapshots/5/snapshot/rodrigo/a.txt", "/home/.snapshots", ".snapshots", "/home/rodrigo/a.txt"),
    ("/tank/.zfs/snapshot/daily-1/docs/a.txt", "/tank/.zfs/snapshot", ".zfs/snapshot", "/tank/docs/a.txt"),
    ("/srv/share/@GMT-2026.09.08-00.00.00/docs/a.txt", "/srv/share/@GMT-2026.09.08-00.00.00", "@GMT-*",
     "/srv/share/docs/a.txt"),
    ("/sysroot/ostree/deploy/default/deploy/abc.1/usr/lib/os-release", "/sysroot/ostree/deploy",
     "ostree/deploy", "/usr/lib/os-release"),
    ("/sysroot/ostree/deploy/default/var/x", "/sysroot/ostree/deploy", "ostree/deploy", None),
    ("/outro/lugar", "/sysroot/ostree/deploy", "ostree/deploy", None),
]
for path, arv, pat, esp in casos:
    r = T(path, arv, pat)
    ok(r == esp, f"_caminho_vivo[{pat}] {path} -> {r!r} (esperado {esp!r})")


# ---------------------------------------------------------------- fixture Timeshift
def arvore_timeshift():
    raiz = tempfile.mkdtemp(prefix="sfs-fb-")
    escreve(os.path.join(raiz, "docs", "vivo.txt"), "laudo vivo\n")
    snap = os.path.join(raiz, "timeshift", "snapshots", "2026-09-08_17-00-01", "localhost")
    escreve(os.path.join(snap, "docs", "vivo.txt"), "laudo vivo\n")             # cópia
    escreve(os.path.join(snap, "docs", "apagado.txt"), "laudo apagado unico\n")  # só no snapshot
    return raiz, snap

raiz, snap = arvore_timeshift()
try:
    for backend in ("nativo", "python"):
        for modo, extra in (("nome", {}), ("conteudo", {"content": "laudo"})):
            tag = f"[{modo}/{backend}]"
            # 1) vivo com achado: snapshot NÃO varrido
            q = E.Query(paths=[raiz], name_patterns=["vivo.txt"], **extra)
            n, out, st, evs = com_backend(backend, lambda: busca(q))
            ok(n == 1 and out[0].path == os.path.join(raiz, "docs", "vivo.txt") and out[0].snapshot is None,
               f"{tag} vivo com achado: 1 resultado, vivo, sem origem de snapshot")
            ok(motivos(st) == ["snapshots_skipped"] and not any(e == "snapshots_searched" for e, _ in evs),
               f"{tag} vivo com achado: funil 'snapshots_skipped', nada estendido — {motivos(st)}")
            # 2) vivo zero: estendido, achado marcado com a origem
            q = E.Query(paths=[raiz], name_patterns=["apagado.txt"], **extra)
            n, out, st, evs = com_backend(backend, lambda: busca(q))
            ok(n == 1 and out[0].path == os.path.join(snap, "docs", "apagado.txt")
               and out[0].snapshot == os.path.join(raiz, "timeshift", "snapshots"),
               f"{tag} vivo zero: achado no snapshot, snapshot={out[0].snapshot if out else None}")
            ok(motivos(st) == ["snapshots_searched"],
               f"{tag} vivo zero: funil 'snapshots_searched' (não-grave) — {motivos(st)}")
            ev = [i for e, i in evs if e == "snapshots_searched"]
            ok(ev and ev[0]["path"] == raiz and ev[0]["trees"] == [os.path.join(raiz, "timeshift", "snapshots")]
               and ev[0]["ostree"] is False, f"{tag} painel: evento com a árvore estendida")
            ok(any(e == "root_done" and i["path"] == raiz and i["found"] == 1 for e, i in evs),
               f"{tag} narrativa: root_done do dono conta o achado da extensão")
            grave, linhas = E.resumo_incompleto(st)
            ok(not grave and linhas[0].startswith(f"snapshots searched in {raiz}: nothing in the live tree"),
               f"{tag} nota legível: {linhas[0][:60]}…")
            # 3) --snapshots: estende sem esperar zero; a cópia do vivo NÃO
            #    colapsa aqui (o layout do Timeshift mapeia para "/", não para
            #    o tempdir) — o que se prova é a extensão + a marcação
            q = E.Query(paths=[raiz], name_patterns=["vivo.txt"], skip_snapshots=False, **extra)
            n, out, st, evs = com_backend(backend, lambda: busca(q))
            ok(n == 2 and out[0].snapshot is None and out[1].snapshot == os.path.join(raiz, "timeshift", "snapshots"),
               f"{tag} --snapshots: vivo primeiro, depois o do snapshot marcado (n={n})")
            ok(motivos(st) == ["snapshots_searched"]
               and st["incompleto"][0]["detalhe"] == E._TEXTO_PODA[("snapshot", "requested")],
               f"{tag} --snapshots: nota 'requested'")

    # 4) booleano: mesma extensão
    n, out, st, evs = busca_bool(E.Query(paths=[raiz]), "apagado AND unico")
    ok(n == 1 and out[0].snapshot == os.path.join(raiz, "timeshift", "snapshots")
       and motivos(st) == ["snapshots_searched"],
       f"[booleano] vivo zero: estendido, achado marcado, funil searched (n={n}, {motivos(st)})")
    n, out, st, evs = busca_bool(E.Query(paths=[raiz]), "laudo AND vivo")
    ok(n == 1 and out[0].snapshot is None and motivos(st) == ["snapshots_skipped"],
       "[booleano] vivo com achado: snapshot não varrido")
    n, out, st, evs = com_backend("python", lambda: busca_bool(E.Query(paths=[raiz]), "apagado"))
    ok(n == 1 and out[0].snapshot is not None and motivos(st) == ["snapshots_searched"],
       "[booleano/py] vivo zero: estendido pelo fallback Python também")

    # 5) teto na rodada viva: não estende (o teto já foi anunciado)
    for i in range(6):
        escreve(os.path.join(raiz, "docs", f"m{i}.txt"))
    n, out, st, evs = busca(E.Query(paths=[raiz], name_patterns=["*.txt"], max_results=3))
    ok(n == 3 and "truncated" in motivos(st) and "snapshots_searched" not in motivos(st)
       and all(m.snapshot is None for m in out)
       and any(e["detalhe"] == E._TEXTO_PODA[("snapshot", "stopped")] for e in st["incompleto"]),
       "teto atingido no vivo: truncated, sem extensão, nota 'stopped'")

    # 6) cancelamento ao fim da rodada viva: não estende, e a nota diz que
    #    parou (não "teve resultado vivo")
    cancelado = [False]
    def viu(ev, info):
        if ev == "root_done":
            cancelado[0] = True
    out, st = [], {}
    E.search(E.Query(paths=[raiz], name_patterns=["apagado.txt"]), out.append,
             cancel=lambda: cancelado[0], stats=st, on_event=viu)
    ok(out == [] and motivos(st) == ["snapshots_skipped"]
       and st["incompleto"][0]["detalhe"] == E._TEXTO_PODA[("snapshot", "stopped")],
       f"cancelado: nada estendido, nota 'stopped' — {motivos(st)}")
finally:
    shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------- dedup
raiz = tempfile.mkdtemp(prefix="sfs-dd-")
try:
    a = escreve(os.path.join(raiz, "docs", "a.txt"), "laudo\n")
    b = os.path.join(raiz, "docs", "b.txt"); os.link(a, b)               # hardlink vivo
    # 7) identidade: hardlink -> 1 resultado, +1 cópia; nada de snapshot aqui
    n, out, st, evs = busca(E.Query(paths=[raiz], name_patterns=["*.txt"]))
    ok(n == 1 and sorted([out[0].path] + out[0].copies) == [a, b],
       f"hardlink vivo: 1 resultado, +1 cópia ({out[0].copies if out else None})")
    ok([e for e, _ in evs if e == "copy"] == ["copy"], "cópia absorvida vira evento 'copy'")
    ok(motivos(st) == [], "Mint sem snapshot: funil vazio, nada de snapshot no caminho")
    # symlink para um resultado é OUTRO objeto (Bazzite: /etc/os-release ->
    # /usr/lib/os-release ficava colapsado): dois resultados, sem cópia
    os.symlink(a, os.path.join(raiz, "docs", "link_a.txt"))
    n, out, st, evs = busca(E.Query(paths=[raiz], name_patterns=["*a.txt"]))
    ok(n == 2 and all(m.copies == [] for m in out), f"symlink do resultado não é cópia dele (n={n})")
    os.unlink(os.path.join(raiz, "docs", "link_a.txt"))
    # mesma raiz duas vezes ("/" e "/home"): o mesmo caminho não é cópia
    n, out, st, evs = busca(E.Query(paths=[raiz, os.path.join(raiz, "docs")], name_patterns=["a.txt"]))
    ok(n == 1 and out[0].copies == [], "raiz repetida: o mesmo caminho colapsa SEM virar cópia")

    # 8) cópia idêntica (snapper: .snapshots/<n>/snapshot/<rel> -> <raiz>/<rel>)
    os.unlink(b)
    t0 = time.time() - 1000
    os.utime(a, (t0, t0))
    s1 = os.path.join(raiz, ".snapshots", "1", "snapshot")
    s2 = os.path.join(raiz, ".snapshots", "2", "snapshot")
    shutil.copy2(a, escreve(os.path.join(s1, "docs", "a.txt")))            # cópia idêntica
    shutil.copy2(a, escreve(os.path.join(s2, "docs", "a.txt")))            # de novo
    escreve(os.path.join(s1, "docs", "sumiu.txt"), "laudo sumiu\n", t0)    # só no snapshot
    escreve(os.path.join(s2, "docs", "sumiu.txt"), "laudo sumiu\n", t0)    # idem, 2x
    escreve(os.path.join(s1, "docs", "versao.txt"), "v1\n", t0)            # versão antiga
    escreve(os.path.join(raiz, "docs", "versao.txt"), "v2 maior\n", t0 + 60)
    q = E.Query(paths=[raiz], name_patterns=["*.txt"], skip_snapshots=False, include_hidden=True)
    n, out, st, evs = busca(q)
    por = {m.path: m for m in out}
    ok(a in por and por[a].snapshot is None and sorted(por[a].copies) ==
       sorted([os.path.join(s1, "docs", "a.txt"), os.path.join(s2, "docs", "a.txt")]),
       f"cópia idêntica vivo×snapshot: caminho VIVO com +2 cópias ({por.get(a) and por[a].copies})")
    sumiu = [m for m in out if os.path.basename(m.path) == "sumiu.txt"]
    ok(len(sumiu) == 1 and sumiu[0].snapshot == os.path.join(raiz, ".snapshots")
       and sumiu[0].path.startswith(s1) and sumiu[0].copies == [os.path.join(s2, "docs", "sumiu.txt")],
       f"só-snapshot: aparece UMA vez com caminho do snapshot, origem marcada, +1 cópia")
    versoes = sorted(m.path for m in out if os.path.basename(m.path) == "versao.txt")
    ok(versoes == [os.path.join(s1, "docs", "versao.txt"), os.path.join(raiz, "docs", "versao.txt")],
       "versão diferente (tamanho/mtime) NÃO colapsa: dois resultados")
    ok(n == 4, f"total: a.txt, sumiu.txt, versao.txt×2 = 4 (deu {n})")
    # GUI/CSV/JSON compartilham a contagem: export do searches
    from lfs import searches
    import io
    buf = io.StringIO(); searches.export_json(out, buf)
    dj = json.loads(buf.getvalue())
    ok(any(d["path"] == a and len(d["copies"]) == 2 and d["snapshot"] is None for d in dj)
       and any(d["snapshot"] == os.path.join(raiz, ".snapshots") for d in dj),
       "export JSON da GUI carrega snapshot e copies")

    # 9) "zero" por raiz DIGITADA: dois locais, um achou, outro não
    outra = tempfile.mkdtemp(prefix="sfs-dd2-")
    try:
        escreve(os.path.join(outra, "timeshift", "snapshots", "2026-09-08", "localhost", "x", "a.txt"))
        escreve(os.path.join(raiz, "timeshift", "snapshots", "2026-09-08", "localhost", "x", "a.txt"))
        n, out, st, evs = busca(E.Query(paths=[raiz, outra], name_patterns=["a.txt"]))
        onde = {e["motivo"]: e["onde"] for e in st["incompleto"]}
        ok(onde == {"snapshots_skipped": raiz, "snapshots_searched": outra},
           f"raiz que achou fica podada; a que deu zero é estendida — {onde}")
        ok(n == 2 and any(m.path.startswith(outra) and m.snapshot for m in out)
           and not any(m.path.startswith(os.path.join(raiz, "timeshift")) for m in out),
           "só o snapshot da raiz em zero entrou nos resultados")
    finally:
        shutil.rmtree(outra, ignore_errors=True)
finally:
    shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------- ostree: mesmo caminho
raiz = tempfile.mkdtemp(prefix="sfs-ot-")
try:
    dep = os.path.join(raiz, "sysroot", "ostree", "deploy", "default", "deploy")
    escreve(os.path.join(dep, "abc.1", "usr", "lib", "antigo.conf"), "laudo antigo\n")
    escreve(os.path.join(raiz, "sysroot", "ostree", "repo", "objects", "ab", "antigo.conf"), "laudo antigo\n")
    escreve(os.path.join(raiz, "usr", "lib", "vivo.conf"), "laudo vivo\n")
    os.symlink("sysroot/ostree", os.path.join(raiz, "ostree"))
    n, out, st, evs = busca(E.Query(paths=[raiz], name_patterns=["antigo.conf"]))
    ok(n == 1 and out[0].path == os.path.join(dep, "abc.1", "usr", "lib", "antigo.conf")
       and out[0].snapshot == os.path.join(raiz, "sysroot", "ostree", "deploy"),
       f"ostree: só na implantação antiga -> achado no fallback, origem = ostree/deploy (n={n})")
    ok(motivos(st) == ["snapshots_searched"]
       and st["incompleto"][0]["detalhe"] == E._TEXTO_PODA[("ostree", "searched")],
       "ostree: MESMO motivo do Timeshift, texto do ostree")
    ok(not any("/repo/" in m.path for m in out), "ostree/repo nunca é estendido")
    ev = [i for e, i in evs if e == "snapshots_searched"]
    ok(ev and ev[0]["ostree"] is True and ev[0]["trees"] == [os.path.join(raiz, "sysroot", "ostree", "deploy")],
       "painel: evento comum com marca ostree, só o deploy nas árvores")
    n, out, st, evs = busca(E.Query(paths=[raiz], name_patterns=["vivo.conf"]))
    ok(n == 1 and motivos(st) == ["snapshots_skipped"]
       and st["incompleto"][0]["detalhe"] == E._TEXTO_PODA[("ostree", "skipped")],
       "ostree: vivo com achado -> implantações puladas, texto honesto")
finally:
    shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------- CLI --json
raiz = tempfile.mkdtemp(prefix="sfs-cli-")
try:
    a = escreve(os.path.join(raiz, "a.txt")); os.link(a, os.path.join(raiz, "b.txt"))
    escreve(os.path.join(raiz, "timeshift", "snapshots", "2026-09-08", "localhost", "etc", "so.txt"))
    cli = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lfs", "cli.py")
    r = subprocess.run([sys.executable, cli, raiz, "-n", "*.txt", "--json"],
                       capture_output=True, text=True)
    linhas = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    matches = [l for l in linhas if "path" in l and "copy" not in l]
    copias = [l for l in linhas if "copy" in l]
    ok(len(matches) == 1 and matches[0]["snapshot"] is None and "copies" in matches[0],
       f"--json: 1 objeto com campos snapshot/copies ({matches})")
    ok(len(copias) == 1 and copias[0]["of"] == matches[0]["path"] and copias[0]["snapshot"] is None,
       f"--json: a cópia absorvida depois sai como evento copy/of ({copias})")
    ok(any(l.get("reason") == "snapshots_skipped" for l in linhas), "--json: warn snapshots_skipped")
    r = subprocess.run([sys.executable, cli, raiz, "-n", "so.txt", "--json"],
                       capture_output=True, text=True)
    linhas = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    m = [l for l in linhas if "path" in l and "copy" not in l]
    ok(r.returncode == 0 and len(m) == 1 and m[0]["snapshot"] == os.path.join(raiz, "timeshift", "snapshots")
       and any(l.get("reason") == "snapshots_searched" and l.get("warn") for l in linhas),
       f"--json: achado só no snapshot sai marcado, warn snapshots_searched, exit 0 (rc={r.returncode})")
finally:
    shutil.rmtree(raiz, ignore_errors=True)

print(f"\n{'FALHOU: ' + '; '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
