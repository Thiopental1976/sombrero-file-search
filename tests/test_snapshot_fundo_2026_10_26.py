#!/usr/bin/env python3
"""Árvore de snapshot abaixo do 1º nível da raiz (26/10/2026, Fable §2.2).

A poda dos motores vale em qualquer profundidade (`**/.snapshots/**`), mas a
detecção das árvores para a extensão "vivo primeiro, snapshots só se faltar"
era um glob no 1º nível. /x/sub/.snapshots era podada e nunca estendida:
`sfs -n alvo /x` dava 0 resultados, exit 1, sem nota — nem --snapshots
alcançava. Casos reais: snapper num subvolume aninhado, backup do Timeshift
copiado para uma subpasta, @GMT-* dentro de uma pasta sincronizada.

Contratos presos aqui:
  1. zero no vivo: a árvore funda é estendida, com a nota de sempre (exit 0),
     nos modos -n, -c, -b, e também sem fd/rg (fallback Python);
  2. --snapshots alcança a árvore funda;
  3. com resultado vivo, nada de caminhada extra (a árvore funda fica de fora);
  4. pasta OCULTA no caminho até a árvore: sem --hidden a busca viva não
     entrou ali, então a extensão também não entra;
  5. rasa e funda juntas: as duas são estendidas;
  6. _padrao_no_fim reconhece a raiz de cada árvore podada.

Rode:
    python3 tests/test_snapshot_fundo_2026_10_26.py
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

base = tempfile.mkdtemp(prefix="sfs_snap_fundo_")
cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
env = dict(os.environ, LANG="C.UTF-8")
def busca(q):
    res = []
    engine.search(q, res.append)
    return res

def roda(*args):
    return subprocess.run(cli + list(args), capture_output=True, text=True, env=env, timeout=120)

try:
    # 6. reconhecimento
    ok(engine._padrao_no_fim("/a/b/.snapshots") == ".snapshots", "_padrao_no_fim: .snapshots")
    ok(engine._padrao_no_fim("/m/bk/timeshift/snapshots-daily") == "timeshift/snapshots*",
       "_padrao_no_fim: timeshift/snapshots-daily")
    ok(engine._padrao_no_fim("/nas/@GMT-2026.01.01-00.00.00") == "@GMT-*", "_padrao_no_fim: @GMT-*")
    ok(engine._padrao_no_fim("/a/snapshots") is None, "_padrao_no_fim: 'snapshots' solto não é Timeshift")

    # 1. zero no vivo, três modos
    d1 = os.path.join(base, "um")
    escreve(os.path.join(d1, "sub", ".snapshots", "1", "snapshot", "alvo.txt"))
    escreve(os.path.join(d1, "outra", "vivo.txt"), "nada\n")
    for modo in (["-n", "alvo"], ["-c", "agulha"], ["-b", "agulha"]):
        p = roda(*modo, d1)
        ok(p.returncode == 0 and "alvo.txt" in p.stdout,
           f"{modo[0]}: acha na árvore funda ({p.returncode})")
        ok("snapshots searched" in p.stderr, f"{modo[0]}: com a nota de extensão")

    # 1b. fallback Python (sem fd/rg)
    salvo = (engine.FD, engine.RG)
    engine.FD = engine.RG = None
    try:
        res = busca(Query(paths=[d1], name_patterns=[engine.as_name_glob("alvo*")]))
        ok(any(m.path.endswith("alvo.txt") for m in res), "fallback Python: acha na árvore funda")
        ach = engine._arvores_fundas([d1], Query(paths=[d1]))
        ok([p for _m, p in ach.get(d1, [])] == [os.path.join(d1, "sub", ".snapshots")],
           f"fallback Python: _arvores_fundas ({ach})")
    finally:
        engine.FD, engine.RG = salvo
    ach = engine._arvores_fundas([d1], Query(paths=[d1]))
    ok([p for _m, p in ach.get(d1, [])] == [os.path.join(d1, "sub", ".snapshots")],
       f"fd: _arvores_fundas ({ach})")

    # 2. --snapshots
    p = roda("-n", "alvo", "--snapshots", d1)
    ok(p.returncode == 0 and "alvo.txt" in p.stdout, "--snapshots alcança a árvore funda")

    # 3. com resultado vivo, não caminha de novo
    chamadas = []
    orig = engine._arvores_fundas
    engine._arvores_fundas = lambda *a, **k: chamadas.append(a) or orig(*a, **k)
    try:
        res = busca(Query(paths=[d1], name_patterns=[engine.as_name_glob("vivo*")]))
        ok(any(m.path.endswith("vivo.txt") for m in res), "resultado vivo achado")
        ok(chamadas == [], f"com resultado vivo, nenhuma caminhada extra ({len(chamadas)})")
        busca(Query(paths=[d1], name_patterns=[engine.as_name_glob("alvo*")]))
        ok(len(chamadas) == 1, "com zero no vivo, uma caminhada extra")
    finally:
        engine._arvores_fundas = orig

    # 4. pasta oculta no caminho
    d4 = os.path.join(base, "quatro")
    escreve(os.path.join(d4, ".escondida", ".snapshots", "1", "snapshot", "alvo.txt"))
    p = roda("-n", "alvo", d4)
    ok(p.returncode == 1 and "alvo.txt" not in p.stdout,
       f"sem --hidden: não estende sob pasta oculta ({p.returncode})")
    p = roda("-n", "alvo", "--hidden", d4)
    ok(p.returncode == 0 and "alvo.txt" in p.stdout, "com --hidden: estende")

    # 5. rasa e funda juntas
    d5 = os.path.join(base, "cinco")
    escreve(os.path.join(d5, ".snapshots", "1", "snapshot", "alvo_raso.txt"))
    escreve(os.path.join(d5, "a", "b", ".snapshots", "2", "snapshot", "alvo_fundo.txt"))
    p = roda("-n", "alvo", d5)
    ok("alvo_raso.txt" in p.stdout and "alvo_fundo.txt" in p.stdout,
       f"rasa e funda estendidas ({p.stdout.strip()!r})")
finally:
    shutil.rmtree(base, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
