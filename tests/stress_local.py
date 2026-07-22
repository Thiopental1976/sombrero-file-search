#!/usr/bin/env python3
"""Bateria de stress LOCAL — complemento adversarial à suíte, rodada no metal
(ServidorCedro, discos reais) contra o código pós-`4d6382b`. Foco nos caminhos
frescos: guarda S_ISREG do T1, fallback `_display_lines_py` do T2 e a PARIDADE
com/sem ripgrep. Difere do test_audit por atacar bordas que a suíte não cobre
(zoo de não-regulares, volume, nomes/conteúdo não-UTF-8) e por medir wall-clock.

Rode:  python3 tests/stress_local.py
Sai != 0 se qualquer verificação falhar.
"""
from __future__ import annotations
import os, sys, socket, threading, tempfile, shutil, time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, boolean
from engine import Query

PASS, FAIL = [], []
def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'ok ' if cond else 'XX '} {name}" + (f"   {extra}" if extra else ""))

def run_boolean(d, expr, no_rg=True, timeout=15, content="", **qkw):
    """search_boolean numa thread com timeout; devolve (travou?, matches)."""
    orig = (engine.RG, engine.RGA, engine.FD)
    if no_rg:
        engine.RG = engine.RGA = engine.FD = ""
    box = {}
    def go():
        got = []
        boolean.search_boolean(Query(paths=[d], content=content, **qkw), expr,
                               lambda m: got.append(m))
        box["m"] = got
    th = threading.Thread(target=go, daemon=True); th.start(); th.join(timeout)
    engine.RG, engine.RGA, engine.FD = orig
    return th.is_alive(), box.get("m", [])

def run_names(d, no_rg=True, timeout=15, **qkw):
    orig = (engine.RG, engine.RGA, engine.FD)
    if no_rg:
        engine.RG = engine.RGA = engine.FD = ""
    got, box = [], {}
    def go():
        engine.search(Query(paths=[d], **qkw), lambda m: got.append(m))
        box["done"] = True
    th = threading.Thread(target=go, daemon=True); th.start(); th.join(timeout)
    engine.RG, engine.RGA, engine.FD = orig
    return th.is_alive(), got

# ---------------------------------------------------------------- 1. zoo de não-regulares
d = tempfile.mkdtemp(prefix="stress_zoo_")
try:
    with open(os.path.join(d, "achar.txt"), "w") as f: f.write("tem alvo aqui\n")
    os.mkfifo(os.path.join(d, "p1.fifo"))
    os.mkfifo(os.path.join(d, "alvo_no_nome_p2"))     # FIFO cujo NOME casa
    sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sk.bind(os.path.join(d, "s1.sock"))
    os.symlink(os.path.join(d, "p1.fifo"), os.path.join(d, "link_para_fifo.txt"))
    os.symlink(os.path.join(d, "nao_existe"), os.path.join(d, "quebrado.txt"))

    hung, ms = run_boolean(d, "alvo", no_rg=True)
    check("1a zoo: booleano sem rg NÃO trava com FIFO/socket/symlink->FIFO", not hung,
          f"achou={sorted(os.path.basename(m.path) for m in ms)}")
    check("1b zoo: conteúdo só no arquivo regular",
          not hung and {os.path.basename(m.path) for m in ms} == {"achar.txt"})
    hung2, ns = run_names(d, no_rg=True, name_patterns=["*alvo_no_nome*"])
    check("1c zoo: FIFO aparece na busca por NOME (listar é seguro)",
          not hung2 and any("alvo_no_nome_p2" in m.path for m in ns))
    sk.close()
finally:
    shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- 2. paridade com/sem rg
d = tempfile.mkdtemp(prefix="stress_parity_")
try:
    with open(os.path.join(d, "a.txt"), "w") as f:
        f.write("Paciente com LAUDO\nsegunda linha\npalavra laudos aqui\n")
    with open(os.path.join(d, "b.log"), "w") as f:
        f.write("nada relevante\nLaudo exato\n")
    with open(os.path.join(d, "bin.dat"), "wb") as f:
        f.write(b"laudo\x00binario com laudo depois do NUL\n")
    with open(os.path.join(d, "acento.txt"), "w") as f:
        f.write("relatório com açúcar e laudo\n")

    def summary(ms):
        return {os.path.basename(m.path): [(ln, txt) for ln, txt in m.lines] for m in ms}

    have_rg = bool(engine.RG)
    results = {}
    for tag, norg in (("com_rg", False), ("sem_rg", True)):
        if tag == "com_rg" and not have_rg:
            continue
        _, ms = run_boolean(d, "laudo", no_rg=norg)
        results[tag] = summary(ms)
    if have_rg:
        check("2a paridade: mesmos arquivos com e sem rg",
              set(results["com_rg"]) == set(results["sem_rg"]),
              f"com={set(results['com_rg'])} sem={set(results['sem_rg'])}")
        check("2b paridade: mesmas linhas (nº+texto) com e sem rg",
              results["com_rg"] == results["sem_rg"])
    else:
        check("2a paridade: (sem rg no ambiente — pulado o lado com-rg)", True)
    check("2c binário com NUL é ignorado no fallback", "bin.dat" not in results["sem_rg"])
    ac = results["sem_rg"].get("acento.txt", [])
    check("2d linha com acento vem íntegra sem rg", bool(ac) and "açúcar" in ac[0][1], f"{ac}")
    check("2e case-insensitive pega LAUDO/Laudo/laudo",
          "b.log" in results["sem_rg"] and "a.txt" in results["sem_rg"])

    _, got_ww = run_boolean(d, "laudos", no_rg=True, whole_word=True)
    ww = {os.path.basename(m.path) for m in got_ww}
    check("2f whole_word sem rg: 'laudos' casa a.txt mas não b.log",
          "a.txt" in ww and "b.log" not in ww, f"{ww}")
finally:
    shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- 3. volume sem rg
d = tempfile.mkdtemp(prefix="stress_vol_")
try:
    N = 3000
    for i in range(N):
        with open(os.path.join(d, f"f{i:04d}.txt"), "w") as f:
            f.write(f"linha um\nalvo na {i}\n" if i % 2 == 0 else "sem nada aqui\n")
    t0 = time.time()
    hung, ms = run_boolean(d, "alvo", no_rg=True, timeout=60)
    dt = time.time() - t0
    check("3a volume 3000 arq sem rg termina sem travar", not hung,
          f"{len({m.path for m in ms})} hits em {dt:.2f}s")
    check("3b volume: todo hit tem linha coletada", all(m.lines for m in ms), f"n={len(ms)}")
finally:
    shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- 4. nomes/conteúdo não-UTF-8
d = tempfile.mkdtemp(prefix="stress_utf_")
try:
    bad = os.path.join(os.fsencode(d), b"n\xff\xfe.txt")
    with open(bad, "wb") as f: f.write("conteudo com alvo\n".encode())
    with open(os.path.join(d, "ok.txt"), "wb") as f:
        f.write(b"linha valida com alvo\nlinha \xff\xfe suja binaria-ish\n")
    hung, ms = run_boolean(d, "alvo", no_rg=True)
    check("4a nome não-UTF-8 não quebra a busca de conteúdo sem rg", not hung, f"n={len(ms)}")
    check("4b achou conteúdo em arquivo de nome não-UTF-8",
          any(b"\xff\xfe" in os.fsencode(m.path) for m in ms))
finally:
    shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- 5. FIFO no meio de resultado grande
d = tempfile.mkdtemp(prefix="stress_fiforesult_")
try:
    for i in range(50):
        with open(os.path.join(d, f"r{i:02d}.txt"), "w") as f: f.write("achado\n")
    os.mkfifo(os.path.join(d, "meio.txt"))
    hung, ms = run_boolean(d, "achado", no_rg=True, timeout=15)
    check("5 FIFO no meio de 50 resultados não pendura _display_lines_py", not hung,
          f"hits={len(ms)}")
finally:
    shutil.rmtree(d, ignore_errors=True)

print("\n" + "=" * 60)
print(f"LOCAL STRESS: {len(PASS)} ok, {len(FAIL)} falhas")
if FAIL:
    print("FALHAS:", FAIL); sys.exit(1)
print("TODOS VERDES")
