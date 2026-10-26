#!/usr/bin/env python3
"""Cópia colapsada avisada na saída de texto da CLI (26/10/2026, Fable §2.6).

O dedup de 09/09 (mesmo arquivo = uma linha) é legítimo, mas a CLI texto não
tinha canal nenhum para o caminho dobrado: `sfs -c x -l | xargs cp` perdia o
segundo nome de um hardlink sem aviso. Só o --json listava ({"copy": …}).

Contratos presos aqui:
  1. hardlink: stdout continua com UMA linha; stderr ganha a nota com a
     contagem, nos modos -n, -c, -b;
  2. --json não ganha a nota (lá cada cópia já é uma linha "copy");
  3. cópia idêntica em snapshot: nota própria;
  4. sem cópia, sem nota.

Rode:
    python3 tests/test_hardlink_cli_2026_10_26.py
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

base = tempfile.mkdtemp(prefix="sfs_hardlink_")
cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
env = dict(os.environ, LANG="C.UTF-8")
def roda(*args):
    return subprocess.run(cli + list(args), capture_output=True, text=True, env=env, timeout=60)

try:
    hl = os.path.join(base, "hl")
    os.makedirs(hl)
    with open(os.path.join(hl, "a.txt"), "w") as f:
        f.write("agulha\n")
    os.link(os.path.join(hl, "a.txt"), os.path.join(hl, "b.txt"))
    os.link(os.path.join(hl, "a.txt"), os.path.join(hl, "c.txt"))

    for modo in (["-n", "*.txt"], ["-c", "agulha", "-l"], ["-b", "agulha"]):
        p = roda(*modo, hl)
        linhas = [L for L in p.stdout.splitlines() if L]
        ok(len(linhas) == 1, f"{modo[0]}: uma linha no stdout ({linhas})")
        ok("# note: 2 more path(s) to files already listed" in p.stderr,
           f"{modo[0]}: nota com as 2 cópias dobradas")
    p = roda("-c", "agulha", "--json", hl)
    ok("# note:" not in p.stderr and p.stdout.count('"copy"') == 2,
       "--json: as cópias como linhas 'copy', sem a nota")

    sn = os.path.join(base, "sn")
    os.makedirs(os.path.join(sn, ".snapshots", "1", "snapshot"))
    with open(os.path.join(sn, "x.txt"), "w") as f:
        f.write("agulha\n")
    shutil.copy2(os.path.join(sn, "x.txt"), os.path.join(sn, ".snapshots", "1", "snapshot", "x.txt"))
    p = roda("-c", "agulha", "-l", "--snapshots", sn)
    ok([L for L in p.stdout.splitlines() if L] == [os.path.join(sn, "x.txt")],
       f"snapshot: só o arquivo vivo no stdout ({p.stdout!r})")
    ok("# note: 1 identical copy(ies) in snapshots folded" in p.stderr, "snapshot: nota própria")

    p = roda("-c", "agulha", "-l", os.path.join(sn, "x.txt").rsplit(os.sep, 1)[0])
    ok("# note: 1 identical" not in p.stderr and "more path(s)" not in p.stderr,
       "sem --snapshots (vivo achou): sem nota de cópia")
finally:
    shutil.rmtree(base, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
