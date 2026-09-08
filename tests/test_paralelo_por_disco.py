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
    ok(E._jobs_para_classe(["klass_que_nao_existe"]) is None,
       "classe desconhecida NAO estrangula: errar pra menos custa 12,5x, pra mais 21%")


def test_lvm_nao_vira_desconhecido():
    """/ no Mint e no Ubuntu e LVM, e o portatil e LUKS: /dev/mapper/* nao tem
    'rotational' proprio. Antes o disks devolvia None pros dois, e sob /mnt|/media
    isso virava "rotational" por padrao — um NVMe em gaveta USB com LUKS levava
    1 thread, 12,5x mais lento. O conserto e no disks._rotational (nao no motor)
    porque path_needs_serial e search_profile bebem da mesma fonte."""
    try:
        from lfs import disks
    except Exception:
        print("~pula lvm (sem pacote disks)"); return
    if not os.path.isdir("/sys/block"):
        print("~pula lvm (sem /sys/block)"); return
    k = disks.search_profile("/").klass
    ok(k in ("ssd", "rotational"), f"/ (LVM) e classificado de verdade (deu {k!r})")
    ok(disks._rotational("/dev/mapper/vgmint-root") in ("0", "1", None),
       "dm nao quebra o _rotational")
    ok(E._jobs_para_classe([k]) == E._JOBS_POR_CLASSE.get(k),
       "a classe resolvida escolhe o pool")


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
           test_jobs_de_rede,
           test_streaming,
           test_saida_antecipada, test_erro_de_um_disco, test_cancel_mata_processo):
    fn()
print(f"\n{'FALHOU: ' + ', '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
