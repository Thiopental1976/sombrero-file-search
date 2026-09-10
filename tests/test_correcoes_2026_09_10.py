#!/usr/bin/env python3
"""Correções de 10/09/2026 — três achados reais, e a prova de dois que NÃO eram.

Origem: revisão do Grok 4.6 sobre o diff do Fable (~/Downloads/REVISAO_diff_Fable_2026-09-09.md)
e um /code-review low local. Cada célula abaixo existe porque alguém afirmou um
defeito; as que dizem "REFUTADO" travam o comportamento CORRETO para que a
próxima revisão não o "conserte".

REAIS, corrigidos aqui:
  A) nota de poda MENTIA quando nada sob o dono é extensível (só ostree/repo):
     dizia "este local teve resultado vivo (--snapshots para varrer sempre)"
     mesmo com ZERO achados, e oferecia uma flag que não faria nada ali.
  B) a rodada de EXTENSÃO do booleano ficava MUDA: a _Phase era uma por busca e
     `term()` só conta cada termo uma vez, então a segunda rodada (que por
     conteúdo em disco de backup leva minutos) não emitia progresso nenhum.
  C) o preview `list_search_targets` prometia N montagens contando bind mount
     duas vezes, enquanto `planejar_raizes` já as unia por (st_dev, st_ino).

REFUTADOS por fato, travados aqui:
  D) "o dedup do Timeshift ancora em / e por isso o mesmo arquivo sai 2×."
     O snapshot do Timeshift rsync É uma cópia da RAIZ DO SISTEMA — conferido no
     acervo real (/mnt/SSD128Gb/timeshift/snapshots/<data>/localhost/{bin,boot,
     etc,usr,var,...}). Ancorar na raiz digitada faria o arquivo do snapshot
     colapsar com um arquivo HOMÔNIMO do disco de backup (falso colapso, esconde
     arquivo distinto) e deixaria de colapsar com o arquivo vivo de verdade.
     Aqui a prova é de ponta a ponta, contra o /etc/os-release DO HOST.
  E) "no ostree um arquivo do /boot sai 2× (bind de /sysroot/boot)."
     Sai UMA vez: o dedup por identidade (st_dev, st_ino) do _Colapso pega
     qualquer bind/hardlink, e o segundo caminho vira "+1 cópia".
"""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, boolean as B, disks as D

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond:
        falhas.append(nome)

def escreve(p, corpo="laudo\n"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(corpo)
    return p

def busca(q, **kw):
    out, st, evs = [], {}, []
    n, _ = E.search(q, out.append, stats=st, on_event=lambda e, i: evs.append((e, i)), **kw)
    return n, out, st, evs

def funil(st):
    return {e["motivo"]: e for e in (st.get("incompleto") or [])}


# ---------------------------------------------------------------- A) nota que mentia
def test_nota_sem_arvore_extensivel_nao_finge_resultado_vivo():
    """Dono cujo único podado é ostree/repo (EXCLUSOES_SEM_FALLBACK) e ZERO
    achados vivos: a nota não pode dizer que houve resultado vivo, nem oferecer
    --snapshots — o repo nunca é varrido."""
    raiz = tempfile.mkdtemp(prefix="sfs_norepo_")
    try:
        escreve(os.path.join(raiz, "ostree", "repo", "objects", "ab", "cdef.file"), "laudo\n")
        escreve(os.path.join(raiz, "docs", "outro.txt"), "nada\n")
        n, out, st, _ = busca(E.Query(paths=[raiz], name_patterns=["cdef.file"]))
        f = funil(st)
        e = f.get("snapshots_skipped")
        det = (e or {}).get("detalhe", "")
        ok(n == 0, f"repo-only: nada encontrado no vivo (n={n})")
        ok(e is not None, "repo-only: a poda continua sendo DITA (snapshots_skipped)")
        ok("had live results" not in det,
           f"repo-only: a nota NÃO afirma resultado vivo ({det[:60]!r})")
        ok("--snapshots" not in det,
           "repo-only: a nota não oferece --snapshots para árvore que nunca é varrida")
        ok("never" in det or "hash" in det,
           f"repo-only: a nota diz o fato (nunca varrido / nome de hash) ({det[:60]!r})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def test_nota_com_arvore_extensivel_continua_dizendo_o_de_sempre():
    """Catraca do outro lado: com uma árvore extensível e achado vivo, o texto
    de 'skipped' (que fala de resultado vivo e oferece a flag) NÃO mudou."""
    raiz = tempfile.mkdtemp(prefix="sfs_skip_")
    try:
        escreve(os.path.join(raiz, "docs", "vivo.txt"), "laudo\n")
        escreve(os.path.join(raiz, "timeshift", "snapshots", "2026-09-09_17-00-01",
                             "localhost", "docs", "vivo.txt"), "laudo\n")
        n, out, st, _ = busca(E.Query(paths=[raiz], name_patterns=["vivo.txt"]))
        det = funil(st).get("snapshots_skipped", {}).get("detalhe", "")
        ok(n == 1, f"vivo achou: 1 resultado (n={n})")
        ok("had live results" in det and "--snapshots" in det,
           f"árvore extensível: texto de sempre preservado ({det[:60]!r})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------- B) fase da extensão
def test_extensao_booleana_reporta_progresso():
    """A rodada de extensão às podadas emite progresso próprio. Antes: _Phase
    única por busca + dedup por termo em `term()` = segunda rodada sem 1 evento."""
    raiz = tempfile.mkdtemp(prefix="sfs_fase_")
    try:
        escreve(os.path.join(raiz, "timeshift", "snapshots", "2026-09-09_17-00-01",
                             "localhost", "docs", "apagado.txt"), "laudo unico\n")
        fases, evs = [], []
        out, st = [], {}
        n, _ = B.search_boolean(E.Query(paths=[raiz]), "laudo AND unico", out.append,
                                stats=st, on_phase=lambda d, tot, lab: fases.append((d, tot, lab)),
                                on_event=lambda e, i: evs.append((e, i)))
        motivos = [e for e, _i in evs]
        primeiros = [d for d, _t, _l in fases if d == 1]
        ok(n == 1, f"extensão booleana achou o arquivo só-snapshot (n={n})")
        ok("snapshots_searched" in motivos, "extensão booleana: a nota saiu")
        ok(len(primeiros) >= 2,
           f"a extensão reporta progresso próprio (passos '1/N' vistos: {len(primeiros)})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def test_fase_nao_estoura_o_total_com_varios_grupos():
    """Catraca: a numeração continua sem passar do total (o dedup por termo do
    `_Phase` é o que garante isso quando há um grupo de disco por thread)."""
    raiz = tempfile.mkdtemp(prefix="sfs_fase2_")
    try:
        escreve(os.path.join(raiz, "a", "x.txt"), "laudo paciente\n")
        escreve(os.path.join(raiz, "b", "y.txt"), "laudo paciente\n")
        fases = []
        out, st = [], {}
        B.search_boolean(E.Query(paths=[os.path.join(raiz, "a"), os.path.join(raiz, "b")]),
                         "laudo AND paciente", out.append, stats=st,
                         on_phase=lambda d, tot, lab: fases.append((d, tot, lab)))
        ok(fases and all(d <= tot for d, tot, _l in fases),
           f"nenhum passo passa do total ({[(d, t) for d, t, _ in fases][:6]})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------- C) preview x bind
def _perfil_local(mp):
    return D.IOProfile(klass="ssd", mountpoint=mp, fstype="ext4", serialize=False,
                       is_network=False, max_workers=None, enumerate_default=True)

def test_preview_nao_conta_bind_duas_vezes():
    """`list_search_targets` (preview 'vai tocar N montagens') tem de usar a
    MESMA identidade de `planejar_raizes`: duas montagens que são o mesmo
    diretório contam uma. Simulado com symlink — `os.stat` devolve o mesmo
    (st_dev, st_ino), que é exatamente o que um bind mount faz."""
    raiz = tempfile.mkdtemp(prefix="sfs_prev_")
    try:
        var = os.path.join(raiz, "var"); os.makedirs(var)
        deploy = os.path.join(raiz, "deploy_var"); os.symlink(var, deploy)
        outra = os.path.join(raiz, "home"); os.makedirs(outra)
        mounts = [("/dev/vda3", raiz, "ext4"), ("/dev/vda3", var, "ext4"),
                  ("/dev/vda3", deploy, "ext4"), ("/dev/vda3", outra, "ext4")]
        alvos = D.list_search_targets([raiz], mounts=mounts,
                                      _profile=lambda p, m=None: _perfil_local(p),
                                      _alive=lambda p, timeout=None: True)
        caminhos = [a["path"] for a in alvos]
        ok(deploy not in caminhos,
           f"bind (mesmo diretório) não aparece 2x no preview: {caminhos}")
        ok(var in caminhos, "o vencedor é o caminho mais curto (/var, não o de dentro do deploy)")
        ok(outra in caminhos, "montagem que é outro diretório continua listada")
        ok(len(alvos) == 3, f"3 alvos: raiz + var + home (veio {len(alvos)}: {caminhos})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def test_diferenca_conhecida_preview_lista_montagem_do_mesmo_fs():
    """LACUNA DECLARADA (não é o que se corrigiu em 10/09). `planejar_raizes`
    tem DUAS regras: (1) montagem que é o mesmo DIRETÓRIO de outra raiz — o bind
    do ostree — entra uma vez, e é essa que o preview passou a respeitar; e
    (2) montagem cujo st_dev é igual ao da raiz-mãe não vira raiz própria, porque
    o walker da mãe já a varre. O preview NÃO aplica a (2): ele mostra a
    fronteira (o NAS, o pendrive), e uma montagem do mesmo sistema de arquivos
    continua listada. Efeito: o número do preview pode ser MAIOR que o de raízes
    efetivas. Fica pinado aqui para que mudar isso seja decisão, não acidente."""
    raiz = tempfile.mkdtemp(prefix="sfs_prev2_")
    try:
        var = os.path.join(raiz, "var"); os.makedirs(var)
        mounts = [("/dev/vda3", raiz, "ext4"), ("/dev/vda3", var, "ext4")]
        alvos = D.list_search_targets([raiz], mounts=mounts,
                                      _profile=lambda p, m=None: _perfil_local(p),
                                      _alive=lambda p, timeout=None: True)
        roots, _expandidas, _forca = E.planejar_raizes([raiz], False, {}, mounts=mounts)
        ok([a["path"] for a in alvos] == [raiz, var],
           f"preview mostra a fronteira do mesmo FS ({[a['path'] for a in alvos]})")
        ok(roots == [raiz],
           f"o motor funde a montagem do mesmo FS na raiz-mãe (roots={roots})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------- D) âncora do Timeshift (REFUTADO)
def test_timeshift_ancora_na_raiz_do_sistema_de_ponta_a_ponta():
    """PROVA CONTRA O FERRO: um snapshot do Timeshift é cópia da RAIZ DO SISTEMA.
    O /etc/os-release do host e a cópia dele dentro de
    <disco>/timeshift/snapshots/<data>/localhost/etc/os-release são o MESMO
    arquivo, e o dedup por cópia idêntica (caminho vivo reconstruído + tamanho +
    mtime) tem de colapsar os dois com o VIVO na frente.

    Se alguém "consertar" a âncora para a raiz digitada, este teste cai: o
    caminho reconstruído viraria <tmp>/etc/os-release e não casaria com nada."""
    if not os.path.isfile("/etc/os-release"):
        print("skip  /etc/os-release não existe nesta máquina")
        return
    raiz = tempfile.mkdtemp(prefix="sfs_ts_")
    try:
        alvo = os.path.join(raiz, "timeshift", "snapshots", "2026-09-09_17-00-01",
                            "localhost", "etc", "os-release")
        os.makedirs(os.path.dirname(alvo))
        shutil.copy2("/etc/os-release", alvo)      # copy2 preserva tamanho e mtime
        q = E.Query(paths=["/etc", raiz], name_patterns=["os-release"],
                    skip_snapshots=False)          # --snapshots: estende sem esperar zero
        n, out, st, _ = busca(q)
        vivos = [m for m in out if m.path == "/etc/os-release"]
        ok(n == 1, f"1 resultado só: o vivo absorveu a cópia do snapshot (n={n}, "
                   f"paths={[m.path for m in out]})")
        ok(bool(vivos), "o resultado que fica é o caminho VIVO (/etc/os-release)")
        ok(bool(vivos) and alvo in vivos[0].copies,
           f"a cópia do snapshot entrou em copies ({vivos[0].copies if vivos else None})")
        ok(bool(vivos) and vivos[0].snapshot is None,
           "o dono não é marcado como snapshot (quem manda é o vivo)")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def test_homonimo_no_disco_de_backup_nao_colapsa():
    """O outro lado da mesma moeda: um arquivo do disco de backup com o mesmo
    nome relativo NÃO é cópia do arquivo do snapshot (o snapshot é cópia de /).
    Ancorar na raiz digitada colapsaria estes dois e ESCONDERIA um arquivo."""
    raiz = tempfile.mkdtemp(prefix="sfs_hom_")
    try:
        vivo_disco = escreve(os.path.join(raiz, "etc", "hosts.txt"), "conteudo do disco\n")
        snap = escreve(os.path.join(raiz, "timeshift", "snapshots", "2026-09-09_17-00-01",
                                    "localhost", "etc", "hosts.txt"), "conteudo do disco\n")
        os.utime(snap, (os.stat(vivo_disco).st_mtime, os.stat(vivo_disco).st_mtime))
        q = E.Query(paths=[raiz], name_patterns=["hosts.txt"], skip_snapshots=False)
        n, out, st, _ = busca(q)
        paths = sorted(m.path for m in out)
        ok(n == 2 and paths == sorted([vivo_disco, snap]),
           f"homônimo do disco e arquivo do snapshot são DOIS resultados (n={n}, {paths})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------- E) bind do /boot (REFUTADO)
def test_bind_do_mesmo_arquivo_colapsa_por_identidade():
    """No ostree /boot é bind de /sysroot/boot: o mesmo arquivo alcançado por
    dois caminhos. Ele NÃO sai duas vezes — o dedup por identidade (st_dev,
    st_ino) o colapsa e o segundo caminho vira '+1 cópia'. Hardlink reproduz
    exatamente a mesma identidade."""
    raiz = tempfile.mkdtemp(prefix="sfs_boot_")
    try:
        a = escreve(os.path.join(raiz, "boot", "vmlinuz.cfg"), "laudo\n")
        os.makedirs(os.path.join(raiz, "sysroot", "boot"))
        b = os.path.join(raiz, "sysroot", "boot", "vmlinuz.cfg")
        os.link(a, b)
        n, out, st, _ = busca(E.Query(paths=[raiz], name_patterns=["vmlinuz.cfg"]))
        ok(n == 1, f"o arquivo alcançado por 2 caminhos sai 1x (n={n})")
        ok(out and len(out[0].copies) == 1,
           f"o segundo caminho vira +1 cópia ({out[0].copies if out else None})")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


TESTES = (test_nota_sem_arvore_extensivel_nao_finge_resultado_vivo,
          test_nota_com_arvore_extensivel_continua_dizendo_o_de_sempre,
          test_extensao_booleana_reporta_progresso,
          test_fase_nao_estoura_o_total_com_varios_grupos,
          test_preview_nao_conta_bind_duas_vezes,
          test_diferenca_conhecida_preview_lista_montagem_do_mesmo_fs,
          test_timeshift_ancora_na_raiz_do_sistema_de_ponta_a_ponta,
          test_homonimo_no_disco_de_backup_nao_colapsa,
          test_bind_do_mesmo_arquivo_colapsa_por_identidade)

for fn in TESTES:
    print(f"--- {fn.__name__}")
    try:
        fn()
    except Exception as e:
        print(f"ERRO  {fn.__name__}: {type(e).__name__}: {e}")
        falhas.append(f"{fn.__name__} ({type(e).__name__})")
print(f"\n{'FALHOU: ' + ', '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
