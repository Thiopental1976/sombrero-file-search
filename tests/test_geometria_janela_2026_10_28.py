#!/usr/bin/env python3
"""A janela volta onde estava (28/10/2026).

O SFS nunca guardou posição nem tamanho: toda abertura nascia no canto, no
tamanho padrão. O Rodrigo percebeu por acaso, abrindo e fechando a janela
muitas vezes seguidas. Contrato: fechar grava (cfg["window_geometry"]) e a
próxima janela nasce com a mesma posição e tamanho (±4 px de moldura).

Rode (com o python que tem PySide6):
    python3 tests/test_geometria_janela_2026_10_28.py
"""
from __future__ import annotations
import os, sys, tempfile, time

TMP = tempfile.mkdtemp(prefix="sfs_geo_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "cfg")
os.environ["XDG_CACHE_HOME"] = os.path.join(TMP, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

from PySide6.QtWidgets import QApplication
qa = QApplication([])
def gira(seg):
    fim = time.time() + seg
    while time.time() < fim:
        qa.processEvents(); time.sleep(0.01)

import app as A
w = A.MainWindow(); w.cfg.setdefault("updates", {})["auto"] = False
w.show(); gira(0.2)
w.setGeometry(90, 110, 650, 500); gira(0.2)   # cabe na tela offscreen (800×800)
antes = w.geometry()
w.close(); gira(0.2)
ok(bool(A.load_cfg().get("window_geometry")), "fechar grava a geometria no config")
w2 = A.MainWindow(); w2.show(); gira(0.3)
g = w2.geometry()
ok(abs(g.x() - antes.x()) <= 4 and abs(g.y() - antes.y()) <= 4 and g.size() == antes.size(),
   "reabre com a mesma geometria (%s → %s)" % (antes, g))
w2.close()

print()
print("FALHAS: %d" % len(falhas) if falhas else "tudo ok")
sys.exit(1 if falhas else 0)
