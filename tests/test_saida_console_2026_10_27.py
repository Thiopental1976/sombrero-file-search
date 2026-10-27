#!/usr/bin/env python3
"""Saída capturada no código de página do console (27/10/2026).

No Windows, o PowerShell lê a saída capturada de um programa pelo código de
página do console (cp850 num Windows pt-BR). O sfs escrevia caminhos em UTF-8
e avisos em cp1252: `$r = sfs … -l` devolvia `relat├│rio.txt` (Test-Path
False) e `·` virava `À`. Visto na VM sfs-win10.

Contratos presos aqui (o caso real, com PowerShell, mora no CI Windows F3):
  1. caminho em cp850 volta idêntico ao decodificar com cp850;
  2. letra fora do código de página vira `?` — nunca um parente ASCII, que
     poderia apontar para OUTRO arquivo;
  3. sem código de página (Linux, terminal): os bytes originais, como antes;
  4. aviso no stderr: `—` vira `-`, `·` (existe no cp850) fica;
  5. --json no Windows é ASCII puro e o parser devolve o mesmo nome,
     inclusive surrogate solto; no Linux segue UTF-8 cru;
  6. no Linux, console_codepage() é None — nada muda lá.

Rode:
    python3 tests/test_saida_console_2026_10_27.py
"""
from __future__ import annotations
import json, os, sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import cli, plat

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

acentuado = "C:\\Laudos\\relatório São José.txt"
japones = "C:\\tenc\\a\u3042.txt"

b = cli._codifica_caminho(acentuado, "cp850")
ok(b.decode("cp850") == acentuado, "1. caminho acentuado sobrevive ao cp850")

b = cli._codifica_caminho(japones, "cp850")
ok(b.decode("cp850") == "C:\\tenc\\a?.txt", "2. letra fora do cp850 vira '?'")
b = cli._codifica_caminho("a\u2014b.txt", "cp850")
ok(b == b"a?b.txt", "2. travessão em CAMINHO vira '?', não '-'")

ok(cli._codifica_caminho(acentuado, None) == os.fsencode(acentuado),
   "3. sem código de página: bytes originais")

aviso = "# 3 files \u00b7 0.11s \u2014 index of today"
b = aviso.encode("cp850", "sfs-console")
ok(b.decode("cp850") == "# 3 files \u00b7 0.11s - index of today",
   "4. aviso: '—' vira '-', '·' fica")

obj = {"path": acentuado, "copies": [japones, "x\udcff.txt"]}
b = cli._json_bytes(obj, True)
ok(all(c < 0x80 for c in b), "5. --json no Windows é ASCII puro")
ok(json.loads(b.decode("ascii")) == obj, "5. o parser devolve os mesmos nomes")
b = cli._json_bytes({"path": acentuado}, False)
ok("relatório".encode("utf-8") in b, "5. --json no Linux segue UTF-8 cru")

if not plat.IS_WIN:
    ok(plat.console_codepage() is None, "6. Linux: console_codepage() é None")

print()
if falhas:
    print(f"{len(falhas)} falha(s)")
    sys.exit(1)
print("tudo ok")
