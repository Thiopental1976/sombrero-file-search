#!/usr/bin/env python3
"""Regressões da 2ª revisão do Fable (22/09/2026), sobre a sessão 21–22/09.

Achado na evidência de campo (docs/campo/2026-09-22-nas-truenas/2_nas_congelado):
o NAS congelado era a RAIZ DIGITADA e a CLI saiu 1 ("nada encontrado") com
`warn` no --json. Pela regra do H3 (raiz inexistente / não montada é grave
porque é ZERO daquele lugar apresentado como resposta), a raiz digitada morta
é grave. Montagem morta EXPANDIDA sob "/" segue não-grave (F9a: pula e segue).
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, shutil

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, disks, boolean     # noqa: E402
from engine import Query          # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

_d = tempfile.mkdtemp(prefix="sfs_rev2_")
nas = os.path.join(_d, "NAS"); os.makedirs(os.path.join(nas, "sub"))
open(os.path.join(nas, "sub", "laudo.txt"), "w").write("laudo\n")
open(os.path.join(_d, "local.txt"), "w").write("laudo\n")

net = disks.IOProfile("network", nas, "cifs", False, True, 4, True)
_sp, _ms, _mu = disks.search_profile, disks.mount_status, disks.mounts_under
try:
    disks.search_profile = lambda p, mounts=None: net if p.startswith(nas) else _sp(p, mounts)
    disks.mount_status = lambda mp, timeout=3.0, **k: "no_response"
    disks.mounts_under = lambda r, mounts=None: [nas] if r.rstrip("/") == _d else _mu(r, mounts)

    st = {}; engine.search(Query(paths=[nas], content="laudo"), lambda m: None, stats=st)
    ok(engine.resumo_incompleto(st)[0], "busca simples: raiz DIGITADA morta é grave")
    st = {}; boolean.search_boolean(Query(paths=[nas]), "laudo AND x", lambda m: None, stats=st)
    ok(engine.resumo_incompleto(st)[0], "booleano: raiz DIGITADA morta é grave")

    st = {}; r = []
    engine.search(Query(paths=[_d], content="laudo"), r.append, stats=st)
    ok(not engine.resumo_incompleto(st)[0] and any(e["motivo"] == "dead_mount" for e in st["incompleto"])
       and len(r) == 1,
       "montagem morta EXPANDIDA sob a raiz: dead_mount NÃO-grave, e o local foi achado")

    d = {}; engine._funde_stats(d, {"incompleto": [{"motivo": "dead_mount", "onde": nas,
                                                    "detalhe": "x", "n": 1, "grave": True}]})
    ok(engine.resumo_incompleto(d)[0], "a fusão do particionado preserva a gravidade")
    ok(json.loads(json.dumps(st["incompleto"])) == st["incompleto"], "entrada do funil segue serializável")
finally:
    disks.search_profile, disks.mount_status, disks.mounts_under = _sp, _ms, _mu

# CLI de ponta a ponta: o reason fica 'dead_mount' (contrato), mas sai como error e exit 2
prelude = f'''
import sys, os; sys.path.insert(0, {os.path.join(RAIZ, "lfs")!r})
import disks
net = disks.IOProfile("network", {nas!r}, "cifs", False, True, 4, True)
_sp = disks.search_profile
disks.search_profile = lambda p, mounts=None: net if p.startswith({nas!r}) else _sp(p, mounts)
disks.mount_status = lambda mp, timeout=3.0, **k: "no_response"
sys.argv = ["sfs", {nas!r}, "-c", "laudo", "--json"]
import cli; cli._main_protegido()
'''
r = subprocess.run([sys.executable, "-c", prelude], capture_output=True, text=True, timeout=60)
evs = [json.loads(L) for L in r.stdout.splitlines() if L.startswith("{")]
inc = [e for e in evs if e.get("reason") == "dead_mount"]
ok(r.returncode == 2 and inc and "error" in inc[0],
   f"CLI: raiz digitada morta -> exit 2 e {{\"error\": \"incomplete\", reason: dead_mount}} (rc={r.returncode})")
ok("INCOMPLETE" in r.stderr, "CLI: stderr avisa que o resultado está INCOMPLETO, não 'nada encontrado'")

shutil.rmtree(_d, ignore_errors=True)
print()
if falhas:
    print(f"{len(falhas)} FALHA(S)"); sys.exit(1)
print("todos os testes passaram")
