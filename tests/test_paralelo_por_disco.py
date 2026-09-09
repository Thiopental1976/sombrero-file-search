#!/usr/bin/env python3
"""F11 — paralelismo de I/O por disco: partição, streaming e encerramento.

Não toca em disco de verdade: exercita _grupos_por_disco com st_dev fingido e
_iter_particionado com uma fábrica sintética (um "disco" lento, outro rápido).
O que precisa valer:
  - roots do mesmo dispositivo ficam no MESMO processo (1 thread por montagem);
  - o resultado do disco rápido chega ANTES do disco lento terminar (era isso
    que o iterador serial impedia);
  - ao_fim(paths) só é chamado depois de entregues TODOS os achados do grupo;
  - saída antecipada (max_results/cancel) não deixa thread presa no put().
"""
import os, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)


# ---- 1) agrupamento por DISCO FISICO (nao st_dev: btrfs @/@home e LVM dariam
#         st_dev diferentes pro mesmo cabecote — ver _chave_de_disco)
def test_grupos():
    # dois subvolumes do MESMO disco fisico com st_dev diferentes
    mapa = {"/a": ("disco", "sda"), "/a2": ("disco", "sda"),
            "/b": ("disco", "sdb"), "/c": ("disco", "sdc")}
    real = E._chave_de_disco
    E._chave_de_disco = lambda p: mapa.get(p) or real(p)
    try:
        g = E._grupos_por_disco(["/a", "/b", "/a2", "/c"])
    finally:
        E._chave_de_disco = real
    ok(g == [["/a", "/a2"], ["/b"], ["/c"]],
       "1 grupo por DISCO (subvolumes do mesmo prato nao viram 2 processos)")

def test_grupos_discos_reais():
    reais = [d for d in ("/mnt/DiscoQ", "/mnt/DiscoL", "/media/rodrigo/4TB-Portable")
             if os.path.isdir(d)]
    if len(reais) < 2:
        print("~pula grupos_discos_reais (montagens ausentes)"); return
    ok(len(E._grupos_por_disco(reais)) == len(reais),
       "discos fisicos distintos viram grupos distintos")

def test_grupo_inacessivel():
    real = E._chave_de_disco
    E._chave_de_disco = lambda p: (_ for _ in ()).throw(OSError()) if p == "/sumiu" else real(p)
    try:
        g = E._grupos_por_disco(["/sumiu", "/tmp"])
    finally:
        E._chave_de_disco = real
    ok(len(g) == 2, "root sem stat vira grupo próprio (não some da busca)")


# ---- 1b) exclusao de snapshot: casa por COMPONENTE, com glob
def test_eh_snapshot():
    casos = [("/disco/timeshift/snapshots/2026-09-01/usr/x", True),
             ("/disco/timeshift/snapshots-daily/2026-09-01/usr/x", True),   # symlink farm
             ("/disco/x/@GMT-2026.01.01-00.00.00/etc/y", True),             # Samba
             ("/mnt/x/.snapshots/3/snapshot/etc", True),
             ("/disco/meus_timeshift_backups/a.mp4", False),                # falso positivo
             ("/mnt/DiscoQ/_Atrizes/Kevlyn/a.mp4", False)]
    bad = [p for p, esp in casos if E.eh_snapshot(p) != esp]
    ok(not bad, f"eh_snapshot casa por componente ({len(casos)} casos)" + (f" — errou {bad}" if bad else ""))


# ---- 1c) F11b: tamanho do pool por classe de disco
def test_jobs_por_classe():
    ok(E._jobs_para_classe(["ssd"]) is None,
       "SSD fica com o padrao do fd (estrangular custou 12,5x no NVMe, medido)")
    ok(E._jobs_para_classe(["rotational"]) == 1,
       "disco mecanico fica em 1 thread (ganhou 21% no SMR grande, medido)")
    ok(E._jobs_para_classe(["ssd", "rotational"]) == 1,
       "grupo misto leva a politica MAIS conservadora")
    ok(E._jobs_para_classe([]) is None, "grupo sem classe nao estrangula")
    # medido 09/09/2026: CONTEÚDO em disco mecânico quer fila funda (35 s vs 52+ s)
    ok(E._jobs_para_classe(["rotational"], conteudo=True) is None,
       "conteudo em rotacional NAO estrangula (medido: pool cheio 35 s, 1 thread 52-657 s)")
    ok(E._jobs_para_classe(["network", "rotational"], conteudo=True) == E._jobs_de_rede(),
       "conteudo: rede mantem o teto por montagem")
    ok(E._jobs_para_classe(["klass_que_nao_existe"]) is None,
       "classe desconhecida NAO estrangula: errar pra menos custa 12,5x, pra mais 21%")


def test_lvm_nao_vira_desconhecido():
    """/ no Mint e no Ubuntu e LVM, e o portatil e LUKS: /dev/mapper/* nao tem
    'rotational' proprio. Antes o disks devolvia None pros dois, e sob /mnt|/media
    isso virava "rotational" por padrao — um NVMe em gaveta USB com LUKS levava
    1 thread, 12,5x mais lento. O conserto e no disks._rotational (nao no motor)
    porque path_needs_serial e search_profile bebem da mesma fonte.

    Bazzite/composefs (09/09/2026): "/" e overlay sem no de bloco, mas com
    `datadir+=` — o disks herda o disco de /sysroot, entao AQUI NAO PULA: e
    testado de verdade (se a heranca quebrar, este teste fica vermelho no
    Bazzite). So pula onde "/" nao tem bloco NEM datadir (live-USB, container):
    ai nao ha LVM pra testar e o "unknown" e a resposta honesta."""
    try:
        from lfs import disks
    except Exception:
        print("~pula lvm (sem pacote disks)"); return
    if not os.path.isdir("/sys/block"):
        print("~pula lvm (sem /sys/block)"); return
    ent = disks._mount_entry("/")
    if (not ent[0].startswith("/dev/")
            and not disks._overlay_datadirs(getattr(ent, "opts", ""))):
        print(f"~pula lvm (/ sem no de bloco nem datadir: {ent[0]} {ent[2]})"); return
    k = disks.search_profile("/").klass
    ok(k in ("ssd", "rotational"), f"/ (LVM) e classificado de verdade (deu {k!r})")
    ok(disks._rotational("/dev/mapper/vgmint-root") in ("0", "1", None),
       "dm nao quebra o _rotational")
    ok(E._jobs_para_classe([k]) == E._JOBS_POR_CLASSE.get(k),
       "a classe resolvida escolhe o pool")


# /proc/mounts REAL da VM Bazzite (bootc, composefs), 09/09/2026, sem pseudo-fs.
# "/" nao tem no de bloco; o kernel declara datadir+=/sysroot/ostree/repo/objects.
_MOUNTS_BAZZITE = [
    "composefs / overlay ro,seclabel,relatime,lowerdir+=/run/ostree/.private/cfsroot-lower,"
    "datadir+=/sysroot/ostree/repo/objects,redirect_dir=on,metacopy=on 0 0\n",
    "/dev/vda3 /etc btrfs rw,seclabel,relatime,subvolid=5,subvol=/ 0 0\n",
    "/dev/vda3 /sysroot btrfs ro,seclabel,relatime,subvolid=5,subvol=/ 0 0\n",
    "/dev/vda3 /sysroot/ostree/deploy/default/var btrfs rw,seclabel,relatime,subvolid=5,subvol=/ 0 0\n",
    "/dev/vda3 /boot btrfs ro,seclabel,relatime,subvolid=5,subvol=/ 0 0\n",
    "/dev/vda3 /var btrfs rw,seclabel,relatime,subvolid=5,subvol=/ 0 0\n",
    "portal /run/user/968/doc fuse.portal rw,nosuid,nodev,relatime 0 0\n",
]


def test_composefs_herda_disco_do_datadir():
    """Bazzite/composefs (09/09/2026): "/" e overlay com `datadir+=`, e o SFS
    herda o disco desse caminho — le o fato que o kernel publica, nao inventa.
    Overlay COMUM (Docker/live-USB: lowerdir/upperdir, sem datadir) e datadir
    espalhado em dois discos continuam "unknown". Puro: tabela sintetica,
    _rotational/_sys_disk fingidos (o /dev/vda3 nao existe aqui)."""
    try:
        from lfs import disks
    except Exception:
        print("~pula composefs (sem pacote disks)"); return
    M = disks._read_mounts(_MOUNTS_BAZZITE)
    orig_rot, orig_sys, orig_me, orig_rm = (disks._rotational, disks._sys_disk,
                                            disks._mount_entry, disks._read_mounts)
    disks._rotational = lambda dev: {"/dev/vda3": "1"}.get(dev)
    disks._sys_disk = lambda dev: "vda" if dev == "/dev/vda3" else ""
    try:
        p = disks.search_profile("/", M)
        ok(p.klass == "rotational" and p.mountpoint == "/" and p.fstype == "overlay"
           and not p.serialize,
           f"/ composefs herda o disco do datadir+= (rotacional na VM) — deu {p}")
        ok(disks.search_profile("/usr/bin", M).klass == "rotational",
           "/usr (dentro do composefs) herda igual")
        ok(disks._dev_for_path("/", M) == "/dev/vda3",
           "_dev_for_path resolve composefs -> /dev/vda3 (path_needs_serial bebe daqui)")
        disks._rotational = lambda dev: {"/dev/vda3": "0"}.get(dev)
        ok(disks.search_profile("/", M).klass == "ssd",
           "no metal com SSD vira 'ssd': segue o fato, nao o nome da distro")
        G = disks._read_mounts([
            "overlay / overlay rw,lowerdir=/l1:/l2,upperdir=/u,workdir=/w 0 0\n",
            "/dev/sda1 /l1 ext4 rw 0 0\n"])
        ok(disks.search_profile("/", G).klass == "unknown",
           "overlay comum (Docker/live-USB, sem datadir) NAO herda: continua unknown")
        Dd = disks._read_mounts([
            "composefs / overlay ro,datadir+=/a/objs,datadir+=/b/objs,metacopy=on 0 0\n",
            "/dev/sda1 /a ext4 rw 0 0\n", "/dev/sdb1 /b ext4 rw 0 0\n"])
        ok(disks.search_profile("/", Dd).klass == "unknown",
           "datadir em dois discos: nao escolhe um, fica unknown")
        # agrupamento: "/" cai no grupo do /sysroot (1 processo no prato), nao em
        # grupo proprio por st_dev (37 x 35 na VM). _chave_de_disco nao recebe
        # tabela, entao a tabela do Bazzite entra pelos dois leitores.
        disks._mount_entry = lambda ap, mounts=None: orig_me(ap, M if mounts is None else mounts)
        disks._read_mounts = lambda src="/proc/mounts": M if src == "/proc/mounts" else orig_rm(src)
        g = E._grupos_por_disco(["/", "/etc", "/sysroot", "/var", "/boot"])
        ok(g == [["/", "/etc", "/sysroot", "/var", "/boot"]],
           f"composefs / vai pro grupo do /sysroot (1 processo, 1 prato) — deu {g}")
    finally:
        disks._rotational, disks._sys_disk = orig_rot, orig_sys
        disks._mount_entry, disks._read_mounts = orig_me, orig_rm


def test_bind_do_mesmo_diretorio_entra_uma_vez():
    """Bazzite/ostree (09/09/2026): /var e bind de /sysroot/ostree/deploy/default/var
    — MESMO diretorio, duas montagens. planejar_raizes so deduplicava bind contra
    a raiz-mae (st_dev de "/"), nao contra irmas: as duas viravam raiz, a de
    dentro de ostree/deploy ganhava grupo proprio com snapshots LIGADOS, e o /var
    era varrido 2x. Agora dedup por identidade do diretorio ((st_dev, st_ino) do
    ponto de montagem) — fato do kernel, nao nome de distro. Puro: tabela
    sintetica, stat fingido, disco fingido."""
    try:
        from lfs import disks
    except Exception:
        print("~pula bind (sem pacote disks)"); return
    M = disks._read_mounts(_MOUNTS_BAZZITE)
    DEPLOY_VAR = "/sysroot/ostree/deploy/default/var"
    # st_dev: "/" e overlay (37); tudo do vda3 e 35. st_ino: /var == deploy/var.
    dev = {"/": 37, "/etc": 35, "/sysroot": 35, DEPLOY_VAR: 35, "/var": 35, "/boot": 35}
    ino = {"/": 2, "/etc": 300, "/sysroot": 256, DEPLOY_VAR: 400, "/var": 400, "/boot": 270}
    def _ident(p):
        if p not in ino: raise OSError(2, "sem stat fingido", p)
        return (dev[p], ino[p])
    orig = (E._st_dev, E._ident, disks._rotational, disks._sys_disk)
    E._st_dev = lambda p: dev[p]
    E._ident = _ident
    disks._rotational = lambda d: {"/dev/vda3": "1"}.get(d)
    disks._sys_disk = lambda d: "vda" if d == "/dev/vda3" else ""
    try:
        st = {}
        roots, exp, forca = E.planejar_raizes(["/"], False, st, mounts=M)
        btrfs = [r for r in roots if r in dev]
        ok(btrfs == ["/", "/boot", "/etc", "/sysroot", "/var"],
           f"/var entra UMA vez, pelo nome curto; deploy/var some — deu {btrfs}")
        ok(DEPLOY_VAR not in exp and "/var" in exp and forca,
           "a expandida que ficou e /var; a duplicata nao vira raiz nem expandida")
        ok(not any(e["motivo"] for e in st.get("incompleto", []) if e["onde"] == DEPLOY_VAR),
           "dedup nao e perda: o diretorio e varrido sob o outro nome, nada no funil")
        # com o dedup, nenhum root cai dentro de ostree/deploy: nao ha grupo com
        # a poda de snapshots desligada (era ele que varria /var de novo)
        ok(not any(E.eh_snapshot(r + "/") for r in roots),
           "nenhuma raiz dentro de ostree/deploy sobrou (nao ha grupo com snapshots ligados)")
        # o que o usuario DIGITOU manda: pediu o caminho longo, o /var expandido cede
        roots2, exp2, _ = E.planejar_raizes(["/", DEPLOY_VAR], False, {}, mounts=M)
        ok(DEPLOY_VAR in roots2 and "/var" not in roots2 and "/var" not in exp2,
           f"raiz digitada tem precedencia sobre a expandida do mesmo diretorio — deu {roots2}")
        # Mint/Ubuntu (sem bind): identidades todas distintas, nada muda
        Mint = disks._read_mounts([
            "/dev/mapper/vgmint-root / ext4 rw 0 0\n",
            "/dev/sda1 /mnt/DiscoQ ext4 rw 0 0\n",
            "/dev/sdb1 /media/rodrigo/4TB btrfs rw,subvol=/@ 0 0\n"])
        dev.update({"/mnt/DiscoQ": 10, "/media/rodrigo/4TB": 11})
        ino.update({"/mnt/DiscoQ": 2, "/media/rodrigo/4TB": 256})
        disks._rotational = lambda d: "0"
        disks._sys_disk = lambda d: d.split("/")[-1][:3]
        roots3, exp3, _ = E.planejar_raizes(["/"], False, {}, mounts=Mint)
        ok(roots3 == ["/", "/media/rodrigo/4TB", "/mnt/DiscoQ"] and exp3 == {"/media/rodrigo/4TB", "/mnt/DiscoQ"},
           f"Mint sem bind: expansao inalterada — deu {roots3}")
        # stat que falha (disco que nao existe aqui) nao derruba a expansao
        ino.pop("/mnt/DiscoQ")
        roots4, _, _ = E.planejar_raizes(["/"], False, {}, mounts=Mint)
        ok("/mnt/DiscoQ" in roots4, "sem identidade (stat falhou) a montagem entra como sempre")
    finally:
        E._st_dev, E._ident, disks._rotational, disks._sys_disk = orig


def test_nota_ostree_mesma_mecanica():
    """Bazzite/ostree (09/09/2026, decisao do Rodrigo): ostree/deploy e ostree/repo
    NAO tem mecanica propria — passam pelo MESMO "vivo primeiro, podadas so se
    faltar" do Timeshift (_plano_extensao), com o mesmo motivo no funil. So o
    TEXTO da nota muda (acervo do sistema, nao snapshot), decidido pelo padrao
    que casou, nao por /run/ostree-booted. UMA nota ("/ostree" e symlink de
    "/sysroot/ostree": mesmo acervo, atribuido a raiz mais especifica). O repo
    (content-addressed) nunca e estendido, e a nota diz isso."""
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix="lfs_ostree_")
    os.makedirs(os.path.join(d, "sysroot", "ostree", "repo"))
    os.makedirs(os.path.join(d, "sysroot", "ostree", "deploy"))
    os.symlink("sysroot/ostree", os.path.join(d, "ostree"))
    sysroot = os.path.join(d, "sysroot")
    deploy = os.path.join(sysroot, "ostree", "deploy")
    def plano(roots, counts, digitadas=None, skip=True):
        st, evs = {}, []
        q = E.Query(paths=digitadas or roots, skip_snapshots=skip)
        pl = E._plano_extensao(q, roots, counts, False, st,
                               lambda ev, i: evs.append((ev, i["path"], i["ostree"], i["trees"])))
        return [a["arvore"] for a in pl], [(e["motivo"], e["onde"]) for e in st.get("incompleto", [])], evs, st
    try:
        # zero no vivo: estende SO o deploy (repo fica de fora), nota 'searched', texto ostree
        ext, fila, evs, st = plano([d, sysroot], {d: 0, sysroot: 0}, [d])
        ok(ext == [deploy], f"zero no vivo: estende ostree/deploy e NAO ostree/repo — deu {ext}")
        ok(fila == [("snapshots_searched", sysroot)],
           f"UMA nota, mesmo motivo do Timeshift (snapshots_searched), na raiz mais especifica — deu {fila}")
        ok(evs == [("snapshots_searched", sysroot, True, [deploy])],
           f"painel recebe o evento comum com a marca ostree e a arvore estendida — deu {evs}")
        _, linhas = E.resumo_incompleto(st)
        ok(linhas == [f"snapshots searched in {sysroot}: " + E._TEXTO_PODA[("ostree", "searched")]],
           f"texto honesto em EN-US (acervo do sistema; repo nunca varrido) — deu {linhas}")
        # achado vivo na raiz DIGITADA (mesmo com /sysroot em zero): nada estendido
        ext, fila, evs, _ = plano([d, sysroot], {d: 3, sysroot: 0}, [d])
        ok(ext == [] and fila == [("snapshots_skipped", sysroot)] and evs[0][2] is True,
           f"'zero' e por raiz DIGITADA: /sysroot em zero nao estende se '/' achou — deu {ext}, {fila}")
        # --snapshots: estende sem esperar zero
        ext, fila, _, _ = plano([d, sysroot], {d: 3, sysroot: 0}, [d], skip=False)
        ok(ext == [deploy] and fila == [("snapshots_searched", sysroot)],
           f"--snapshots estende mesmo com achado vivo — deu {ext}, {fila}")
        # so a raiz-mae (--one-fs): a nota vai pra ela
        ext, fila, _, _ = plano([d], {d: 0})
        ok(fila == [("snapshots_searched", d)], f"so a raiz-mae: a nota vai pra ela — deu {fila}")
        # Timeshift no mesmo root: mesma mecanica, texto de snapshot, ao lado
        os.makedirs(os.path.join(d, "timeshift", "snapshots", "2026-09-09"))
        ext, fila, evs, st = plano([d, sysroot], {d: 0, sysroot: 0}, [d])
        ok(sorted(ext) == sorted([deploy, os.path.join(d, "timeshift", "snapshots")]),
           f"Timeshift e ostree/deploy entram pela MESMA extensao — deu {ext}")
        ok(fila == [("snapshots_searched", sysroot), ("snapshots_searched", d)]
           or fila == [("snapshots_searched", d), ("snapshots_searched", sysroot)],
           f"duas notas, mesmo motivo, textos distintos — deu {fila}")
        textos = {e["onde"]: e["detalhe"] for e in st["incompleto"]}
        ok(textos[sysroot] == E._TEXTO_PODA[("ostree", "searched")]
           and textos[d] == E._TEXTO_PODA[("snapshot", "searched")], "texto por tipo de arvore")
        ok("snapshots_searched" not in E.MOTIVOS_GRAVES and "snapshots_skipped" not in E.MOTIVOS_GRAVES,
           "poda e extensao continuam nao-graves (exit code 0/1 intacto)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_jobs_de_rede():
    """Montagem de rede tem dono do numero: NET_WORKERS_PER_MOUNT do disks. O
    motor nao inventa o seu proprio."""
    try:
        from lfs import disks
    except Exception:
        print("~pula rede (sem pacote disks)"); return
    ok(E._jobs_para_classe(["network"]) == disks.NET_WORKERS_PER_MOUNT,
       "rede usa NET_WORKERS_PER_MOUNT, nao um numero solto no motor")
    ok(E._jobs_para_classe(["network", "rotational"]) == 1,
       "rede + mecanico no mesmo grupo leva a politica mais conservadora")


# ---- 2) streaming: o rápido não espera o lento
def _m(p): return E.Match(p, 0, 0.0)

def fabrica_sintetica(qq, cc, ss, procs=None):
    lento = qq.paths == ["/lento"]
    for i in range(3):
        if cc(): return
        if lento: time.sleep(0.30)
        ss["vistos"] = ss.get("vistos", 0) + 1
        yield _m(f"{qq.paths[0]}/{i}")

def test_streaming():
    q = E.Query(paths=["/lento", "/rapido"])
    stats, fins = {}, []
    t0 = time.time()
    tempos = []
    for m in E._iter_particionado(q, lambda: False, stats,
                                  [["/lento"], ["/rapido"]], fabrica_sintetica,
                                  ao_fim=lambda p, meu=None: fins.append((p, time.time() - t0))):
        tempos.append((m.path, time.time() - t0))
    rap = [t for p, t in tempos if p.startswith("/rapido")]
    len_lento = [t for p, t in tempos if p.startswith("/lento")]
    ok(len(tempos) == 6, "todos os achados dos dois discos chegam (6)")
    ok(max(rap) < max(len_lento), "disco rápido entrega antes do lento terminar")
    ok(stats.get("vistos") == 6, "stats dos workers são fundidos no dict compartilhado")
    ok([p for p, _ in fins] == [["/rapido"], ["/lento"]], "ao_fim na ordem de término")
    # ao_fim do rápido depois do último achado dele, antes do lento acabar
    fim_rapido = dict((tuple(p), t) for p, t in fins)[("/rapido",)]
    ok(fim_rapido >= max(rap), "ao_fim(grupo) só depois de entregues os achados dele")

def test_saida_antecipada():
    q = E.Query(paths=["/lento", "/rapido"])
    antes = threading.active_count()
    it = E._iter_particionado(q, lambda: False, {}, [["/lento"], ["/rapido"]],
                              fabrica_sintetica)
    next(it)
    it.close()                       # como o `break` do search() por max_results
    t0 = time.time()
    while threading.active_count() > antes and time.time() - t0 < 5:
        time.sleep(0.05)
    ok(threading.active_count() <= antes, "saída antecipada não deixa thread presa no put()")

def test_erro_de_um_disco():
    def fabrica_ruim(qq, cc, ss, procs=None):
        if qq.paths == ["/ruim"]:
            raise OSError("disco caiu")
        yield _m("/bom/1")
    stats = {}
    got = list(E._iter_particionado(E.Query(paths=["/ruim", "/bom"]), lambda: False,
                                    stats, [["/ruim"], ["/bom"]], fabrica_ruim))
    ok([m.path for m in got] == ["/bom/1"], "um disco quebrar não derruba a busca")
    ok(len(stats.get("erros", [])) == 1, "o erro do disco é registrado em stats['erros']")

def test_cancel_mata_processo():
    """F11 bug1 (achado pelo Fable 5): o worker fica bloqueado no read1() de um
    fd que nao tem mais nada a dizer naquele disco; o Event `parar` so seria
    lido se chegasse chunk. Sem MATAR o processo, cancelar esperava a caminhada
    inteira — no 4TB-Portable, ~1000 s de Cancel que nao solta."""
    import subprocess
    vistos = []

    def fabrica_bloqueante(qq, cc, ss, procs=None):
        if qq.paths == ["/rapido"]:
            yield _m("/rapido/0")
            return
        pr = subprocess.Popen(["sleep", "30"], stdout=subprocess.PIPE)
        if procs is not None:
            procs.append(pr)
        vistos.append(pr)
        pr.stdout.read()               # bloqueia ate o processo morrer
        return
        yield                          # noqa: torna a funcao um gerador

    it = E._iter_particionado(E.Query(paths=["/lento", "/rapido"]), lambda: False, {},
                              [["/lento"], ["/rapido"]], fabrica_bloqueante)
    next(it)                            # consome o achado do rapido
    t0 = time.time()
    it.close()                          # como o `break` do search() por max_results
    dt = time.time() - t0
    ok(dt < 3.0, f"cancelar solta em {dt:.2f}s sem esperar o disco lento")
    time.sleep(0.2)
    ok(vistos and vistos[0].poll() is not None,
       "o processo do disco lento foi morto, nao ficou martelando o disco")


for fn in (test_grupos, test_grupos_discos_reais, test_grupo_inacessivel,
           test_eh_snapshot, test_jobs_por_classe, test_lvm_nao_vira_desconhecido,
           test_composefs_herda_disco_do_datadir, test_bind_do_mesmo_diretorio_entra_uma_vez,
           test_nota_ostree_mesma_mecanica, test_jobs_de_rede,
           test_streaming,
           test_saida_antecipada, test_erro_de_um_disco, test_cancel_mata_processo):
    fn()
print(f"\n{'FALHOU: ' + ', '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
