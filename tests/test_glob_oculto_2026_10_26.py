#!/usr/bin/env python3
"""Filtro de nome + conteúdo não traz oculto sem --hidden (26/10/2026, Fable §2.5).

No rg, um --glob que casa o caminho é whitelist e vence o filtro de ocultos
(crate ignore). `-n rotina -c agulha` trazia .oculto_rotina.txt e entrava em
.rotina_x/; `-n rotina` sozinho (fd) e o fallback Python não traziam. A flag
"ocultos" tem de significar o mesmo nos quatro caminhos — e um .env ou
.netrc não pode aparecer numa busca "sem ocultos".

Contratos presos aqui:
  1. -c e -b com filtro de nome, sem --hidden: só o visível, igual ao -n;
  2. pasta oculta cujo nome casa o filtro não é aberta;
  3. com --hidden, os ocultos voltam;
  4. raiz digitada DENTRO de pasta oculta continua buscada (o '!.*' casa só
     o nome, não o caminho da raiz);
  5. rg e fallback Python dão o mesmo conjunto.

Rode:
    python3 tests/test_glob_oculto_2026_10_26.py
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine
from engine import Query

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

def escreve(caminho, texto="agulha\n"):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w") as f:
        f.write(texto)

base = tempfile.mkdtemp(prefix="sfs_glob_oculto_")
escreve(os.path.join(base, ".oculto_rotina.txt"))
escreve(os.path.join(base, "visivel_rotina.txt"))
escreve(os.path.join(base, ".rotina_dir", "rotina_dentro.txt"))
escreve(os.path.join(base, ".cfg", "rotina_cfg.txt"))

cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
env = dict(os.environ, LANG="C.UTF-8")
def lista(*args):
    p = subprocess.run(cli + list(args) + ["-l"], capture_output=True, text=True, env=env, timeout=60)
    return sorted(os.path.relpath(L, base) for L in p.stdout.splitlines() if L)

def nomes(q):
    res = []
    engine.search(q, res.append)
    return sorted(os.path.relpath(m.path, base) for m in res)

try:
    so_visivel = ["visivel_rotina.txt"]
    ok(lista("-n", "rotina", base) == so_visivel, f"-n: só o visível ({lista('-n', 'rotina', base)})")
    for modo in ("-c", "-b"):
        r = lista("-n", "rotina", modo, "agulha", base)
        ok(r == so_visivel, f"-n rotina {modo}: só o visível, sem abrir .rotina_dir ({r})")
    r = lista("-n", "rotina", "-c", "agulha", "--hidden", base)
    ok(".oculto_rotina.txt" in r and os.path.join(".rotina_dir", "rotina_dentro.txt") in r,
       f"com --hidden os ocultos voltam ({r})")
    r = subprocess.run(cli + ["-n", "rotina", "-c", "agulha", "-l", os.path.join(base, ".cfg")],
                       capture_output=True, text=True, env=env, timeout=60).stdout
    ok("rotina_cfg.txt" in r, "raiz dentro de pasta oculta continua buscada")

    q = Query(paths=[base], name_patterns=[engine.as_name_glob("rotina")], content="agulha")
    com_rg = nomes(q)
    salvo = (engine.FD, engine.RG)
    engine.FD = engine.RG = None
    try:
        sem_rg = nomes(q)
    finally:
        engine.FD, engine.RG = salvo
    ok(com_rg == sem_rg == so_visivel, f"rg e fallback concordam ({com_rg} × {sem_rg})")
finally:
    shutil.rmtree(base, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
