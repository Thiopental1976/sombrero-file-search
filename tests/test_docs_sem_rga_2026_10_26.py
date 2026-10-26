#!/usr/bin/env python3
"""Documentos sem rga: a perda vai ao funil (26/10/2026, Fable §2.7).

`documents` sem rga virava rg puro em silêncio no motor: só a CLI imprimia um
aviso dela. Na GUI, uma busca salva com "documentos" marcava a caixa mesmo
desabilitada; a busca rodava em texto puro e terminava com ✔.

Contratos presos aqui:
  1. busca de conteúdo com documents=True e sem rga: uma entrada
     component_missing em "rga", não-grave (o texto plano foi buscado);
  2. o booleano anota igual;
  3. busca só por nome não anota (documentos não mudam nada nela);
  4. com rga presente, nada;
  5. a GUI não marca a caixa "documentos" sem rga ao aplicar uma busca salva.

Rode:
    QT_QPA_PLATFORM=offscreen python3 tests/test_docs_sem_rga_2026_10_26.py
"""
from __future__ import annotations
import os, shutil, sys, tempfile

os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sfs-test-docs-")   # config descartável
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="sfs-test-docs-")
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, boolean
from engine import Query

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

def motivos(stats):
    return [e for e in stats.get("incompleto") or []
            if e["motivo"] == "component_missing" and e["onde"] == "rga"]

base = tempfile.mkdtemp(prefix="sfs_docs_sem_rga_")
with open(os.path.join(base, "a.txt"), "w") as f:
    f.write("agulha\n")
salvo = engine.RGA
try:
    engine.RGA = None
    st = {}
    engine.search(Query(paths=[base], content="agulha", documents=True), lambda m: None, stats=st)
    e = motivos(st)
    ok(len(e) == 1, f"conteúdo + documentos sem rga: uma nota ({e})")
    ok(e and not e[0].get("grave") and "component_missing" not in engine.MOTIVOS_GRAVES,
       "a nota é não-grave")
    ok(e and "plain text" in engine.texto_detalhe(e[0]), "o detalhe diz que virou texto puro")
    ok(len([x for x in st["incompleto"] if x["motivo"] == "component_missing"]) == 1,
       "rg presente: só o rga é apontado")

    st = {}
    boolean.search_boolean(Query(paths=[base], documents=True), "agulha", lambda m: None, stats=st)
    ok(len(motivos(st)) == 1, "booleano: uma nota")

    st = {}
    engine.search(Query(paths=[base], name_patterns=["*.txt"], documents=True), lambda m: None, stats=st)
    ok(not motivos(st), "só por nome: sem nota")

    if salvo:
        engine.RGA = salvo
        st = {}
        engine.search(Query(paths=[base], content="agulha", documents=True), lambda m: None, stats=st)
        ok(not motivos(st), "com rga: sem nota")

    # 5. GUI
    engine.RGA = None
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import app as gui
    qa = QApplication.instance() or QApplication([])
    w = gui.MainWindow()
    w.cfg.setdefault("updates", {})["auto"] = False
    w.apply_form(dict(w.form_state(), documents=True))
    ok(not w.ck_doc.isChecked(), "GUI: busca salva com documentos não marca a caixa sem rga")
    w.close()
finally:
    engine.RGA = salvo
    shutil.rmtree(base, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
