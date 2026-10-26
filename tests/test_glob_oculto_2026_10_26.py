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

    # 6. Windows: oculto por ATRIBUTO (sem ponto no nome), 26/10/2026 — o '!.*'
    # não o alcança; engine.filtro_oculto_win tira o que o --glob deixou passar
    atrib = os.path.join(base, "rotina_atrib.txt")
    escreve(atrib)
    escreve(os.path.join(base, "pasta_atrib", "rotina_dentro2.txt"))
    if os.name == "nt":
        subprocess.run(["attrib", "+h", atrib], check=True)
        subprocess.run(["attrib", "+h", os.path.join(base, "pasta_atrib")], check=True)
        for modo in ("-c", "-b"):
            r = lista("-n", "rotina", modo, "agulha", base)
            ok(r == so_visivel, f"Windows {modo}: oculto por atributo fica de fora ({r})")
        r = lista("-n", "rotina", "-c", "agulha", "--hidden", base)
        ok("rotina_atrib.txt" in r, f"Windows --hidden: o oculto por atributo volta ({r})")
    else:
        # Linux: o atributo não existe; simula o _oculto do Windows para
        # exercitar o filtro (raiz, componente do meio, cache por pasta)
        salvo_win, salvo_oc = engine.plat.IS_WIN, engine._oculto
        chamadas = []
        engine.plat.IS_WIN = True
        engine._oculto = lambda pasta, nome: chamadas.append(nome) or nome.endswith("atrib") or nome == "rotina_atrib.txt"
        try:
            f = engine.filtro_oculto_win(Query(paths=[base], name_patterns=["*rotina*"]))
            ok(f is not None and f(atrib), "simulado: arquivo com atributo sai")
            ok(f(os.path.join(base, "pasta_atrib", "rotina_dentro2.txt")), "simulado: pasta com atributo no caminho sai")
            ok(not f(os.path.join(base, "visivel_rotina.txt")), "simulado: visível fica")
            f(os.path.join(base, "normal", "a.txt"))
            n = len(chamadas)
            f(os.path.join(base, "normal", "b.txt"))
            ok(len(chamadas) == n + 1, "simulado: a pasta já vista não é consultada de novo")
            ok(engine.filtro_oculto_win(Query(paths=[base], name_patterns=["*rotina*"], include_hidden=True)) is None,
               "simulado: com --hidden não há filtro")
            ok(engine.filtro_oculto_win(Query(paths=[base])) is None, "simulado: sem filtro de nome não há filtro")
        finally:
            engine.plat.IS_WIN, engine._oculto = salvo_win, salvo_oc
finally:
    shutil.rmtree(base, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
