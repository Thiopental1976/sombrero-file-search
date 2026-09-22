#!/usr/bin/env python3
"""Caracteres INVISÍVEIS no nome de arquivo (22/09/2026).

Medido no NAS TrueNAS: "fatura_\\u202Etxt.exe" aparecia na tela como
"fatura_exe.txt" — o RLO (U+202E) inverte a direção do resto do texto, o truque
clássico para disfarçar executável — e "zero\\u200Bwidth.txt" não era achado por
"zerowidth". Decisões do Rodrigo: MOSTRAR o invisível como marcador visível
(⟦RLO⟧, itálico + tooltip) e a BUSCA ignorá-lo ao comparar. ZWJ/ZWNJ ficam
intocados (emoji compostos; escrita persa/hindi).
Rode:  python3 tests/test_invisiveis_2026_09_22.py
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine                                                 # noqa: E402
from engine import Query                                      # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

RLO, ZWSP, ZWJ, ZWNJ = "\u202e", "\u200b", "\u200d", "\u200c"
NOMES = {
    "rlo":    f"fatura_{RLO}txt.exe",
    "zwsp":   f"zero{ZWSP}width.txt",
    "bom":    "\ufeffcom_bom_no_inicio.txt",
    "shy":    "hifen\u00adsuave.txt",
    "emoji":  f"medico_👨{ZWJ}⚕️.txt",          # ZWJ legítimo: fica intocado
    "persa":  f"می{ZWNJ}خواهم.txt",              # ZWNJ legítimo (persa): intocado
    "normal": "zerowidth_normal.txt",
}

# ------------------------------------------------------------- exibição
ok(engine.nome_exibivel(NOMES["rlo"]) == "fatura_⟦RLO⟧txt.exe", "RLO vira marcador ⟦RLO⟧ no lugar exato")
ok(engine.nome_exibivel(NOMES["zwsp"]) == "zero⟦ZWSP⟧width.txt", "ZWSP vira ⟦ZWSP⟧")
ok(engine.nome_exibivel(NOMES["bom"]).startswith("⟦BOM⟧"), "BOM no início vira ⟦BOM⟧")
ok(engine.nome_exibivel(NOMES["emoji"]) == NOMES["emoji"], "ZWJ do emoji composto fica intocado")
ok(engine.nome_exibivel(NOMES["persa"]) == NOMES["persa"], "ZWNJ do persa fica intocado")
ok(not engine.tem_invisivel(NOMES["emoji"]) and not engine.tem_invisivel(NOMES["persa"]),
   "emoji e persa não são 'invisível perigoso'")
ok(engine.nome_para_busca(NOMES["rlo"]) == "fatura_txt.exe", "para comparar: sem o invisível")
sh = engine.caminho_para_shell("/x/" + NOMES["rlo"])
ok(sh == "$'/x/fatura_\\u202etxt.exe'" and RLO not in sh,
   f"copiar caminho: forma do terminal sem o RLO cru ({sh})")

T = tempfile.mkdtemp(prefix="sfs_invis_")
try:
    por_nome = {}
    for rot, n in NOMES.items():
        open(os.path.join(T, n), "w").close()
        por_nome[n] = rot
    r = subprocess.run(["bash", "-c", "test -e " + engine.caminho_para_shell(os.path.join(T, NOMES["rlo"]))])
    ok(r.returncode == 0, "a forma do terminal acha o arquivo com RLO no bash")

    def busca(globs, python=False):
        salvos = (engine.RG, engine.RGA, engine.FD)
        if python:
            engine.RG = engine.RGA = engine.FD = ""
        try:
            res = []
            engine.search(Query(paths=[T], name_patterns=list(globs)), res.append)
            return {por_nome.get(os.path.basename(m.path), "?") for m in res}
        finally:
            engine.RG, engine.RGA, engine.FD = salvos

    g = engine.as_name_glob
    casos = [([g("zerowidth")], {"zwsp", "normal"}, "'zerowidth' acha o nome com ZWSP"),
             ([g("fatura_txt")], {"rlo"}, "'fatura_txt' acha o nome com RLO"),
             ([g("com_bom")], {"bom"}, "BOM no início não impede"),
             ([g("hifensuave")], {"shy"}, "hífen suave não impede"),
             ([g("medico_👨")], {"emoji"}, "emoji com ZWJ segue achável"),
             (["*.txt", "*.exe"], set(NOMES), "globs comuns acham todos")]
    for globs, esp, oque in casos:
        a, b = busca(globs), busca(globs, python=True)
        ok(a == esp, f"[fd    ] {oque} ({sorted(a)})")
        ok(b == esp, f"[python] {oque} ({sorted(b)})")

    # GUI: itálico, tooltip e filtro
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
    except ImportError:
        print("--    (pulado) GUI: sem PySide6")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import app, i18n
        i18n.set_lang("en")
        qa = QApplication.instance() or QApplication([])
        model = app.ResultModel()
        model.rows = [engine.Match(os.path.join(T, NOMES[k]), 0, 0.0) for k in ("rlo", "emoji")]
        i0 = model.index(0, 0)
        ok(model.data(i0, Qt.DisplayRole) == "fatura_⟦RLO⟧txt.exe", "tabela mostra o marcador")
        f = model.data(i0, Qt.FontRole)
        ok(f is not None and f.italic(), "nome com invisível em itálico")
        ok("RLO" in model.data(i0, Qt.ToolTipRole) and "disguise" in model.data(i0, Qt.ToolTipRole),
           "tooltip explica o truque")
        ok(model.data(model.index(1, 0), Qt.FontRole) is None, "emoji com ZWJ não fica em itálico")
        proxy = app.ResultFilterProxy(); proxy.setSourceModel(model)
        proxy.set_filter_text("fatura_txt")
        ok(proxy.filterAcceptsRow(0, None), "filtro 'fatura_txt' acha o nome com RLO")
        i18n.set_lang(None)
finally:
    shutil.rmtree(T, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]
    sys.stdout.flush(); os._exit(1)
print("\ntodos os testes passaram")
sys.stdout.flush(); os._exit(0)
