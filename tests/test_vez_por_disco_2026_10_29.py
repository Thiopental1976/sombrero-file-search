#!/usr/bin/env python3
"""A vez do disco físico (lfs/vez.py, desenho do Fable 29/10/2026, P1).

Contratos:
  1. FIFO: dois tickets no mesmo HD → o 2º começa quando o 1º solta, na ordem de chegada;
  4. grupo fundido {sda,sdb} só toma com os dois livres; 4 buscas cruzadas sem deadlock;
  5. cancel na espera volta em < 0,3 s, tira o ticket da fila, e o próximo toma;
  +  baixa=True não passa na frente de quem espera e não toma disco ocupado;
  +  on_espera só para espera > 100 ms; soltar é idempotente; chave "?" não ocupa nada.
"""
from __future__ import annotations
import os, sys, threading, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lfs"))
import vez as V

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

A = ("disco", frozenset({"sda"})); B = ("disco", frozenset({"sdb"}))
AB = ("disco", frozenset({"sda", "sdb"}))

# 1. FIFO
V._reset(); ordem = []; marcas = {}
def usa(nome, chave, dur, atraso=0.0):
    time.sleep(atraso)
    with V.vez(V.discos_de(chave), nome):
        marcas[nome] = [time.time()]; ordem.append(nome)
        time.sleep(dur)
        marcas[nome].append(time.time())
ts = [threading.Thread(target=usa, args=(n, A, 0.3, i * 0.05)) for i, n in enumerate(("aba1", "aba2", "aba3"))]
for t in ts: t.start()
for t in ts: t.join(5)
ok(ordem == ["aba1", "aba2", "aba3"], "FIFO: ordem de chegada (%s)" % ordem)
ok(all(marcas[b][0] >= marcas[a][1] - 0.001 for a, b in (("aba1", "aba2"), ("aba2", "aba3"))),
   "FIFO: sem sobreposição no mesmo disco")
gaps = [marcas[b][0] - marcas[a][1] for a, b in (("aba1", "aba2"), ("aba2", "aba3"))]
ok(max(gaps) < 0.05, "FIFO: disco não fica ocioso entre uma e outra (gaps %s)" % ["%.3f" % g for g in gaps])
ok(V.ocupados() == ({}, {}), "registro vazio ao fim")

# discos diferentes não se esperam
V._reset(); marcas.clear(); ordem.clear()
ts = [threading.Thread(target=usa, args=("a", A, 0.4)), threading.Thread(target=usa, args=("b", B, 0.4))]
t0 = time.time()
for t in ts: t.start()
for t in ts: t.join(5)
ok(time.time() - t0 < 0.6, "discos diferentes rodam juntos (%.2f s)" % (time.time() - t0))

# 4. VG fundido, atômico, sem deadlock
V._reset(); marcas.clear(); ordem.clear()
ts = [threading.Thread(target=usa, args=("soA", A, 0.3)),
      threading.Thread(target=usa, args=("AB", AB, 0.2, 0.05)),
      threading.Thread(target=usa, args=("soB", B, 0.3, 0.1)),
      threading.Thread(target=usa, args=("AB2", AB, 0.1, 0.15))]
t0 = time.time()
for t in ts: t.start()
for t in ts: t.join(5)
ok(all(not t.is_alive() for t in ts) and time.time() - t0 < 5, "VG: 4 buscas cruzadas terminam (sem deadlock)")
def sobrepoe(x, y):
    return marcas[x][0] < marcas[y][1] - 0.001 and marcas[y][0] < marcas[x][1] - 0.001
ok(not sobrepoe("AB", "soA") and not sobrepoe("AB", "soB") and not sobrepoe("AB2", "soB"),
   "VG: o grupo {sda,sdb} nunca divide disco com ninguém")
ok(ordem.index("AB") < ordem.index("soB"), "VG: FIFO vale no conjunto (AB pediu antes de soB)")

# 5. cancel na espera
V._reset()
segura = V.pedir(V.discos_de(A), "aba1")
cancela = {"v": False}; res = {}
def espera():
    t = time.time()
    try:
        V.pedir(V.discos_de(A), "aba2", cancel=lambda: cancela["v"])
        res["r"] = "tomou"
    except V.Cancelado:
        res["r"] = "cancelado"
    res["dt"] = time.time() - t
th = threading.Thread(target=espera); th.start()
time.sleep(0.3); tc = time.time(); cancela["v"] = True; th.join(2)
ok(res.get("r") == "cancelado" and time.time() - tc < 0.3, "cancel na espera volta rápido (%s)" % res)
ok(V.ocupados()[1] == {}, "cancel tira o ticket da fila")
tk3 = {}
th = threading.Thread(target=lambda: tk3.setdefault("t", V.pedir(V.discos_de(A), "aba3"))); th.start()
time.sleep(0.1); V.soltar(segura); V.soltar(segura); th.join(2)
ok("t" in tk3 and V.quem_segura("sda") is tk3["t"], "o próximo da fila toma; soltar 2× é inofensivo")
V.soltar(tk3["t"])

# baixa prioridade (updatedb do Flash)
V._reset()
seg = V.pedir(V.discos_de(A), "aba1")
esp = {}
th_b = threading.Thread(target=lambda: esp.setdefault("tb", V.pedir(V.discos_de(A), "conferência", baixa=True)))
th_b.start(); time.sleep(0.1)
th_n = threading.Thread(target=lambda: esp.setdefault("tn", V.pedir(V.discos_de(A), "aba2")))
th_n.start(); time.sleep(0.1)
V.soltar(seg); th_n.join(2); time.sleep(0.1)
ok("tn" in esp and "tb" not in esp, "baixa: a busca que chegou depois passa na frente da conferência")
V.soltar(esp["tn"]); th_b.join(2)
ok("tb" in esp, "baixa: toma quando o disco fica livre e a fila vazia")
V.soltar(esp["tb"])

# on_espera: só para espera > 100 ms, com quem segura e a posição
V._reset()
avisos = []
seg = V.pedir(V.discos_de(A), "aba1")
rapido = threading.Thread(target=lambda: V.soltar(V.pedir(V.discos_de(B), "x", on_espera=lambda *a: avisos.append(a))))
rapido.start(); rapido.join(2)
ok(avisos == [], "on_espera: sem aviso quando toma na hora")
th = threading.Thread(target=lambda: V.soltar(V.pedir(V.discos_de(A), "aba2",
                                                       on_espera=lambda tk, q, p: avisos.append((q.dono, p)))))
th.start(); time.sleep(0.4); V.soltar(seg); th.join(2)
ok(avisos == [("aba1", 1)], "on_espera: diz quem segura e a posição (%s)" % avisos)
ok(V.discos_de(("?", "/x")) == frozenset() and V.pedir(frozenset(), "y").discos == frozenset(),
   "chave '?' (stat falhou) não ocupa disco")

print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
