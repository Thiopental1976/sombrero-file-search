#!/usr/bin/env python3
"""Regressões da revisão de código do Fable (21/09/2026).

Cada bloco prova um defeito que foi MEDIDO antes de ser corrigido — o número
medido está no comentário do bloco. Tudo em tempdir, sem tocar no acervo, sem
display, sem rede. Rode:  python3 tests/test_revisao_fable_2026_09_21.py
"""
from __future__ import annotations
import io, json, os, stat, subprocess, sys, tempfile, shutil, threading, time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, boolean, disks, searches, dupes, indexed     # noqa: E402
from engine import Query                                     # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

def pulado(msg):
    print("--    (pulado) " + msg)


# =====================================================================
# 1) CANCELAR com o motor CALADO — medido: cancel aos 0,5 s, search() de volta
#    aos 20,0 s (caminho serial, nome e conteúdo; e o booleano inteiro).
# =====================================================================
_tmp = tempfile.mkdtemp(prefix="sfs_rev_")
_surdo = os.path.join(_tmp, "motor_surdo.sh")
with open(_surdo, "w") as f:
    # `exec`: processo ÚNICO, como o fd/rg de verdade (um filho `sleep` herdaria
    # o pipe e seguraria o EOF — artefato de script, não do programa)
    f.write('#!/bin/sh\ncase "$1" in --help) echo "--show-errors"; exit 0;; esac\nexec sleep 30\n')
os.chmod(_surdo, 0o755)
_disco = os.path.join(_tmp, "disco"); os.makedirs(_disco)

def _cronometra(fn):
    flag = {"v": False}
    threading.Timer(0.4, lambda: flag.__setitem__("v", True)).start()
    t0 = time.time()
    st = {}
    fn(lambda: flag["v"], st)
    return time.time() - t0, st

_rg, _fd = engine.RG, engine.FD
try:
    engine.FD = _surdo
    dt, st = _cronometra(lambda c, s: engine.search(
        Query(paths=[_disco], name_patterns=["*raro*"]), lambda m: None, c, stats=s))
    ok(dt < 5, f"cancelar solta a busca por NOME com o fd calado, caminho serial ({dt:.1f}s; era 20s+)")
    grave, _ = engine.resumo_incompleto(st)
    ok(not grave, "cancelar NÃO vira 'search engine failed' (o motor morreu porque NÓS o matamos)")

    engine.FD, engine.RG = _fd, _surdo
    dt, st = _cronometra(lambda c, s: engine.search(
        Query(paths=[_disco], content="raro"), lambda m: None, c, stats=s))
    ok(dt < 5, f"cancelar solta a busca por CONTEÚDO com o rg calado ({dt:.1f}s)")
    ok(not engine.resumo_incompleto(st)[0], "…e sem falso 'engine failed'")

    dt, st = _cronometra(lambda c, s: boolean.search_boolean(
        Query(paths=[_disco]), "raro AND outro", lambda m: None, c, stats=s))
    ok(dt < 5, f"cancelar solta o BOOLEANO com o rg calado ({dt:.1f}s)")
    dt, st = _cronometra(lambda c, s: boolean.search_boolean(
        Query(paths=[_disco]), "NOT raro", lambda m: None, c, stats=s))
    ok(dt < 5, f"cancelar solta o universo do NOT ({dt:.1f}s)")
finally:
    engine.RG, engine.FD = _rg, _fd

# _reap: kill (-9) depois de terminate ignorado, por iniciativa NOSSA, não é falha
_teimoso = os.path.join(_tmp, "teimoso.py")
with open(_teimoso, "w") as f:
    f.write("import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('pronto', flush=True)\ntime.sleep(30)\n")
p = subprocess.Popen([sys.executable, _teimoso], stdout=subprocess.PIPE)
p.stdout.readline()                        # SIGTERM já está ignorado
errf = tempfile.TemporaryFile(mode="w+")
st = {}
engine._reap(p, errf, st)
ok(p.returncode == -9 and not st.get("incompleto"),
   f"processo que ignora SIGTERM leva kill e NÃO entra no funil como falha (rc={p.returncode})")
# …mas um motor que morreu SOZINHO com código estranho continua sendo falha
p = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(7)"]); p.wait()
errf = tempfile.TemporaryFile(mode="w+"); st = {}
engine._reap(p, errf, st)
ok(any(e["motivo"] == "engine_failed" for e in st.get("incompleto", [])),
   "motor que saiu sozinho com rc=7 continua 'engine_failed' (a guarda não afrouxou)")


# =====================================================================
# 2) rg --json com {"bytes": …}: nome não-UTF-8 era DESCARTADO mudo; linha
#    cp1252 aparecia VAZIA. No booleano o caminho mutilado ainda virava
#    `engine_failed` grave (rg rc=2, "No such file") — exit 2 por um nome.
# =====================================================================
_enc = os.path.join(_tmp, "enc"); os.makedirs(_enc)
_nome_cru = os.path.join(os.fsencode(_enc), b"laudo_m\xe9dico.txt")
open(_nome_cru, "wb").write(b"paciente com laudo\n")
open(os.path.join(_enc, "antigo.txt"), "wb").write(
    "laudo do paciente João — avaliação\n".encode("cp1252"))
open(os.path.join(_enc, "normal.txt"), "w").write("laudo normal\n")
_esperado_nome = os.fsdecode(_nome_cru)
_esperado_linha = "laudo do paciente João — avaliação"

def _simples():
    res, st = [], {}
    engine.search(Query(paths=[_enc], content="laudo"), res.append, stats=st)
    return {m.path: m for m in res}, st

def _bool():
    res, st = [], {}
    boolean.search_boolean(Query(paths=[_enc]), "laudo AND paciente", res.append, stats=st)
    return {m.path: m for m in res}, st

def _confere(rotulo):
    r, st = _simples()
    ok(_esperado_nome in r, f"{rotulo}: conteúdo acha arquivo de NOME não-UTF-8")
    ok(r.get(os.path.join(_enc, "antigo.txt")) is not None
       and r[os.path.join(_enc, "antigo.txt")].lines == [(1, _esperado_linha)],
       f"{rotulo}: linha cp1252 sai LEGÍVEL, não vazia")
    r, st = _bool()
    ok(set(r) == {_esperado_nome, os.path.join(_enc, "antigo.txt")},
       f"{rotulo}: booleano devolve os 2 arquivos (nome cru incluído): {sorted(map(repr, r))}")
    ok(not engine.resumo_incompleto(st)[0],
       f"{rotulo}: booleano sem 'engine_failed' fantasma por causa do nome")
    ok(r.get(os.path.join(_enc, "antigo.txt")) is not None
       and r[os.path.join(_enc, "antigo.txt")].lines == [(1, _esperado_linha)],
       f"{rotulo}: booleano também exibe a linha cp1252 legível")

if engine.RG:
    _confere("rg")
else:
    pulado("sem rg: caminho rg do bloco 2")
_rg, _fd = engine.RG, engine.FD
try:
    engine.RG = engine.FD = None
    _confere("fallback Python")          # os dois lados exibem o MESMO texto
finally:
    engine.RG, engine.FD = _rg, _fd

ok(engine.texto_legivel("aç".encode("utf-8") + "ão".encode("cp1252")) == "ação",
   "texto_legivel: linha MISTA mantém o trecho UTF-8 e resgata só o que não é")
ok(engine._rg_caminho({"text": "/a"}) == "/a" and engine._rg_caminho(None) is None
   and engine._rg_caminho({"bytes": "!!!não-base64"}) in (None, ""),
   "_rg_caminho: text, ausente e base64 inválido não levantam")

# nome com '\n' no booleano (antes rachava em 2 'linhas' de caminho)
_nl = os.path.join(_tmp, "nl"); os.makedirs(_nl)
open(os.path.join(_nl, "duas\nlinhas.txt"), "w").write("alfa beta\n")
if engine.RG:
    res = []
    boolean.search_boolean(Query(paths=[_nl]), "alfa AND beta", res.append)
    ok([m.path for m in res] == [os.path.join(_nl, "duas\nlinhas.txt")],
       "booleano: nome de arquivo com '\\n' sobrevive (saída do rg -l é NUL-delimitada)")


shutil.rmtree(_tmp, ignore_errors=True)
print()
if falhas:
    print(f"{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("todos os testes passaram")
