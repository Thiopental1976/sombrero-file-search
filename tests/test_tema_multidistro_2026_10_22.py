#!/usr/bin/env python3
"""Tema escuro de ponta a ponta + nada de emoji colorido (22/10/2026).

O que o Rodrigo viu no Bazzite:
  - a área de resultados da aba Duplicatas BRANCA no tema escuro: a árvore é
    QTreeWidget, e a folha de estilo só tinha regra para QTableView;
  - a janela de erro ilegível: o QLabel global pinta o texto claro, e a caixa
    de mensagem não tinha fundo próprio (branco do sistema);
  - um botão vazio ao lado de "Discos" e um buraco antes de "Buscar": eram os
    emojis 📂 e 🔍. Emoji colorido (plano U+1Fxxx) depende da fonte de emoji da
    distro, e o Qt do PySide6 não desenha a Noto Color Emoji COLRv1 do Fedora —
    sai em branco. As bolinhas 🟢🟠🟡 das duplicatas sumiam do mesmo jeito.

Regra da casa: o SFS é multidistro, SEMPRE. Então:
  1. nenhum caractere U+1F000+ em código de interface (comentário pode);
  2. desenhado de verdade (offscreen), no tema escuro, a árvore das duplicatas,
     as abas e uma caixa de mensagem têm fundo ESCURO; no claro, fundo claro.

Rode (precisa do PySide6 — use o Python do venv do app):
    ~/.local/share/sombrero-file-search/venv/bin/python tests/test_tema_multidistro_2026_10_22.py
"""
from __future__ import annotations
import glob, os, sys, tempfile, tokenize

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sfs-test-tema-")   # config descartável

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

# ---------------------------------------------------------------- 1. sem emoji colorido
achados = []
for fn in sorted(glob.glob(os.path.join(LFS, "*.py"))):
    with open(fn, "rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.STRING and any(ord(c) >= 0x1F000 for c in tok.string):
                achados.append(f"{os.path.basename(fn)}:{tok.start[0]}")
ok(not achados, "nenhum emoji colorido (U+1F000+) em string de código: " + ", ".join(achados[:8]))

# ---------------------------------------------------------------- 2. desenhado de verdade
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer
import app as A

qa = QApplication.instance() or QApplication([])

def luz(widget, janela=None) -> float:
    """Luminância média (0..1) de uma amostra do MEIO do widget desenhado.
    Com `janela`, mede o widget DENTRO da captura da janela: grab() de um filho
    sem fundo próprio sai branco e mentiria (foi o caso da barra de abas)."""
    if janela is None:
        img = widget.grab().toImage(); x0 = y0 = 0
        w, h = img.width(), img.height()
    else:
        img = janela.grab().toImage()
        o = widget.mapTo(janela, widget.rect().topLeft())
        x0, y0, w, h = o.x(), o.y(), widget.width(), widget.height()
    pts = [(x0 + int(w * fx), y0 + int(h * fy)) for fx in (0.3, 0.5, 0.7) for fy in (0.4, 0.6, 0.8)]
    tot = 0.0
    for x, y in pts:
        c = img.pixelColor(x, y)
        tot += (0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF())
    return tot / len(pts)

win = A.MainWindow(); win.resize(1100, 720); win.show()
qa.processEvents()

for tema, escuro in (("dark", True), ("light", False)):
    win.apply_theme(tema); qa.processEvents()
    win.workspace.setCurrentIndex(1); qa.processEvents()            # aba Duplicatas
    L = luz(win.dup_panel.tree.viewport())
    ok((L < 0.3) if escuro else (L > 0.7), f"[{tema}] árvore das duplicatas (luz {L:.2f})")
    L = luz(win.workspace.tabBar(), janela=win)
    ok((L < 0.35) if escuro else (L > 0.6), f"[{tema}] barra de abas (luz {L:.2f})")
    box = QMessageBox(QMessageBox.Warning, "SFS", "teste de legibilidade " * 4,
                      QMessageBox.Ok, win)
    box.show(); qa.processEvents()
    L = luz(box)
    ok((L < 0.3) if escuro else (L > 0.7), f"[{tema}] caixa de mensagem (luz {L:.2f})")
    box.close()

ok(win.dup_panel.btn_browse.text().strip() != "", "botão de procurar das duplicatas tem texto")
ok(not any(ord(c) >= 0x1F000 for c in win.workspace.tabText(0)), "aba Buscar sem emoji colorido")
QTimer.singleShot(0, win.close); qa.processEvents()

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("tudo ok")
