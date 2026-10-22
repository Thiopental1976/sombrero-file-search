#!/usr/bin/env python3
"""Tela baixa e o "×" das abas (22/10/2026, VM Windows 10 a 1024x768).

O que se viu na VM, e se mediu igual no Linux (offscreen):
  - numa janela de ~705 px de altura (tela de 768 com barra de tarefas) a tabela
    de resultados ficava com ZERO linhas visíveis: o divisor dava o espaço ao
    painel do trecho (1024x705 → tabela 0 px, trecho 103 px; 1366x705 → 1 px);
  - o botão nativo de fechar aba saía um quadrado azul no Windows (laranja no
    Linux), fora do tema.

O que este teste garante:
  1. o trecho NUNCA segura espaço enquanto a tabela está abaixo do piso: ou a
     tabela tem RES_LINHAS_MIN linhas, ou o trecho está recolhido;
  2. quando a janela volta a crescer, o trecho reaparece;
  3. cada aba de busca tem o "×" do tema (QToolButton#tabclose), e ele fecha
     a aba certa;
  4. a tabela não quebra linha: com a quebra (padrão do Qt) a pasta
     C:\\Windows\\servicing\\LCU\\Package_for_RollupFix~… saía só "C:..." (o "~"
     abre ponto de quebra depois do "C:");
  5. trocar o tema redesenha a narrativa (as cores vão no HTML: no claro, o
     nome do disco ficava com o texto claro do escuro, quase invisível);
  6. terminada a busca, o tempo do painel para: redesenhar (trocar de aba ou
     de tema) não o faz continuar correndo.

Rode (precisa do PySide6 — use o Python do venv do app):
    ~/.local/share/sombrero-file-search/venv/bin/python tests/test_altura_baixa_2026_10_22.py
"""
from __future__ import annotations
import os, sys, tempfile, time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)
# tela offscreen de 1920x1080 (a padrão tem 800 px e espreme a largura). Caminho
# RELATIVO: o ":" do "C:" no Windows quebraria a sintaxe "offscreen:configfile=…"
os.chdir(tempfile.mkdtemp(prefix="sfs-test-altura-"))
with open("tela.json", "w") as f:
    f.write('{"screens":[{"name":"t","x":0,"y":0,"width":1920,"height":1080,"logicalDpi":96}]}')
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=tela.json"
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sfs-test-altura-")   # config descartável
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="sfs-test-altura-")

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QTabBar, QToolButton
import app as A

qa = QApplication([])

def assenta():
    for _ in range(30):
        qa.processEvents(); time.sleep(0.01)

w = A.MainWindow()
w.cfg.setdefault("updates", {})["auto"] = False   # sem consulta ao GitHub no teste
w.show()
# o painel de narrativa aparece em toda busca; com ele a parte de cima fica no máximo
# (pela função de verdade: é ela que dá a altura do painel pelo número de linhas)
_t = w.tabs.currentWidget()
_t.roots = {"C:\\": {"name": "Windows (C:)", "klass": "ssd", "state": "done", "found": 9,
                      "reason": "", "snap": False}}
_t.root_order = ["C:\\"]
w._render_narrative(_t)

def estado():
    t = w.tabs.currentWidget().table
    linhas = t.viewport().height() // t.verticalHeader().defaultSectionSize()
    return linhas, w.split_res.sizes()

# ---------------------------------------------------------------- 1. tela baixa
# piso medido com a correção (antes: 0 nos dois); abaixo disso quem manda é a
# parte de cima (cabeçalho, campos, chips, narrativa), não o divisor
for (lw, lh, piso) in [(1024, 705, 4), (1366, 705, 5)]:
    w._render_narrative(_t)
    w.resize(lw, lh); assenta()
    linhas, sizes = estado()
    ok(linhas >= w.RES_LINHAS_MIN or sizes[1] == 0,
       f"{lw}x{lh}: tabela {linhas} linha(s), trecho {sizes[1]} px — o trecho cede antes")
    ok(linhas >= piso, f"{lw}x{lh}: tabela com pelo menos {piso} linhas ({linhas})")

# ---------------------------------------------------------------- 2. volta a crescer
w.narr.setVisible(False)
w.resize(1920, 1040); assenta()
linhas, sizes = estado()
ok(sizes[1] > 0, f"janela alta de novo: o trecho reaparece ({sizes[1]} px)")
ok(linhas >= w.RES_LINHAS_MIN, f"janela alta: tabela com {linhas} linhas")

# ---------------------------------------------------------------- 3. o "×" do tema
w.new_tab(); w.new_tab(); assenta()
bar = w.tabs.tabBar()
botoes = [bar.tabButton(i, QTabBar.RightSide) for i in range(w.tabs.count())]
ok(all(isinstance(b, QToolButton) and b.objectName() == "tabclose" for b in botoes),
   f"todas as {len(botoes)} abas têm o × do tema (QToolButton#tabclose)")
alvo = w.tabs.widget(1)
botoes[1].click(); assenta()
ok(w.tabs.count() == 2 and w.tabs.indexOf(alvo) == -1, "o × fecha a aba dele, não outra")

# ---------------------------------------------------------------- 4. linha única
ok(all(not w.tabs.widget(i).table.wordWrap() for i in range(w.tabs.count())),
   "tabela de resultados sem quebra de linha (caminho com ~ não vira \"C:...\")")

# ---------------------------------------------------------------- 5. tema
_a = w.tab
_a.roots = dict(_t.roots); _a.root_order = list(_t.root_order)
_a.t0, _a.t1 = time.time() - 100, time.time() - 93      # busca de 7 s, há 93 s
for tema in ("light", "dark"):
    w.apply_theme(tema)
    cor = A.THEMES[tema]["txt"]
    ok(f"color:{cor}" in w.narr_body.text(), f"tema {tema}: a narrativa usa o texto do tema ({cor})")

# ---------------------------------------------------------------- 6. tempo congelado
ok(w.narr_head.text().endswith("· 7s"), f"busca terminada: o painel mostra 7s, não 100s ({w.narr_head.text()!r})")

QTimer.singleShot(0, w.close); assenta()          # fechar para as threads da janela
if w._upd_worker:
    w._upd_worker.wait(10000)
print()
if falhas:
    print(f"{len(falhas)} falha(s)")
    sys.exit(1)
print("tudo ok")
