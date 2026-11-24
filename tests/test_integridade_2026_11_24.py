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

        # 4) Arquivo extra -> AVISO com exit 0 (decisão do Rodrigo 24/11), listado e NÃO apagado
        extra = os.path.join(pkg, "bin", "velho.dll")
        with open(extra, "wb") as f:
            f.write(b"dll antiga")
        res_ext = integridade.verify_package(pkg)
        code_ext, txt_ext = integridade.format_report(res_ext)
        ok(res_ext["ok"] and code_ext == 0 and res_ext["extra"] == ["bin/velho.dll"]
           and "WARNING" in txt_ext and "EXTRA: bin/velho.dll" in txt_ext and os.path.isfile(extra),
           f"arquivo extra: aviso, exit 0, sem apagar ({res_ext['extra']})")
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


def test_checagem_rapida_arranque_bin() -> None:
    import plat
    T = tempfile.mkdtemp(prefix="sfs_verify_fast_")
    is_win_orig = plat.IS_WIN
    try:
        pkg = os.path.join(T, "pkg_win")
        os.makedirs(pkg)
        _faz_pacote_falso(pkg, {
            "SombreroFileSearch.exe": b"gui-grande-nao-tocado",
            "_internal/Qt6Core.dll": b"qt-dll-grande",
            "bin/rg.exe": b"rg-bytes",
            "bin/fd.exe": b"fd-bytes",
            "bin/rga.exe": b"rga-bytes",
            "bin/pdftotext.exe": b"pdf-bytes",
            "bin/poppler.dll": b"dll-nao-exe",
        })
        # Simula Windows: só bin/*.exe entram na checagem rápida do arranque
        plat.IS_WIN = True
        # Altera arquivo fora de bin/ e coloca extra fora de bin/: checagem rápida ignora
        with open(os.path.join(pkg, "_internal", "Qt6Core.dll"), "wb") as f:
            f.write(b"mudado-fora-de-bin")
        with open(os.path.join(pkg, "extra_fora.txt"), "wb") as f:
            f.write(b"extra")

        res_ok = integridade.verify_bundled_bins(pkg, budget_s=1.5)
        ok(res_ok["ok"] and res_ok["checked"] == 4 and res_ok["total"] == 4,
           f"checagem rápida só confere os 4 .exe de bin/ ({res_ok['checked']}/{res_ok['total']})")

        # Altera 1 byte em bin/rg.exe -> checagem rápida acusa modified
        with open(os.path.join(pkg, "bin", "rg.exe"), "wb") as f:
            f.write(b"rg-byteX")
        res_bad = integridade.verify_bundled_bins(pkg, budget_s=1.5)
        ok(not res_bad["ok"] and res_bad["modified"] == ["bin/rg.exe"],
           f"checagem rápida detecta bin/rg.exe alterado ({res_bad['modified']})")

        # Teto de tempo (budget_s): garante que para cedo e marca timed_out sem travar
        import time
        real_mono = time.monotonic
        ticks = iter([100.0, 100.0, 102.0, 102.0, 102.0])
        time.monotonic = lambda: next(ticks, 102.0)  # type: ignore[assignment]
        try:
            res_to = integridade.verify_bundled_bins(pkg, budget_s=1.0)
        finally:
            time.monotonic = real_mono
        ok(res_to["timed_out"] and not res_to["ok"] and res_to["checked"] < 4,
           f"checagem rápida respeita budget_s e encerra cedo (timed_out={res_to['timed_out']}, checked={res_to['checked']})")
    finally:
        plat.IS_WIN = is_win_orig
        shutil.rmtree(T, ignore_errors=True)


def main() -> int:
    test_build_windows_ps1_manifest()
    test_verify_pacote_falso()
    test_checagem_rapida_arranque_bin()
    if falhas:
        print(f"\n{len(falhas)} FALHA(S):")
        for f in falhas:
            print("  -", f)
        return 1
    print("\ntodos os testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
