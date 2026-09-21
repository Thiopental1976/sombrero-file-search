#!/usr/bin/env python3
"""Nome de arquivo NÃO-UTF-8 na GUI (21/09/2026, item 5 do parecer do Fable).

Medido antes: o Qt não desenha substituto solitário — "relat\\xf3rio_\\xc7\\xc3O.txt"
aparecia "relatrio_O.txt". E não era só cosmético: Abrir, Abrir pasta (último
recurso) e o player usavam QUrl.fromLocalFile, que manda para o sistema a URL de
um arquivo que NÃO EXISTE; "Copiar caminho" punha no clipboard um caminho sem as
letras. Decisões do Rodrigo: exibir LEGÍVEL (cp1252) em ITÁLICO + tooltip; copiar
caminho na forma do terminal ($'…\\xNN…').

Tudo em tempdir, GUI em offscreen. Rode:
    python3 tests/test_nome_nao_utf8_2026_09_21.py
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine                                                # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

T = tempfile.mkdtemp(prefix="sfs_nome8_")
try:
    tb = os.fsencode(T)
    nomes_b = [b"laudo_m\xe9dico.txt", b"relat\xf3rio_\xc7\xc3O.txt",
               b"d'aspa \\ m\xe9d\nx.txt"]                 # o pior caso: ' \ \n e byte cru
    for nb in nomes_b:
        with open(os.path.join(tb, nb), "w") as f:
            f.write("x")
    normal = os.path.join(T, "normal_médico.txt")
    open(normal, "w").close()
    laudo = os.fsdecode(os.path.join(tb, nomes_b[0]))
    relat = os.fsdecode(os.path.join(tb, nomes_b[1]))
    pior = os.fsdecode(os.path.join(tb, nomes_b[2]))

    # --------------------------------------------------------- funções puras
    ok(engine.tem_bytes_crus(laudo) and not engine.tem_bytes_crus(normal),
       "tem_bytes_crus distingue byte cru de UTF-8 legítimo")
    ok(engine.nome_exibivel(os.path.basename(laudo)) == "laudo_médico.txt",
       "nome_exibivel: laudo_m\\xe9dico -> laudo_médico")
    ok(engine.nome_exibivel(os.path.basename(relat)) == "relatório_ÇÃO.txt",
       "nome_exibivel: nenhuma letra some (relatório_ÇÃO)")
    ok(engine.nome_exibivel(normal) == normal and engine.caminho_para_shell(normal) == normal,
       "caminho normal passa INTACTO nas duas funções")
    for p in (laudo, relat, pior):
        sh = engine.caminho_para_shell(p)
        r = subprocess.run(["bash", "-c", "test -e " + sh], timeout=10)
        ok(r.returncode == 0, f"forma do terminal acha o arquivo no bash: {sh[-34:]!r}")

    # --------------------------------------------------------- GUI (offscreen)
    try:
        from PySide6.QtWidgets import QApplication, QTreeWidgetItem
        from PySide6.QtCore import Qt
    except ImportError:
        print("--    (pulado) GUI: sem PySide6")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import app
        from urllib.parse import unquote_to_bytes
        qa = QApplication.instance() or QApplication([])

        def url_existe(u):
            b = unquote_to_bytes(bytes(u.toEncoded()).decode("ascii")[len("file://"):])
            return os.path.exists(b)
        ok(url_existe(app.url_local(laudo)) and url_existe(app.url_local(pior)),
           "url_local (Abrir/Abrir pasta/player) chega no arquivo CERTO")
        md = app.build_paths_mime([laudo])
        r = subprocess.run(["bash", "-c", "test -e " + md.text()], timeout=10)
        ok(r.returncode == 0 and all(url_existe(u) for u in md.urls()),
           "Ctrl+C/arrastar: texto na forma do terminal + URL certa")

        model = app.ResultModel()
        ms = [engine.Match(laudo, 1, 0.0), engine.Match(normal, 0, 0.0)]
        model.rows = ms
        i0, i1 = model.index(0, 0), model.index(0, 1)
        ok(model.data(i0, Qt.DisplayRole) == "laudo_médico.txt",
           f"tabela mostra o nome legível ({model.data(i0, Qt.DisplayRole)!r})")
        f = model.data(i0, Qt.FontRole)
        ok(f is not None and f.italic(), "nome em codificação antiga sai em ITÁLICO")
        ok(model.data(i1, Qt.FontRole) is None, "pasta UTF-8 normal não fica em itálico")
        ok(model.data(model.index(1, 0), Qt.FontRole) is None,
           "nome UTF-8 normal (com acento) não fica em itálico")
        tip = model.data(i0, Qt.ToolTipRole)
        ok("laudo_médico" in tip and "Windows-1252" in tip, "tooltip explica a codificação")

        proxy = app.ResultFilterProxy()
        proxy.setSourceModel(model)
        proxy.set_filter_text("médico")
        ok(proxy.filterAcceptsRow(0, None), "filtro 'médico' acha o nome em cp1252")

        it = QTreeWidgetItem([engine.nome_exibivel(laudo)])
        app._marca_nome_antigo(it, laudo)
        ok(it.font(0).italic() and "Windows-1252" in it.toolTip(0),
           "duplicatas: mesmo sinal (itálico + tooltip)")

        win = app.MainWindow()
        try:
            win.tab.model.beginResetModel(); win.tab.model.rows = [ms[0]]
            win.tab.model.endResetModel()
            win.tab.table.selectRow(0)
            win.copy_paths()
            txt = app.QGuiApplication.clipboard().text()
            r = subprocess.run(["bash", "-c", "test -e " + txt], timeout=10)
            ok(r.returncode == 0, f"'Copiar caminho' cola no terminal e acha o arquivo ({txt[-28:]!r})")
        finally:
            win.close()
finally:
    shutil.rmtree(T, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]
    sys.stdout.flush(); os._exit(1)
print("\ntodos os testes passaram")
sys.stdout.flush(); os._exit(0)          # os._exit: QThread viva no fim não vira core dump
