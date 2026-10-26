#!/usr/bin/env python3
"""O `.ripgreprc` do usuário não muda a busca do SFS (26/10/2026, parecer do Fable §2.3).

O rg lê o arquivo apontado por RIPGREP_CONFIG_PATH em TODA chamada, e o rga
repassa ao rg. Uma config com `--glob=!*.txt` (ou --max-filesize, --type,
--ignore-file…) somava-se às flags do SFS e escondia arquivos: "0 resultados"
sem nenhum aviso, na busca de conteúdo, na booleana e em documentos. O fd não lê
essa config, então a busca por nome não era afetada.

Contratos presos aqui:
  1. `engine.rg_flags_comuns` (fonte única das flags de conteúdo E booleano)
     leva `--no-config`;
  2. ponta a ponta, com uma config hostil no ambiente, a CLI acha o arquivo
     nos três modos de conteúdo (-c, -b, -D) e sai 0.

Rode:
    python3 tests/test_ripgreprc_2026_10_26.py
"""
from __future__ import annotations
import os, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

q = engine.Query(paths=["/x"], content="agulha")
ok("--no-config" in engine.rg_flags_comuns(q), "rg_flags_comuns leva --no-config")
ok("--no-config" in engine.rg_flags_comuns(q, matching=False), "idem no universo do NOT")

if not engine.RG:
    print("(sem rg nesta máquina: ponta a ponta pulada — o fallback Python não lê .ripgreprc)")
else:
    tmp = tempfile.mkdtemp(prefix="sfs_ripgreprc_")
    palheiro = os.path.join(tmp, "palheiro"); os.mkdir(palheiro)
    with open(os.path.join(palheiro, "a.txt"), "w") as f:
        f.write("linha um\nagulha aqui\n")
    rc_hostil = os.path.join(tmp, "ripgreprc")
    with open(rc_hostil, "w") as f:
        f.write("--glob=!*.txt\n--max-count=0\n")
    env = dict(os.environ, LANG="C.UTF-8", RIPGREP_CONFIG_PATH=rc_hostil)
    cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
    modos = [("conteúdo", ["-c", "agulha"]), ("booleana", ["-b", "agulha"])]
    if engine.RGA:
        modos.append(("documentos", ["-D", "-c", "agulha"]))
    for nome, flags in modos:
        p = subprocess.run(cli + flags + ["-l", palheiro], capture_output=True, text=True,
                           env=env, timeout=120)
        achou = any(L.endswith("a.txt") for L in p.stdout.splitlines())
        ok(achou and p.returncode == 0,
           f"{nome}: acha a.txt com .ripgreprc hostil (rc={p.returncode}, saída={p.stdout.strip()!r})")

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
