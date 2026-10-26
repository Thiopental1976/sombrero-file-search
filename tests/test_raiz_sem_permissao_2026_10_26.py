#!/usr/bin/env python3
"""Raiz digitada sem permissão de leitura é grave (26/10/2026, Fable §2.4).

`sfs -c agulha /pasta_000` saía 1 com "1 directories without permission —
partial results": parcial de nada, com cara de "nada encontrado". Pela regra
da montagem morta digitada (22/09), nada foi olhado, então é grave.

Contratos presos aqui:
  1. raiz digitada sem leitura: exit 2 nos modos -n, -c, -b; --json traz
     "error" com reason permission_denied (o reason não muda);
  2. evento root_skipped com reason "denied" (painel da GUI);
  3. subpasta sem leitura continua não-grave (exit 0, warn);
  4. outra raiz legível na mesma busca continua sendo buscada.

Rode:
    python3 tests/test_raiz_sem_permissao_2026_10_26.py
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

WIN = os.name == "nt"
if not WIN and os.geteuid() == 0:
    print("(rodando como root: permissão não se nega, teste pulado)")
    sys.exit(0)

# Linux: chmod. Windows: o chmod não toca as ACLs — nega a leitura a Todos
# (S-1-1-0) com icacls, como um usuário sem acesso veria (CI 26/10/2026)
def fecha(p):
    if WIN:
        subprocess.run(["icacls", p, "/deny", "*S-1-1-0:(OI)(CI)(RX)"],
                       check=True, capture_output=True)
    else:
        os.chmod(p, 0)

def abre(p):
    if WIN:
        subprocess.run(["icacls", p, "/remove:d", "*S-1-1-0"], capture_output=True)
    else:
        os.chmod(p, 0o755)

base = tempfile.mkdtemp(prefix="sfs_sem_perm_")
fechada = os.path.join(base, "fechada")
aberta = os.path.join(base, "aberta")
os.makedirs(fechada); os.makedirs(os.path.join(aberta, "sub"))
for d in (fechada, aberta, os.path.join(aberta, "sub")):
    with open(os.path.join(d, "x.txt"), "w") as f: f.write("agulha\n")
fecha(fechada)
fecha(os.path.join(aberta, "sub"))

cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
env = dict(os.environ, LANG="C.UTF-8")
def roda(*args):
    return subprocess.run(cli + list(args), capture_output=True, text=True, env=env, timeout=60)

try:
    # 1. raiz fechada, três modos
    for modo in (["-n", "x"], ["-c", "agulha"], ["-b", "agulha"]):
        p = roda(*modo, fechada)
        ok(p.returncode == 2, f"{modo[0]} na raiz fechada sai 2 ({p.returncode})")
        ok("denied reading" in p.stderr, f"{modo[0]}: diz que a pasta negou a leitura")
    p = roda("-c", "agulha", "--json", fechada)
    objs = [json.loads(L) for L in p.stdout.splitlines() if L.startswith("{")]
    ok(any(o.get("error") == "incomplete" and o.get("reason") == "permission_denied"
           and o.get("where") == fechada for o in objs),
       f"--json: error permission_denied na raiz ({objs})")

    # 2. evento do painel
    evs = []
    stats = {}
    vivas = engine._live_roots([fechada], stats, on_event=lambda ev, info: evs.append((ev, info)))
    ok(vivas == [], "a raiz fechada não entra na busca")
    ok(any(ev == "root_skipped" and i.get("reason") == "denied" for ev, i in evs),
       "root_skipped com reason 'denied'")
    ok("denied" in engine.REASON_TEXTO, "REASON_TEXTO tem 'denied'")

    # 3. subpasta fechada segue não-grave
    p = roda("-c", "agulha", aberta)
    ok(p.returncode == 0, f"subpasta fechada: sai 0 ({p.returncode})")
    p = roda("-c", "agulha", "--json", aberta)
    objs = [json.loads(L) for L in p.stdout.splitlines() if L.startswith("{")]
    ok(not any(o.get("error") for o in objs), "subpasta fechada: nada de 'error' no --json")

    # 4. raiz aberta junto da fechada continua buscada
    p = roda("-c", "agulha", "-l", aberta, fechada)
    ok(os.path.join(aberta, "x.txt") in p.stdout, "a raiz aberta é buscada mesmo com a fechada junto")
    ok(p.returncode == 2, f"com uma raiz digitada fechada, a busca toda sai 2 ({p.returncode})")
finally:
    abre(fechada); abre(os.path.join(aberta, "sub"))
    shutil.rmtree(base, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
