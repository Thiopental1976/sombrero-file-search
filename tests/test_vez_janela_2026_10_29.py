#!/usr/bin/env python3
"""A vez do disco na JANELA (desenho do Fable 29/10/2026, P4).

Contrato 9: 2 abas no mesmo HD partem as duas na hora (nada de "Queued"), a 2ª
mostra o disco esperando a 1ª (narrativa e status), e as duas terminam.
"""
from __future__ import annotations
import os, sys, tempfile, time

TMP = tempfile.mkdtemp(prefix="vez_gui_")
for k in ("CONFIG", "CACHE", "DATA"):
    os.environ["XDG_%s_HOME" % k] = os.path.join(TMP, k.lower())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lfs"))

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

import engine, vez as V
import disks as D

raiz = os.path.realpath(os.path.join(TMP, "acervo")); os.makedirs(raiz)
DISCO = frozenset({"sdq"})

# 9. janela: duas abas no mesmo HD
DUR = 1.0
def walker(q, stats=None, cancel=None, progresso=None):
    for r in q.paths:
        fim = time.time() + DUR
        while time.time() < fim and not (cancel and cancel()):
            time.sleep(0.01)
        yield engine.Match(path=os.path.join(r, "achado.txt"), size=1, mtime=0.0)
engine.FD = None
engine._iter_names_python = walker
engine._chave_de_disco = lambda p: ("disco", DISCO)
D.search_profile = lambda p, mounts=None: D.IOProfile(klass="rotational", mountpoint=raiz, fstype="ext4",
                                                      serialize=True, is_network=False, max_workers=None,
                                                      enumerate_default=True)
import app as A
from PySide6.QtWidgets import QApplication
qa = QApplication.instance() or QApplication([])
w = A.MainWindow(); w.cfg.setdefault("updates", {})["auto"] = False; w.show(); qa.processEvents()
V._reset()
abas = []
for nome in ("primeira", "segunda"):
    w.new_tab(focus=True); w.ed_path.setText(raiz); w.ed_name.setText(nome); w.start_search()
    abas.append(w.tab); qa.processEvents()
ok(all(a.searching for a in abas), "as 2 abas partem na hora")
ok(not any("Queued" in a.status_text or "fila" in a.status_text.lower() for a in abas), "nada de 'Queued'")
t0 = time.time(); visto = ""
while time.time() - t0 < 0.8:
    qa.processEvents(); time.sleep(0.05)
    w._heartbeat_tab(abas[1]); visto = visto or (abas[1].status_text if "waiting" in abas[1].status_text else "")
rec = abas[1].roots.get(raiz) or {}
ok(rec.get("state") == "waiting" and rec.get("por") == "primeira", "2ª aba: disco esperando a 1ª (%s)" % {k: rec.get(k) for k in ("state", "por")})
ok("1 disk(s) waiting for “primeira”" in visto, "status diz o disco esperando (%s)" % visto[-80:])
w.tabs.setCurrentWidget(abas[1]); qa.processEvents()
narr = w.narr_body.text()
ok("primeira" in narr and "waiting" in narr, "narrativa da 2ª aba mostra a espera")
while any(a.searching for a in abas) and time.time() - t0 < 10:
    qa.processEvents(); time.sleep(0.05)
for _ in range(5):                       # sinais enfileirados depois que a thread acabou
    qa.processEvents(); time.sleep(0.02)
ok(not any(a.searching for a in abas) and all(a.model.rowCount() == 1 for a in abas), "as duas terminam com o achado")
ok(abas[1].roots[raiz]["state"] == "done", "a 2ª varreu depois de esperar")
w._encerra_threads()
print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
