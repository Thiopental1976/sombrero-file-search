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


def gui() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--docs-adapter":
        sys.exit(_docs_adapter(sys.argv[2:]))
    import app
    app.main()


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--docs-adapter":
        sys.exit(_docs_adapter(sys.argv[2:]))
    import cli as _cli
    sys.argv[0] = "sfs"
    _cli._main_protegido()
