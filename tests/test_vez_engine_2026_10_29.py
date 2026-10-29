#!/usr/bin/env python3
"""A vez do disco no MOTOR (desenho do Fable 29/10/2026, P2).

Topologia fictícia: discos A (HD, 1 s por busca), B (HD, 3 s), C (SSD, 0,1 s);
o walker Python é trocado por um que dorme e grava [início, fim] por (busca, disco).
Contratos:
  3. três buscas simultâneas nos três discos: em cada HD os intervalos não se
     sobrepõem e o disco NÃO fica ocioso entre uma busca e a outra (gap < 50 ms);
     a 3ª busca acaba no HD rápido em ≈3 s (não ≈9 s, que era o gate por busca);
     o SSD roda as 3 juntas;
  6. worker preso: após o teto, o registro fica vazio;
  8. root_waiting(por, posicao) → root_scanning → root_done, e nada de
     root_waiting quando a vez é tomada na hora;
  +  cancel durante a espera: a busca volta logo e o disco segue para a próxima.
"""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, vez as V
from lfs.disks import IOProfile

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

DUR = {"/A": 1.0, "/B": 3.0, "/C": 0.1}
CHAVE = {"/A": ("disco", frozenset({"sda"})), "/B": ("disco", frozenset({"sdb"})),
         "/C": ("disco", frozenset({"nvme0n1"}))}
def perfil(r):
    hd = r != "/C"
    return IOProfile(klass="rotational" if hd else "ssd", mountpoint=r, fstype="ext4",
                     serialize=hd, is_network=False, max_workers=None, enumerate_default=True)
CLASSES = {r: perfil(r) for r in DUR}

marcas = {}            # (busca, disco) -> [t_ini, t_fim]
lock = threading.Lock()
preso = threading.Event()

def walker_falso(q, stats=None, cancel=None, progresso=None):
    for r in q.paths:
        t = time.time()
        busca = q.name_patterns[0]
        fim = t + DUR[r]
        while time.time() < fim:
            if busca == "preso" and not preso.is_set():
                time.sleep(0.05); fim = time.time() + 1; continue   # não ouve o cancel
            if cancel is not None and cancel():
                break
            time.sleep(0.01)
        with lock:
            marcas[(busca, r)] = [t, time.time()]
        yield E.Match(path=r + "/achado", size=1, mtime=0.0)

E.FD = None
E._iter_names_python = walker_falso
E._chave_de_disco = lambda p: CHAVE[p]

def rodada(nome, roots, cancel=lambda: False, eventos=None):
    ev = eventos.append if eventos is not None else (lambda *a: None)
    entrega = E._Entrega(lambda m: None, lambda n: None, {}, 10**6, lambda *a: None)
    q = E.Query(paths=list(roots), name_patterns=[nome])
    counts = {r: 0 for r in roots}
    E._rodada(q, list(roots), CLASSES, cancel, {}, lambda e, i: ev((e, i)), entrega,
              counts=counts, dono=nome)

# 3. três buscas contínuas
V._reset(); marcas.clear()
t0 = time.time()
ts = []
for i, n in enumerate(("aba1", "aba2", "aba3")):
    th = threading.Thread(target=rodada, args=(n, ["/A", "/B", "/C"])); th.start(); ts.append(th)
    time.sleep(0.05)
for th in ts: th.join(20)
for d in ("/A", "/B"):
    iv = sorted(marcas[(n, d)] for n in ("aba1", "aba2", "aba3"))
    sob = any(iv[i + 1][0] < iv[i][1] - 0.001 for i in range(2))
    gaps = [iv[i + 1][0] - iv[i][1] for i in range(2)]
    ok(not sob, "%s: as 3 buscas não se sobrepõem no HD" % d)
    ok(max(gaps) < 0.05, "%s: nenhum disco ocioso entre buscas (gaps %s)" % (d, ["%.3f" % g for g in gaps]))
fimA3 = marcas[("aba3", "/A")][1] - t0
ok(2.8 < fimA3 < 4.0, "a 3ª busca termina no HD rápido em ≈3 s, não ≈9 s (%.2f s)" % fimA3)
c = [marcas[(n, "/C")] for n in ("aba1", "aba2", "aba3")]
ok(max(x[0] for x in c) < min(x[1] for x in c), "SSD: as 3 buscas rodam juntas")
ok(V.ocupados() == ({}, {}), "registro vazio ao fim")

# 8. eventos
V._reset(); marcas.clear()
ev1, ev2 = [], []
t1 = threading.Thread(target=rodada, args=("e1", ["/A"], lambda: False, ev1)); t1.start()
time.sleep(0.2)
rodada("e2", ["/A"], eventos=ev2); t1.join(5)
nomes2 = [e for e, _ in ev2]
esp = [i for e, i in ev2 if e == "root_waiting"]
ok(esp and esp[0]["por"] == "e1" and esp[0]["posicao"] == 1 and esp[0]["path"] == "/A",
   "root_waiting diz quem segura e a posição (%s)" % (esp[:1],))
ok(nomes2.index("root_waiting") < nomes2.index("root_scanning") < nomes2.index("root_done"),
   "sequência root_waiting → root_scanning → root_done (%s)" % nomes2)
ok("root_waiting" not in [e for e, _ in ev1], "quem toma na hora não emite root_waiting")

# cancel na espera
V._reset()
t1 = threading.Thread(target=rodada, args=("c1", ["/B"])); t1.start()
time.sleep(0.2)
cancela = {"v": False}; evc = []
tc = threading.Thread(target=rodada, args=("c2", ["/B"], lambda: cancela["v"], evc)); tc.start()
time.sleep(0.4); t_c = time.time(); cancela["v"] = True; tc.join(2)
ok(not tc.is_alive() and time.time() - t_c < 0.5, "cancel na espera: a busca volta logo")
done = [i for e, i in evc if e == "root_done"]
ok(done and done[0]["completo"] is False, "cancel na espera: root_done incompleto (%s)" % done)
ok(("c2", "/B") not in marcas, "cancel na espera: o disco nunca foi tocado pela busca cancelada")
t1.join(5)

# 6. worker preso além do teto: o registro fica vazio
V._reset(); preso.clear()
cancela = {"v": False}
th = threading.Thread(target=rodada, args=("preso", ["/A", "/C"], lambda: cancela["v"])); th.start()
time.sleep(0.3); cancela["v"] = True
th.join(8)
ok(not th.is_alive() and V.ocupados()[0] == {}, "worker preso: após o teto o disco é solto à força (%s)" % (V.ocupados(),))
preso.set()

print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
