#!/usr/bin/env python3
"""A prévia recolhida tem que voltar quando a janela volta a ter espaço (28/10/2026).

Rodrigo, janela de 1108×1038 no ultrawide: a prévia sumiu e não voltava. Causa:
o painel recolhido só reaparecia quando o tamanho PREFERIDO coubesse inteiro, e o
preferido (cfg pv_w) tinha ficado em 1573 px de quando a janela ocupava o
ultrawide. Em qualquer janela menor que ~2000 px ela nunca mais aparecia.

Contratos:
  1. com pv_w enorme, encolher até recolher e voltar a 1108 px → prévia visível;
  2. a histerese continua: 1 px acima do ponto de recolher não reabre.

Rode (com o python que tem PySide6):
    python3 tests/test_previa_recolhida_2026_10_28.py
"""
from __future__ import annotations
import json, os, sys, tempfile, time

TMP = tempfile.mkdtemp(prefix="sfs_pv_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "cfg")
os.environ["XDG_CACHE_HOME"] = os.path.join(TMP, "cache")
os.environ["XDG_RUNTIME_DIR"] = TMP
# tela offscreen larga o bastante p/ a janela de 1108 px do caso real
CFGQPA = os.path.join(TMP, "tela.json")
json.dump({"screens": [{"name": "t", "x": 0, "y": 0, "width": 2400, "height": 1400,
                        "logicalDpi": 96, "logicalWidth": 2400, "logicalHeight": 1400}]},
          open(CFGQPA, "w"))
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=" + CFGQPA
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
w = A.MainWindow()
w.cfg.setdefault("updates", {})["auto"] = False
w.cfg["pv_w"] = 1573                       # o valor real gravado no ultrawide
w.show(); gira(0.3)
w.resize(1500, 1000); gira(0.4)            # largo: modo "direita"
ok(w._pv_modo == "direita", "janela larga: prévia à direita")
ok(w.split_res.sizes()[1] > 0, "janela larga: prévia visível (%s)" % w.split_res.sizes())

w.resize(700, 600); gira(0.4)              # estreita (ainda 'direita' pela histerese do modo)
w._reparte_resultados(); gira(0.1)
recolhe = w.split_res.sizes()
ok(recolhe[1] == 0 or w._pv_modo == "baixo", "estreita: painel recolhe (%s, %s)" % (recolhe, w._pv_modo))

w.resize(1108, 1038); gira(0.4)            # o caso dele
w._reparte_resultados(); gira(0.1)
s = w.split_res.sizes()
ok(s[1] >= w._pv_min(), "1108×1038 com pv_w=1573: prévia VOLTA (%s, modo %s)" % (s, w._pv_modo))
ok(w._pv_modo == "direita", "quase quadrada (1,07): prévia À DIREITA da lista, não embaixo")
ok(s[0] >= 0.45 * sum(s), "pv_w do ultrawide não espreme a lista: painel ≤ 55 %% (%s)" % s)
w.resize(1108, 1024); gira(0.3)            # a 2ª captura dele: 1,08
ok(w._pv_modo == "direita" and w.split_res.sizes()[1] > 0, "1108×1024: à direita e visível (%s)" % w.split_res.sizes())

# histerese: recolhido, com só +10 px de folga sobre o mínimo do painel, continua
# recolhido; com +60 px, reabre. (Piso da tabela ajustado só nesta janela de teste.)
if w._pv_modo == "direita":
    tot = sum(w.split_res.sizes())
    w.split_res.setSizes([tot, 0]); gira(0.05)
    w.RES_LARG_MIN = tot - w._pv_min() - 10
    w._reparte_resultados(); gira(0.05)
    ok(w.split_res.sizes()[1] == 0, "histerese: +10 px de folga não reabre (%s)" % w.split_res.sizes())
    w.RES_LARG_MIN = tot - w._pv_min() - 60
    w._reparte_resultados(); gira(0.05)
    ok(w.split_res.sizes()[1] > 0, "folga de +60 px reabre (%s)" % w.split_res.sizes())
w.RES_LARG_MIN = A.MainWindow.RES_LARG_MIN
w.resize(600, 1100); gira(0.4)             # retrato de verdade: vai para baixo
ok(w._pv_modo == "baixo", "janela em pé (0,55): prévia embaixo")
w.close()

print()
print("FALHAS: %d" % len(falhas) if falhas else "tudo ok")
sys.exit(1 if falhas else 0)
