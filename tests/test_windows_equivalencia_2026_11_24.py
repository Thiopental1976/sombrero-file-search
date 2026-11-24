#!/usr/bin/env python3
"""Testes de regressão dos fixes de equivalência e hardening Windows (24/11/2026).

Todos os testes rodam de forma determinística no Linux (simulando Windows via
ntpath / monkeypatch / locale C quando necessário) e também no Windows.

Rode:  python3 tests/test_windows_equivalencia_2026_11_24.py
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)

import engine  # noqa: E402
import plat    # noqa: E402

falhas: list[str] = []


def ok(cond: bool, msg: str) -> None:
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)


def _mk_exec(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def test_rga_env_e_which_pacote() -> None:
    T = tempfile.mkdtemp(prefix="sfs_rga_env_")
    rg_orig, rga_orig = engine.RG, engine.RGA
    bins_orig = list(engine._APP_BINS)
    frozen_orig = plat.frozen
    path_orig = os.environ.get("PATH", "")
    try:
        sys_bin = os.path.join(T, "sysbin")
        pkg_bin = os.path.join(T, "pkg", "bin")
        _mk_exec(os.path.join(sys_bin, "rg"))
        _mk_exec(os.path.join(pkg_bin, "rg"))
        _mk_exec(os.path.join(pkg_bin, "rga"))
        _mk_exec(os.path.join(pkg_bin, "pdftotext"))

        os.environ["PATH"] = sys_bin
        engine._APP_BINS[:] = [pkg_bin]

        # 1) Não congelado: RG veio do PATH do sistema, mas RGA está em pkg/bin ->
        #    rga_env() PRECISA incluir pkg/bin no PATH (para achar pdftotext empacotado).
        plat.frozen = lambda: False
        engine.RG = os.path.join(sys_bin, "rg")
        engine.RGA = os.path.join(pkg_bin, "rga")
        env = engine.rga_env()
        ok(env is not None and pkg_bin in env["PATH"].split(os.pathsep),
           "rga_env inclui pasta do RGA/bin empacotado mesmo quando RG já está no PATH")

        # 2) RG e RGA no PATH do sistema, mas _APP_BINS[0] existe -> ainda entra no PATH.
        engine.RGA = os.path.join(sys_bin, "rga")
        env2 = engine.rga_env()
        ok(env2 is not None and pkg_bin in env2["PATH"].split(os.pathsep),
           "rga_env inclui _APP_BINS existente mesmo quando RG e RGA estão no PATH")

        # 3) Quando tudo já está no PATH e nenhum _APP_BINS extra existe -> retorna None.
        engine._APP_BINS[:] = [os.path.join(T, "nao_existe")]
        ok(engine.rga_env() is None,
           "rga_env devolve None quando todas as pastas relevantes já estão no PATH")

        # 4) Build congelado (plat.frozen() == True): _which prefere bin/ empacotado
        #    ao PATH do sistema, e rga_env coloca pkg/bin no INÍCIO do PATH.
        engine._APP_BINS[:] = [pkg_bin]
        plat.frozen = lambda: True
        achado = engine._which("rg")
        ok(achado == os.path.join(pkg_bin, "rg"),
           f"_which congelado prefere bin/ empacotado sobre PATH do sistema ({achado})")
        engine.RG = os.path.join(pkg_bin, "rg")
        engine.RGA = os.path.join(pkg_bin, "rga")
        env_frz = engine.rga_env()
        ok(env_frz is not None and env_frz["PATH"].split(os.pathsep)[0] == pkg_bin,
           "rga_env congelado coloca bin/ empacotado no INÍCIO do PATH")
    finally:
        engine.RG, engine.RGA = rg_orig, rga_orig
        engine._APP_BINS[:] = bins_orig
        plat.frozen = frozen_orig
        os.environ["PATH"] = path_orig
        shutil.rmtree(T, ignore_errors=True)


def main() -> int:
    test_rga_env_e_which_pacote()
    if falhas:
        print(f"\n{len(falhas)} FALHA(S):")
        for f in falhas:
            print("  -", f)
        return 1
    print("\ntodos os testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
