#!/usr/bin/env python3
"""Fechar a janela com a consulta de atualização pendurada (22/10/2026, VM Windows).

Na VM o app caiu ao fechar ("QThread: Destroyed while thread '' is still
running" no queda.log). O timeout de 8 s do urlopen não cobre o DNS; a janela
esperava a QThread por 9 s, desistia, e o Qt abortava o processo ao destruí-la.
Reproduzido no Linux: 9,3 s de janela congelada e saída 134 (SIGABRT).

O que este teste garante:
  1. com a consulta presa, fechar é imediato e o processo sai limpo (código 0);
  2. uma consulta normal ainda entrega o resultado NA THREAD DA GUI (a consulta
     roda numa thread daemon; o sinal tem de chegar enfileirado).

Rode (precisa do PySide6 — use o Python do venv do app):
    ~/.local/share/sombrero-file-search/venv/bin/python tests/test_fechar_durante_consulta_2026_10_22.py
"""
from __future__ import annotations
import os, subprocess, sys, tempfile, threading, time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

# ------------------------------------------------- 1. fechar com a consulta presa
FILHO = r'''
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(); os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = os.environ["XDG_CACHE_HOME"]; os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import app as A
A.updates.check = lambda cfg, force=False: time.sleep(30)     # rede que não responde
qa = QApplication([])
w = A.MainWindow(); w.cfg.setdefault("updates", {})["auto"] = False; w.show()
w.check_updates(force=True)
QTimer.singleShot(300, w.close)
QTimer.singleShot(400, qa.quit)
qa.exec()
'''
t0 = time.time()
r = subprocess.run([sys.executable, "-c", FILHO, LFS], capture_output=True, text=True, timeout=120)
dt = time.time() - t0
ok(r.returncode == 0, f"consulta presa + fechar: processo sai limpo (código {r.returncode})")
ok("Destroyed while thread" not in r.stderr, "sem 'QThread: Destroyed while thread … is still running'")
ok(dt < 8, f"fechar não espera a rede ({dt:.1f}s no total, com o arranque)")

# ------------------------------------------------- 2. o resultado chega na GUI
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sfs-test-fechar-")
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="sfs-test-fechar-")
sys.path.insert(0, LFS)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import app as A

A.updates.check = lambda cfg, force=False: (time.sleep(0.2), None)[1]   # "já está na última"
qa = QApplication([])
w = A.MainWindow()
w.cfg.setdefault("updates", {})["auto"] = False
onde = []
w._on_update_checked = lambda rel, st, dialog=None: onde.append(threading.current_thread())
w.check_updates(force=True)
fim = time.time() + 10
while not onde and time.time() < fim:
    qa.processEvents(); time.sleep(0.02)
ok(len(onde) == 1, "a consulta normal entrega o resultado")
ok(bool(onde) and onde[0] is threading.main_thread(), "o resultado é tratado na thread da GUI")

QTimer.singleShot(0, w.close)
for _ in range(20):
    qa.processEvents(); time.sleep(0.01)
print()
if falhas:
    print(f"{len(falhas)} falha(s)")
    sys.exit(1)
print("tudo ok")
