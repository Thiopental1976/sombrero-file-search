#!/usr/bin/env python3
"""CLI: o cabeçalho `# engine:` fala inglês também quando falta motor (20/10/2026).

A regra do projeto é CLI sempre em inglês (contrato para scripts do mundo todo),
mas `engine_info()` devolvia "(ausente — fallback Python)" e "(ausente — sem modo
documentos)", e a CLI imprimia isso cru no stderr. Só aparecia na máquina SEM
rg/fd/rga, justamente a que nenhum teste rodava.

Dois contratos presos aqui:
  1. sem motor, o texto é inglês (nenhuma palavra em português);
  2. sem motor, o texto começa com "(" — é assim que a GUI decide a bolinha
     cinza do selo (`_refresh_badges`); com motor, é o caminho do binário.

Rode:
    python3 tests/test_cli_ingles_2026_10_20.py
"""
from __future__ import annotations
import os, subprocess, sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

PORTUGUES = ("ausente", "sem ", "documentos", "modo")

salvo = (engine.RG, engine.FD, engine.RGA)
try:
    engine.RG = engine.FD = engine.RGA = None
    info = engine.engine_info()
    for chave, valor in info.items():
        ok(not any(p in valor.lower() for p in PORTUGUES),
           f"sem motor, {chave} em inglês ({valor!r})")
        ok(valor.startswith("("), f"sem motor, {chave} começa com '(' (selo cinza da GUI)")
finally:
    engine.RG, engine.FD, engine.RGA = salvo

info = engine.engine_info()
for chave, valor in info.items():
    if valor.startswith("("):
        continue                     # motor ausente nesta máquina: já coberto acima
    ok(os.path.isabs(valor), f"com motor, {chave} é o caminho do binário ({valor!r})")

# Ponta a ponta: a CLI de verdade, num PATH sem rg/fd/rga, imprime o cabeçalho.
vazio = os.path.join(RAIZ, "tests")        # pasta sem binários de busca
env = dict(os.environ, PATH=vazio, LANG="C.UTF-8")
p = subprocess.run([sys.executable, os.path.join(RAIZ, "lfs", "cli.py"), vazio, "-n", "zzz_nada"],
                   capture_output=True, text=True, env=env, timeout=120)
cab = next((L for L in p.stderr.splitlines() if L.startswith("# engine:")), "")
ok(cab != "", f"CLI imprime o cabeçalho '# engine:' ({cab!r})")
ok(not any(w in cab.lower() for w in PORTUGUES), f"cabeçalho da CLI sem português ({cab!r})")

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
