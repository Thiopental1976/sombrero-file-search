#!/usr/bin/env python3
"""Testes da verificação de integridade da distribuição (MANIFEST.sha256, --verify e arranque).

Rode:  python3 tests/test_integridade_2026_11_24.py
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)

falhas: list[str] = []


def ok(cond: bool, msg: str) -> None:
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)


def test_build_windows_ps1_manifest() -> None:
    p = os.path.join(RAIZ, "packaging", "windows", "build_windows.ps1")
    raw = open(p, "rb").read()
    ok(not raw.startswith(b"\xef\xbb\xbf"), "build_windows.ps1 sem BOM UTF-8")
    txt = raw.decode("utf-8")
    idx_man = txt.find("MANIFEST.sha256")
    idx_zip = txt.find("Compress-Archive")
    ok(0 < idx_man < idx_zip, "build_windows.ps1 gera MANIFEST.sha256 ANTES de Compress-Archive")
    ok('if ($relPath -ne "MANIFEST.sha256")' in txt,
       "build_windows.ps1 exclui o próprio MANIFEST.sha256 do manifesto")
    ok("Replace('\\', '/')" in txt and '"$hash  $relPath"' in txt,
       "build_windows.ps1 grava formato sha256sum com '/' e dois espaços")
    ok("System.Text.UTF8Encoding($false)" in txt,
       "build_windows.ps1 grava MANIFEST.sha256 em UTF-8 sem BOM")


def main() -> int:
    test_build_windows_ps1_manifest()
    if falhas:
        print(f"\n{len(falhas)} FALHA(S):")
        for f in falhas:
            print("  -", f)
        return 1
    print("\ntodos os testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
