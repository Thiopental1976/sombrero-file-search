# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pontos de entrada do pacote Windows (F3, PyInstaller onedir).

Dois executáveis saem do mesmo código:
  SFS.exe   janela (sem console)         -> app.main()
  sfs.exe   console (CLI + leitor do rga) -> cli, ou `--docs-adapter <ext>`

O leitor de docx/odt/epub roda como filho do rga e conversa por stdin/stdout:
por isso mora no executável de CONSOLE (num exe de janela o stdout pode não
existir). engine.rga_config aponta para o sfs.exe quando está congelado.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lfs"))


def _docs_adapter(argv) -> int:
    import docs_text
    return docs_text.main(argv)


def _crash_log(texto: str) -> str:
    """Grava o traceback onde o usuário (e quem for ajudá-lo) acha: a pasta de
    cache do SFS. Num exe de janela não há console para o erro aparecer."""
    try:
        import plat
        d = plat.cache_dir()
    except Exception:
        d = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    try:
        os.makedirs(d, exist_ok=True)
        caminho = os.path.join(d, "crash.log")
        with open(caminho, "a", encoding="utf-8") as f:
            import time
            f.write("==== %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), texto))
        return caminho
    except OSError:
        return ""


def gui() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--docs-adapter":
        sys.exit(_docs_adapter(sys.argv[2:]))
    try:
        import app
        app.main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        tb = traceback.format_exc()
        caminho = _crash_log(tb)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, "Sombrero File Search could not start.\n\nDetails were saved to:\n%s\n\n%s"
                % (caminho, tb.strip().splitlines()[-1]), "Sombrero File Search", 0x10)
        except Exception:
            pass
        sys.exit(1)


def _gui_selftest() -> int:
    """`sfs.exe --gui-selftest`: monta a janela de verdade (plugin de plataforma
    real), roda o laço de eventos 3 s e fecha. Diz no CONSOLE o que o SFS.exe de
    janela não tem onde dizer. 0 = a janela subiu."""
    import traceback
    try:
        import app
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        qa = QApplication(sys.argv[:1])
        w = app.MainWindow(); w.show()
        QTimer.singleShot(3000, qa.quit)
        qa.exec()
        print("gui ok: plataforma=%s, janela %dx%d" % (qa.platformName(), w.width(), w.height()))
        return 0
    except BaseException:
        traceback.print_exc()
        return 1


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--docs-adapter":
        sys.exit(_docs_adapter(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "--gui-selftest":
        sys.exit(_gui_selftest())
    import cli as _cli
    sys.argv[0] = "sfs"
    _cli._main_protegido()
