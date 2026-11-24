#!/usr/bin/env python3
"""Testes de regressão dos fixes de equivalência e hardening Windows (24/11/2026).

Todos os testes rodam de forma determinística no Linux (simulando Windows via
ntpath / monkeypatch / locale C quando necessário) e também no Windows.

Rode:  python3 tests/test_windows_equivalencia_2026_11_24.py
"""
from __future__ import annotations

import builtins
import datetime
import ntpath
import os
import shutil
import stat
import sys
import tempfile
import threading
import time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)

import boolean       # noqa: E402
import disks         # noqa: E402
import disks_win     # noqa: E402
import engine        # noqa: E402
import fileops       # noqa: E402
import plat          # noqa: E402
import resultfilter  # noqa: E402

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

        # 5) _destino_contido em copy_to não chama os.path.realpath por arquivo
        pf_ok = fileops.preflight([src_file], dest_dir)
        real_rp = os.path.realpath
        chamadas = [0]
        def _conta_rp(p, *a, **kw):
            chamadas[0] += 1
            return real_rp(p, *a, **kw)
        os.path.realpath = _conta_rp  # type: ignore[assignment]
        try:
            res_ok = fileops.copy_to([src_file], dest_dir, plan=pf_ok)
        finally:
            os.path.realpath = real_rp
        ok(len(res_ok.copied) == 1 and chamadas[0] == 0,
           f"copy_to não chama os.path.realpath no loop de arquivos (chamadas={chamadas[0]})")
    finally:
        shutil.rmtree(T, ignore_errors=True)


def test_resultfilter_datas_antigas_windows() -> None:
    # Simula CRT do Windows: timestamp() levanta OSError(22) para < 1970 e
    # OverflowError para > 3001.
    class _WinDatetime(datetime.datetime):
        def timestamp(self) -> float:
            if self.year < 1970:
                raise OSError(22, "Invalid argument")
            if self.year > 3001:
                raise OverflowError("timestamp out of range")
            return super().timestamp()

    dt_mod_orig = resultfilter.datetime

    class _FakeDtMod:
        datetime = _WinDatetime
        timedelta = dt_mod_orig.timedelta

    resultfilter.datetime = _FakeDtMod  # type: ignore[assignment]
    try:
        # <1969 não dá crash e realmente filtra por epoch negativo
        pred_old = resultfilter.compile_filter("<1969")
        mt_1965 = (datetime.datetime(1965, 6, 1) - datetime.datetime(1970, 1, 1)).total_seconds()
        mt_2020 = datetime.datetime(2020, 6, 1).timestamp()
        ok(pred_old("a.txt", "/a.txt", mt_1965),
           "resultfilter <1969 casa mtime de 1965 sob CRT Windows simulado")
        ok(not pred_old("a.txt", "/a.txt", mt_2020),
           "resultfilter <1969 rejeita mtime de 2020 sob CRT Windows simulado")

        # >3500 (OverflowError no Windows) também não dá crash
        pred_far = resultfilter.compile_filter("<3500")
        ok(pred_far("a.txt", "/a.txt", mt_2020),
           "resultfilter <3500 não estoura OverflowError e casa 2020")

        # >9999 (year + 1 == 10000 -> ValueError) cai silenciosamente em substring
        pred_9999 = resultfilter.compile_filter(">9999")
        ok(not pred_9999("a.txt", "/a.txt", mt_2020),
           "resultfilter >9999 não levanta ValueError")

        # Fallback respeita fuso local (time.timezone) em TZ fixada (POSIX tzset)
        if hasattr(time, "tzset"):
            old_tz = os.environ.get("TZ")
            try:
                for tz_name, expected_offset in (("UTC+3", 10800), ("UTC-9", -32400)):
                    os.environ["TZ"] = tz_name
                    time.tzset()
                    lo, hi = resultfilter._period_bounds(1969, 6, 1)
                    # Em 1969-06-01 00:00 local, UTC é 1969-06-01 00:00 + expected_offset
                    esperado_lo = (datetime.datetime(1969, 6, 1) - datetime.datetime(1970, 1, 1)).total_seconds() + expected_offset
                    ok(abs(lo - esperado_lo) < 1e-6 and abs((hi - lo) - 86400.0) < 1e-6,
                       f"_to_epoch fallback alinha com TZ={tz_name} (lo={lo}, esperado={esperado_lo})")
            finally:
                if old_tz is None:
                    os.environ.pop("TZ", None)
                else:
                    os.environ["TZ"] = old_tz
                time.tzset()
    finally:
        resultfilter.datetime = dt_mod_orig

    # Além disso, se _period_bounds levantar OSError/OverflowError direto,
    # _compile_token ainda cai em substring sem derrubar a GUI.
    orig_pb = resultfilter._period_bounds
    try:
        for exc in (OSError(22, "Invalid argument"), OverflowError("range")):
            def _boom(*_a, _e=exc):
                raise _e
            resultfilter._period_bounds = _boom
            p = resultfilter.compile_filter("<1969")
            ok(not p("a.txt", "/a.txt", 0.0),
               f"_compile_token captura {type(exc).__name__} sem derrubar a GUI")
    finally:
        resultfilter._period_bounds = orig_pb


def test_fallback_python_encoding_utf8_sob_cp1252() -> None:
    T = tempfile.mkdtemp(prefix="sfs_utf8_cp1252_")
    real_open = builtins.open

    def _open_default_cp1252(file, mode="r", *args, **kwargs):
        # Simula Windows congelado sem PYTHONUTF8=1: todo open() em modo texto
        # sem `encoding=` explícito abre em cp1252.
        if "b" not in mode and "encoding" not in kwargs and len(args) < 2:
            kwargs["encoding"] = "cp1252"
        return real_open(file, mode, *args, **kwargs)

    try:
        f_utf8 = os.path.join(T, "utf8.txt")
        f_cp1252 = os.path.join(T, "cp1252.txt")
        with real_open(f_utf8, "wb") as f:
            f.write("laudo médico coração\n".encode("utf-8"))
        with real_open(f_cp1252, "wb") as f:
            f.write("exame coração antigo\n".encode("cp1252"))

        q = engine.Query(paths=[T], content="coração")
        builtins.open = _open_default_cp1252  # type: ignore[assignment]
        try:
            hits = list(engine._iter_content_python(q, lambda: False))
            nomes = sorted(os.path.basename(m.path) for m in hits)
            ok(nomes == ["cp1252.txt", "utf8.txt"],
               f"engine._iter_content_python acha UTF-8 e cp1252 sob default cp1252 ({nomes})")
            linhas_utf8 = next((m.lines for m in hits if m.path.endswith("utf8.txt")), [])
            ok(bool(linhas_utf8) and "coração" in linhas_utf8[0][1],
               f"engine._iter_content_python preserva acento UTF-8 sem mojibake ({linhas_utf8})")

            disp = boolean._display_lines_py(["coração"], [f_utf8, f_cp1252], q, lambda: False)
            ok(os.path.abspath(f_utf8) in disp and os.path.abspath(f_cp1252) in disp,
               f"boolean._display_lines_py acha UTF-8 e cp1252 sob default cp1252 ({list(disp)})")
            ok("coração" in disp[os.path.abspath(f_utf8)][0][1],
               f"boolean._display_lines_py preserva acento UTF-8 ({disp[os.path.abspath(f_utf8)]})")
        finally:
            builtins.open = real_open
    finally:
        shutil.rmtree(T, ignore_errors=True)


def test_rga_args_trava_limpeza_e_corrida() -> None:
    T = tempfile.mkdtemp(prefix="sfs_rga_args_")
    cache_env = "LOCALAPPDATA" if plat.IS_WIN else "XDG_CACHE_HOME"
    old_cache = os.environ.get(cache_env)
    old_replace = os.replace
    os.environ[cache_env] = T
    engine._rga_args_cache = None
    try:
        # 1) 8 threads concorrentes na 1ª chamada -> todas obtêm o mesmo arquivo, sem .config-* órfão
        barreira = threading.Barrier(8)
        res = []
        lock = threading.Lock()

        def _worker():
            barreira.wait()
            a = engine.rga_args()
            with lock:
                res.append(a)

        ts = [threading.Thread(target=_worker) for _ in range(8)]
        for th in ts:
            th.start()
        for th in ts:
            th.join()
        ok(len(res) == 8 and all(len(a) == 1 for a in res) and len({a[0] for a in res}) == 1,
           f"rga_args concorrente (8 threads) converge no mesmo config ({res[:2]})")
        cfg_path = res[0][0].split("=", 1)[1]
        rga_dir = os.path.dirname(cfg_path)
        sobras = [f for f in os.listdir(rga_dir) if f.startswith(".config-")]
        ok(not sobras, f"sem temporários .config-* órfãos após corrida ({sobras})")

        # 2) Corrida Windows inter-processo: os.replace falha com PermissionError
        #    quando outro processo criou `path` entre isfile() e replace().
        os.remove(cfg_path)
        engine._rga_args_cache = None

        def _replace_corrida(src, dst):
            # Simula outro processo criando `dst` antes e travando o replace
            with open(dst, "w", encoding="utf-8") as f:
                f.write("{}")
            raise PermissionError(13, "WinError 5 simulated")

        os.replace = _replace_corrida
        try:
            a_race = engine.rga_args()
        finally:
            os.replace = old_replace
        ok(a_race == ["--rga-config-file=" + cfg_path],
           f"rga_args reaproveita config existente quando os.replace dá PermissionError ({a_race})")
        sobras = [f for f in os.listdir(rga_dir) if f.startswith(".config-")]
        ok(not sobras, f"temporário .config-* limpo após PermissionError com destino existente ({sobras})")

        # 3) Falha transitória sem destino existir: devolve [], limpa tmp e NÃO envenena cache
        os.remove(cfg_path)
        engine._rga_args_cache = None

        def _replace_falha(src, dst):
            raise PermissionError(13, "transient failure")

        os.replace = _replace_falha
        try:
            a_fail = engine.rga_args()
        finally:
            os.replace = old_replace
        ok(a_fail == [], f"rga_args devolve [] em falha transitória ({a_fail})")
        sobras = [f for f in os.listdir(rga_dir) if f.startswith(".config-")]
        ok(not sobras, f"temporário .config-* limpo em falha transitória ({sobras})")
        a_rec = engine.rga_args()
        ok(a_rec == ["--rga-config-file=" + cfg_path] and os.path.isfile(cfg_path),
           f"rga_args se recupera na chamada seguinte (cache não envenenado: {a_rec})")
    finally:
        os.replace = old_replace
        engine._rga_args_cache = None
        if old_cache is None:
            os.environ.pop(cache_env, None)
        else:
            os.environ[cache_env] = old_cache
        shutil.rmtree(T, ignore_errors=True)


def test_filtro_oculto_win_caminho_relativo() -> None:
    T = tempfile.mkdtemp(prefix="sfs_oculto_rel_")
    is_win_orig = plat.IS_WIN
    oculto_orig = engine._oculto
    cwd_orig = os.getcwd()
    try:
        sub = os.path.join(T, "pasta_oculta")
        os.makedirs(sub)
        f1 = os.path.join(T, "rotina.txt")
        f2 = os.path.join(sub, "visivel.txt")
        for fp in (f1, f2):
            with open(fp, "w", encoding="utf-8") as f:
                f.write("ok")

        plat.IS_WIN = True
        engine._oculto = lambda pasta, nome: nome in ("rotina.txt", "pasta_oculta")
        os.chdir(T)
        q = engine.Query(paths=["."], name_patterns=["*.txt"], content="ok")
        fora = engine.filtro_oculto_win(q)
        ok(fora is not None, "filtro_oculto_win ativo no Windows com glob de nome")
        if fora is not None:
            ok(fora("./rotina.txt") and fora("rotina.txt"),
               "filtro_oculto_win detecta arquivo oculto passado com caminho relativo")
            ok(fora("./pasta_oculta/visivel.txt"),
               "filtro_oculto_win detecta pasta pai oculta passada com caminho relativo")
            ok(not fora("./normal.txt"),
               "filtro_oculto_win permite arquivo visível passado com caminho relativo")
    finally:
        os.chdir(cwd_orig)
        plat.IS_WIN = is_win_orig
        engine._oculto = oculto_orig
        shutil.rmtree(T, ignore_errors=True)


def test_longpath_relativo() -> None:
    is_win_orig = plat.IS_WIN
    abspath_orig = os.path.abspath
    try:
        plat.IS_WIN = True
        # 1) Caminho relativo curto num diretório de trabalho fundo (>240 chars)
        fundo = "C:\\" + ("pasta_muito_longa\\" * 15) + "arq.txt"
        assert len(fundo) > 260
        os.path.abspath = lambda p: fundo if p == "arq.txt" else abspath_orig(p)
        lp = plat.longpath("arq.txt")
        ok(lp == "\\\\?\\" + fundo,
           f"plat.longpath aplica \\\\?\\ em caminho relativo cuja forma absoluta passa de 240 ({lp[:40]!r})")

        # 2) Caminho relativo num share UNC fundo (>240 chars)
        fundo_unc = "\\\\srv\\share\\" + ("pasta_muito_longa\\" * 15) + "arq.txt"
        os.path.abspath = lambda p: fundo_unc if p == "arq.txt" else abspath_orig(p)
        lp_unc = plat.longpath("arq.txt")
        ok(lp_unc == "\\\\?\\UNC\\" + fundo_unc[2:],
           f"plat.longpath aplica \\\\?\\UNC\\ em caminho relativo UNC fundo ({lp_unc[:40]!r})")

        # 3) Caminho relativo realmente curto continua inalterado
        os.path.abspath = lambda p: "C:\\curto\\a.txt" if p == "a.txt" else abspath_orig(p)
        ok(plat.longpath("a.txt") == "a.txt",
           "plat.longpath preserva caminho relativo curto sem prefixo")

        # 4) Caminho vazio e já prefixado não são alterados
        ok(plat.longpath("") == "" and plat.longpath("\\\\?\\C:\\x") == "\\\\?\\C:\\x",
           "plat.longpath preserva vazio e já prefixado")

        # 5) Fast-path no caminho quente: absoluto curto NÃO chama os.path.abspath
        abs_chamadas = [0]
        def _conta_abs(p):
            abs_chamadas[0] += 1
            return "C:\\curto\\x" if p == "\\sem_drive\\x" else abspath_orig(p)
        os.path.abspath = _conta_abs
        ok(plat.longpath("C:\\curto\\a.txt") == "C:\\curto\\a.txt" and abs_chamadas[0] == 0,
           f"plat.longpath absoluto curto não chama abspath (chamadas={abs_chamadas[0]})")
        ok(plat.longpath("\\\\srv\\share\\a.txt") == "\\\\srv\\share\\a.txt" and abs_chamadas[0] == 0,
           f"plat.longpath UNC curto não chama abspath (chamadas={abs_chamadas[0]})")
        # Caminho drive-relative (\sem_drive\x) ainda passa por abspath
        plat.longpath("\\sem_drive\\x")
        ok(abs_chamadas[0] == 1,
           f"plat.longpath drive-relative chama abspath (chamadas={abs_chamadas[0]})")

        # 6) force=True prefixa sempre (para os.walk descer em árvore funda a partir de raiz curta)
        os.path.abspath = lambda p: p
        ok(plat.longpath("C:\\curto", force=True) == "\\\\?\\C:\\curto",
           "plat.longpath(force=True) prefixa raiz curta C:\\curto")
        ok(plat.longpath("\\\\srv\\share", force=True) == "\\\\?\\UNC\\srv\\share",
           "plat.longpath(force=True) prefixa raiz UNC curta")
    finally:
        plat.IS_WIN = is_win_orig
        os.path.abspath = abspath_orig


def test_longpath_io_engine_dupes_app() -> None:
    import dupes
    T = tempfile.mkdtemp(prefix="sfs_lp_io_")
    try:
        sub = os.path.join(T, "a" * 80, "b" * 80, "c" * 80)
        os.makedirs(sub)
        f1 = os.path.join(sub, "dup1.txt")
        f2 = os.path.join(sub, "dup2.txt")
        for fp in (f1, f2):
            with open(fp, "w", encoding="utf-8") as f:
                f.write("conteudo identico para teste longpath\n")

        # Espiona chamadas a plat.longpath em engine, dupes e app
        chamados: set[str] = set()
        forcados: set[str] = set()
        lp_orig = plat.longpath
        dupes_L_orig = dupes._L

        def _spy_lp(p: str, force: bool = False) -> str:
            chamados.add(p)
            if force:
                forcados.add(p)
            return lp_orig(p, force=force)

        plat.longpath = _spy_lp  # type: ignore[assignment]
        dupes._L = _spy_lp       # type: ignore[assignment]
        try:
            # 1) engine._raiz_existe + _legivel
            chamados.clear(); forcados.clear()
            st_dict: dict = {}
            ok(engine._raiz_existe(sub, st_dict), "engine._raiz_existe aceita pasta longa")
            ok(sub in chamados, "engine._raiz_existe passa a raiz por plat.longpath")

            # 2) engine._iter_names_python a partir de RAIZ CURTA (T) descendo na árvore funda
            chamados.clear(); forcados.clear()
            ms = list(engine._iter_names_python(engine.Query(paths=[T], name_patterns=["*.txt"])))
            ok(len(ms) == 2 and all(not m.path.startswith("\\\\?\\") for m in ms),
               f"engine._iter_names_python acha os 2 arquivos a partir de raiz curta sem vazar \\\\?\\ ({len(ms)})")
            ok(os.path.abspath(T) in forcados,
               "engine._iter_names_python chama plat.longpath(root, force=True) para raiz curta")

            # 3) dupes.find_duplicates a partir de RAIZ CURTA (T) descendo na árvore funda
            chamados.clear(); forcados.clear()
            grps = dupes.find_duplicates([T])
            ok(len(grps) == 1 and len(grps[0].members) == 2,
               f"dupes.find_duplicates acha duplicata em árvore funda a partir de raiz curta ({len(grps)})")
            ok(T in forcados,
               "dupes._walk chama plat.longpath(root, force=True) para raiz curta")
        finally:
            plat.longpath = lp_orig
            dupes._L = dupes_L_orig

        # 4) app.py: checagem em código (sem exigir display Qt no Linux/CI)
        app_src = open(os.path.join(LFS, "app.py"), encoding="utf-8").read()
        for trecho, desc in (
            ("os.stat(engine.plat.longpath(p))", "ConflictDialog._desc usa longpath"),
            ("os.walk(engine.plat.longpath(self.path, force=True)", "_DirSizeWorker usa longpath(force=True)"),
            ("os.lstat(engine.plat.longpath(", "PropertiesDialog/_DirSizeWorker lstat usa longpath"),
            ("os.path.getsize(engine.plat.longpath(p))", "DuplicatesPanel._fill_names usa longpath"),
            ("QImageReader(io)", "_load_image abre QImageReader via longpath"),
            ("with open(io, \"rb\") as f:", "_peek abre arquivo via longpath"),
        ):
            ok(trecho in app_src, f"app.py: {desc}")
    finally:
        shutil.rmtree(T, ignore_errors=True)


def main() -> int:
    test_rga_env_e_which_pacote()
    test_fileops_raiz_origem_e_fail_closed()
    test_resultfilter_datas_antigas_windows()
    test_fallback_python_encoding_utf8_sob_cp1252()
    test_rga_args_trava_limpeza_e_corrida()
    test_filtro_oculto_win_caminho_relativo()
    test_longpath_relativo()
    test_longpath_io_engine_dupes_app()
    if falhas:
        print(f"\n{len(falhas)} FALHA(S):")
        for f in falhas:
            print("  -", f)
        return 1
    print("\ntodos os testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
