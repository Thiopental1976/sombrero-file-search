#!/usr/bin/env python3
"""Testes da verificação de integridade da distribuição (MANIFEST.sha256, --verify e arranque).

Rode:  python3 tests/test_integridade_2026_11_24.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)

import integridade  # noqa: E402

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


def _faz_pacote_falso(base: str, arquivos: dict[str, bytes]) -> str:
    linhas = []
    for rel, data in sorted(arquivos.items()):
        full = os.path.join(base, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        h = hashlib.sha256(data).hexdigest()
        linhas.append(f"{h}  {rel}")
    man = os.path.join(base, integridade.MANIFEST_NAME)
    with open(man, "wb") as f:
        f.write(("\n".join(linhas) + "\n").encode("utf-8"))
    return man


def test_verify_pacote_falso() -> None:
    T = tempfile.mkdtemp(prefix="sfs_verify_")
    try:
        # 1) Pacote íntegro -> ok=True, exit 0, leitura em blocos (> CHUNK_SIZE)
        grande = b"0123456789abcdef" * (integridade.CHUNK_SIZE // 8 + 13)
        pkg = os.path.join(T, "pkg_ok")
        os.makedirs(pkg)
        _faz_pacote_falso(pkg, {
            "SombreroFileSearch.exe": b"fake-gui-exe",
            "sfs.exe": b"fake-cli-exe",
            "bin/rg.exe": grande,
            "bin/pdftotext.exe": b"fake-pdf",
            "licenses/README.txt": b"AGPL/GPL",
        })
        res = integridade.verify_package(pkg)
        code, txt = integridade.format_report(res)
        ok(res["ok"] and code == 0 and res["checked"] == 5 and "OK:" in txt,
           f"pacote íntegro -> exit 0, 5 arquivos conferidos ({code}, checked={res['checked']})")

        # 2) Arquivo alterado (1 byte trocado) -> exit 1, MODIFIED, nunca modifica nada
        alvo = os.path.join(pkg, "bin", "pdftotext.exe")
        with open(alvo, "wb") as f:
            f.write(b"fake-pdX")
        res_mod = integridade.verify_package(pkg)
        code_mod, txt_mod = integridade.format_report(res_mod)
        ok(not res_mod["ok"] and code_mod == 1 and res_mod["modified"] == ["bin/pdftotext.exe"]
           and "MODIFIED: bin/pdftotext.exe" in txt_mod,
           f"arquivo alterado detectado -> exit 1 ({res_mod['modified']})")
        # restaura
        with open(alvo, "wb") as f:
            f.write(b"fake-pdf")

        # 3) Arquivo faltando -> exit 1, MISSING
        os.remove(alvo)
        res_miss = integridade.verify_package(pkg)
        code_miss, txt_miss = integridade.format_report(res_miss)
        ok(not res_miss["ok"] and code_miss == 1 and res_miss["missing"] == ["bin/pdftotext.exe"]
           and "MISSING: bin/pdftotext.exe" in txt_miss,
           f"arquivo faltando detectado -> exit 1 ({res_miss['missing']})")
        with open(alvo, "wb") as f:
            f.write(b"fake-pdf")

        # 4) Arquivo extra -> exit 1, EXTRA (e arquivo extra NÃO é apagado!)
        extra = os.path.join(pkg, "bin", "velho.dll")
        with open(extra, "wb") as f:
            f.write(b"dll antiga")
        res_ext = integridade.verify_package(pkg)
        code_ext, txt_ext = integridade.format_report(res_ext)
        ok(not res_ext["ok"] and code_ext == 1 and res_ext["extra"] == ["bin/velho.dll"]
           and "EXTRA: bin/velho.dll" in txt_ext and os.path.isfile(extra),
           f"arquivo extra detectado sem apagar -> exit 1 ({res_ext['extra']})")
        os.remove(extra)

        # 5) Manifesto ausente (dev/.deb/venv) -> exit 2, mensagem clara sem fingir ok
        sem_man = os.path.join(T, "pkg_sem_manifesto")
        os.makedirs(sem_man)
        res_none = integridade.verify_package(sem_man)
        code_none, txt_none = integridade.format_report(res_none)
        ok(not res_none["has_manifest"] and not res_none["ok"] and code_none == 2
           and "no MANIFEST.sha256 found" in txt_none,
           f"manifesto ausente -> exit 2 com aviso claro ({code_none})")

        # 6) Linha malformada, path traversal e entrada duplicada no manifesto -> exit 1, INVALID
        man = os.path.join(pkg, integridade.MANIFEST_NAME)
        with open(man, "a", encoding="utf-8") as f:
            f.write("linha_quebrada_sem_hash\n")
            f.write(("a" * 64) + "  ../fora.txt\n")
            f.write(("b" * 64) + "  bin\\rg.exe\n")
            f.write(("c" * 64) + "  sfs.exe\n")
        res_bad = integridade.verify_package(pkg)
        code_bad, txt_bad = integridade.format_report(res_bad)
        ok(not res_bad["ok"] and code_bad == 1 and len(res_bad["invalid"]) == 4
           and "INVALID MANIFEST:" in txt_bad,
           f"linhas malformadas/traversal/duplicadas -> exit 1 ({res_bad['invalid']})")

        # 7) CLI real `cli.py --verify` no repo (sem manifesto) -> exit 2 sem exigir argumento `path`
        r = subprocess.run([sys.executable, os.path.join(LFS, "cli.py"), "--verify"],
                           capture_output=True, text=True)
        ok(r.returncode == 2 and "no MANIFEST.sha256 found" in r.stderr,
           f"cli.py --verify sem manifesto sai 2 sem pedir path (rc={r.returncode})")
    finally:
        shutil.rmtree(T, ignore_errors=True)


def main() -> int:
    test_build_windows_ps1_manifest()
    test_verify_pacote_falso()
    if falhas:
        print(f"\n{len(falhas)} FALHA(S):")
        for f in falhas:
            print("  -", f)
        return 1
    print("\ntodos os testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
