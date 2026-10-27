#!/usr/bin/env python3
"""Caractere de controle no nome, marcado na tela (27/10/2026, Fable A6).

No Linux um nome aceita qualquer byte menos "/" e NUL. O Qt desenhava DEL/ESC
como um quadradinho genérico e o TAB como espaço largo, sem aviso. Contratos:
  1. TELA: controle vira ⟦NOME⟧ no lugar exato (⟦TAB⟧, ⟦DEL⟧, ⟦ESC⟧, ⟦LF⟧);
  2. junto com os invisíveis de 22/09 (⟦RLO⟧), sem um apagar o outro;
  3. nome comum (acento, ⌂, emoji) sai intacto;
  4. BUSCA não ignora controle (diferente do invisível): sem_invisiveis mantém;
  5. caminho colado no terminal leva o byte real em $'…' ;
  6. a GUI marca o nome (itálico + nota no tooltip).

Rode:
    python3 tests/test_controle_no_nome_2026_10_27.py
"""
from __future__ import annotations
import os, sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

for bruto, tela in (("a\x7fb.txt", "a⟦DEL⟧b.txt"), ("x\ty.txt", "x⟦TAB⟧y.txt"),
                    ("esc\x1b.txt", "esc⟦ESC⟧.txt"), ("linha\nquebrada", "linha⟦LF⟧quebrada")):
    ok(engine.nome_exibivel(bruto) == tela, f"1. {bruto!r} -> {tela}")
ok(engine.nome_exibivel("f_‮\ttxt.exe") == "f_⟦RLO⟧⟦TAB⟧txt.exe", "2. invisível + controle juntos")
comum = "relatório ⌂ \U0001F389.txt"
ok(engine.nome_exibivel(comum) == comum and not engine.tem_controle(comum), "3. nome comum intacto")
ok(engine.sem_invisiveis("a\x7fb") == "a\x7fb", "4. busca não ignora controle")
ok(engine.caminho_para_shell("/x/a\x7fb\tc") == "$'/x/a\\x7fb\\x09c'", "5. terminal recebe o byte real")
ok(engine.caminho_para_shell("/x/normal.txt") == "/x/normal.txt", "5. caminho comum intacto")

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import app
    ok(app.nome_marcado("/x/a\x7fb") and "TAB or DEL" in app.notas_do_nome("/x/a\x7fb"),
       "6. GUI: itálico + nota no tooltip")
except ImportError as e:
    print(f"(pulado 6: sem PySide6 — {e})")

print()
if falhas:
    print(f"{len(falhas)} falha(s)")
    sys.exit(1)
print("tudo ok")
