#!/usr/bin/env python3
"""A vez do disco no BOOLEANO (desenho do Fable 29/10/2026, P3 + P3b).

Dois diretórios reais de mentira: /hd (perfil rotacional, serialize) e /ssd.
Contratos:
  7. `(a OR b OR c) AND NOT d` → UMA aquisição de vez por grupo de HD, nenhuma no
     SSD; no HD o OR roda sem pool (um cabeçote, uma varredura), no SSD com pool;
     a busca termina (teto 5 s = sem ciclo vez↔Event do single-flight B5) e o
     resultado é o certo, com as linhas de exibição (P3b: por grupo, dentro da vez);
  +  duas buscas booleanas no mesmo HD: a 2ª espera a vez (root_waiting com o dono).
"""
import os, sys, tempfile, threading, time, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, boolean as B, disks as D, vez as V

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

base = os.path.realpath(tempfile.mkdtemp(prefix="vez_bool_", dir=os.path.expanduser("~/.cache")))
HD, SSD = os.path.join(base, "hd"), os.path.join(base, "ssd")
for d in (HD, SSD):
    os.makedirs(d)
    open(os.path.join(d, "x1.txt"), "w").write("tem a e mais nada\n")
    open(os.path.join(d, "x2.txt"), "w").write("tem b\ne d também\n")
    open(os.path.join(d, "x3.txt"), "w").write("só c aqui\n")

real_prof = D.search_profile
def prof(p, mounts=None):
    hd = os.path.realpath(p).startswith(HD)
    return D.IOProfile(klass="rotational" if hd else "ssd", mountpoint=HD if hd else SSD,
                       fstype="ext4", serialize=hd, is_network=False, max_workers=None,
                       enumerate_default=True)
D.search_profile = prof
real_chave = E._chave_de_disco
E._chave_de_disco = lambda p: ("disco", frozenset({"sdz" if os.path.realpath(p).startswith(HD) else "nvme9"}))
B._WORKERS = max(B._WORKERS, 4)

pedidos, pools = [], []
real_pedir = V.pedir
def pedir_espiao(discos, dono="", *a, **k):
    pedidos.append((dono, sorted(discos)))
    return real_pedir(discos, dono, *a, **k)
V.pedir = pedir_espiao
real_eval = B._eval
def eval_espiao(ast, qg, cancel, cache, ub, *a, **k):
    if ast is EXPR_AST[0]:
        pool = a[1] if len(a) > 1 else k.get("pool")
        pools.append((tuple(qg.paths), pool is not None))
    return real_eval(ast, qg, cancel, cache, ub, *a, **k)
B._eval = eval_espiao
EXPR = "(a OR b OR c) AND NOT d"
EXPR_AST = [None]
real_parse = B.parse
def parse_espiao(e):
    n = real_parse(e); EXPR_AST[0] = n; return n
B.parse = parse_espiao

achados = []
t0 = time.time()
q = E.Query(paths=[HD, SSD], name_patterns=[], case_sensitive=True, whole_word=True)
res = {}
th = threading.Thread(target=lambda: res.setdefault("r", B.search_boolean(q, EXPR, achados.append, dono="aba1")))
th.start(); th.join(5)
ok(not th.is_alive(), "termina em < 5 s (sem ciclo vez↔Event)")
nomes = sorted(os.path.relpath(m.path, base) for m in achados)
ok(nomes == ["hd/x1.txt", "hd/x3.txt", "ssd/x1.txt", "ssd/x3.txt"], "resultado certo (%s)" % nomes)
ok(achados and all(m.lines for m in achados), "linhas de exibição presentes (P3b, por grupo)")
ok(pedidos == [("aba1", ["sdz"])], "1 aquisição de vez por grupo de HD, nenhuma no SSD (%s)" % pedidos)
ok(dict(pools) == {(HD,): False, (SSD,): True}, "OR sem pool no HD, com pool no SSD (%s)" % pools)
ok(V.ocupados() == ({}, {}), "registro vazio ao fim")

# duas booleanas no mesmo HD
V._reset(); pedidos.clear()
segura = real_pedir(frozenset({"sdz"}), "aba1")
ev = []
qh = E.Query(paths=[HD], name_patterns=[], case_sensitive=True, whole_word=True)
th = threading.Thread(target=lambda: B.search_boolean(qh, "a", lambda m: None,
                                                      on_event=lambda e, i: ev.append((e, i)), dono="aba2"))
th.start(); time.sleep(0.4)
esp = [i for e, i in ev if e == "root_waiting"]
ok(th.is_alive() and esp and esp[0]["por"] == "aba1", "2ª booleana no mesmo HD espera a vez e diz por quem (%s)" % esp[:1])
V.soltar(segura); th.join(5)
ok(not th.is_alive(), "e segue quando a vez chega")

shutil.rmtree(base, ignore_errors=True)
print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
