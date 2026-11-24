#!/usr/bin/env python3
"""Testes de regressão dos fixes de equivalência e hardening Windows (24/11/2026).

Todos os testes rodam de forma determinística no Linux (simulando Windows via
ntpath / monkeypatch / locale C quando necessário) e também no Windows.

Rode:  python3 tests/test_windows_equivalencia_2026_11_24.py
"""
from __future__ import annotations

import ntpath
import os
import shutil
import stat
import sys
import tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)

import disks    # noqa: E402
import disks_win  # noqa: E402
import engine   # noqa: E402
import fileops  # noqa: E402
import plat     # noqa: E402

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


def test_fileops_raiz_origem_e_fail_closed() -> None:
    # 1) Nomes relativos para raízes Windows/UNC/POSIX (simulado com ntpath no Linux)
    n_drv = fileops._root_rel_name("D:\\", _path=ntpath, label_fn=lambda _: None)
    ok(n_drv == "drive_D", f"raiz D:\\ sem label -> drive_D ({n_drv!r})")
    n_lbl = fileops._root_rel_name("D:\\", _path=ntpath, label_fn=lambda _: "Dados (D:)")
    ok(n_lbl == "Dados (D)", f"raiz D:\\ com label -> sem ':' ({n_lbl!r})")
    n_unc = fileops._root_rel_name("\\\\srv\\share", _path=ntpath, label_fn=lambda _: None)
    ok(n_unc == "srv_share", f"raiz UNC \\\\srv\\share -> srv_share ({n_unc!r})")
    n_dir = fileops._root_rel_name("C:\\Fotos\\2026", _path=ntpath, label_fn=lambda _: None)
    ok(n_dir == "2026", f"pasta normal preserva basename ({n_dir!r})")
    n_posix = fileops._root_rel_name("/", _path=os.path, label_fn=lambda _: None)
    ok(n_posix == "root", f"raiz POSIX / -> root ({n_posix!r})")

    # 2) Capacidades Win32: nenhum desses nomes acusa bad_name e ntpath.join fica dentro do destino
    caps_win = disks.DestCaps(
        fstype="ntfs", mountpoint="E:\\", namemax=255 * 4, readonly=False,
        via_gvfs=False, removable=False, link_mbits=None,
        **disks_win._caps_win("ntfs", disks_win.DRIVE_FIXED),
    )
    for src, lbl_fn in (("D:\\", lambda _: None), ("D:\\", lambda _: "Dados (D:)"),
                        ("\\\\srv\\share", lambda _: None)):
        rel_base = fileops._root_rel_name(src, _path=ntpath, label_fn=lbl_fn)
        rel = ntpath.join(rel_base, "doc.txt")
        dst = ntpath.join("E:\\Backup", rel)
        ok(caps_win.name_problem(rel_base) is None,
           f"rel_base de {src!r} ({rel_base!r}) é válido em Win32")
        ok(fileops._destino_contido("E:\\Backup", rel, dst, _path=ntpath),
           f"join de {src!r} permanece contido em E:\\Backup ({dst!r})")

    # 3) Guarda fail-closed rejeita escape por caminho absoluto, drive ou '..'
    ok(not fileops._destino_contido("E:\\Backup", "\\\\srv\\share\\doc.txt",
                                    "\\\\srv\\share\\doc.txt", _path=ntpath),
       "guarda bloqueia rel UNC que descartaria dest_abs")
    ok(not fileops._destino_contido("E:\\Backup", "D:\\doc.txt",
                                    "D:\\doc.txt", _path=ntpath),
       "guarda bloqueia rel com drive letter")
    ok(not fileops._destino_contido("/tmp/dest", "../fora.txt",
                                    "/tmp/fora.txt", _path=os.path),
       "guarda bloqueia traversal '..'")

    # 4) Teste real de copy_to() com plano injetado tentando escapar do destino
    T = tempfile.mkdtemp(prefix="sfs_fileops_guard_")
    try:
        src_file = os.path.join(T, "origem.txt")
        dest_dir = os.path.join(T, "destino")
        escape_file = os.path.join(T, "nao_tocar.txt")
        os.makedirs(dest_dir)
        with open(src_file, "w", encoding="utf-8") as f:
            f.write("original")
        pf = fileops.preflight([src_file], dest_dir)
        # Substitui entradas por tentativas de escape (absoluto e '..')
        pf.entries = [
            fileops.Entry(src_file, escape_file, "file", 8),
            fileops.Entry(src_file, os.path.join("..", "nao_tocar.txt"), "file", 8),
        ]
        res = fileops.copy_to([src_file], dest_dir, plan=pf)
        ok(not os.path.exists(escape_file),
           "copy_to fail-closed nunca cria arquivo fora de dest_dir")
        ok(len(res.failed) == 2 and not res.copied,
           f"copy_to registra as duas tentativas de escape em failed ({res.failed})")
    finally:
        shutil.rmtree(T, ignore_errors=True)


def main() -> int:
    test_rga_env_e_which_pacote()
    test_fileops_raiz_origem_e_fail_closed()
    if falhas:
        print(f"\n{len(falhas)} FALHA(S):")
        for f in falhas:
            print("  -", f)
        return 1
    print("\ntodos os testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
