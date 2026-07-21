#!/usr/bin/env python3
# Linux File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Linux File Search — which build am I?

Why this module exists: the app is INSTALLED as a copy of the sources under
~/.local/share/linux-file-search/. Committing to the repo therefore changes
nothing about what the user is actually running, and nothing on screen said so.
That silence already cost a real debugging session — a feature was reported
missing that had been implemented and committed, because the installed copy was
six days old.

We do not try to make divergence impossible (a symlink to a git worktree would
mean `git checkout` mutates the running app). We make it VISIBLE: the window
title carries the build, so a glance answers "is this the version with the thing
I just asked for?".

Order of resolution:
  1. a VERSION file written by install.sh next to the package  (installed copy)
  2. git, when running straight from the repo                  (development)
  3. nothing — no build shown, rather than a wrong one

No Qt, no dependency: the CLI and the tests import this too.
"""
from __future__ import annotations
import os, subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)                 # …/linux_file_search ou …/<PREFIX>

# Versão de RELEASE, à mão. Nasceu com o empacotamento (F6): .deb e AppImage
# precisam de um número que ordene ("é mais novo que o instalado?"), e o hash do
# commit não ordena. É o único lugar onde este número existe — o build lê daqui.
# 0.9: em uso diário e completo do F1 ao F4 e F7; o 1.0 fica para quando o
# empacotamento estiver rodando em outra máquina que não a do autor.
RELEASE = "0.9.0"


def _from_file(root: str) -> str:
    """VERSION: '<commit> (<data>)' na 1ª linha.

    Duas origens escrevem esse arquivo: o `install.sh` (carimba na instalação) e
    o próprio `git archive`, que expande `$Format:%h (%cs)$` ao gerar o .zip —
    assim quem recebe o pacote também vê de que commit ele saiu, sem precisar de
    git. No WORKTREE o arquivo existe com o marcador ainda por expandir; nesse
    caso ele não vale nada e caímos no git de verdade."""
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as f:
            line = f.readline().strip()
    except OSError:
        return ""
    return "" if line.startswith("$Format") or not line else line


def _git(root: str, *args) -> str:
    try:
        out = subprocess.run(("git", "-C", root) + args, capture_output=True,
                             timeout=4)
        if out.returncode != 0:
            return ""
        return out.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _from_git(root: str) -> str:
    """Rodando direto do repo: commit curto + data, com '+' se há alteração não
    commitada — quem desenvolve precisa saber que o que está na tela não é o que
    está no commit."""
    commit = _git(root, "rev-parse", "--short", "HEAD")
    if not commit:
        return ""
    date = _git(root, "log", "-1", "--format=%cs")
    dirty = "+" if _git(root, "status", "--porcelain") else ""
    return f"{commit}{dirty}" + (f" ({date})" if date else "")


def build_info(root: str | None = None) -> str:
    """Identificação da build, ou "" se não dá para saber. Nunca inventa: um
    número de versão errado é pior que nenhum."""
    root = root or _ROOT
    return _from_file(root) or _from_git(root)


def deb_version(root: str | None = None) -> str:
    """Versão no formato que o dpkg compara: '0.9.0~git20260721.eb24842'.

    O '~' ordena ANTES de tudo, então qualquer 0.9.0 de snapshot é considerado
    mais antigo que um 0.9.0 final — que é o comportamento certo para um pacote
    gerado a partir do worktree. Sem git (tarball), cai em '0.9.0'."""
    info = build_info(root)                    # "<commit>[+] (<data>)"
    commit = info.split()[0].rstrip("+") if info else ""
    data = info.split("(")[-1].rstrip(")") if "(" in info else ""
    if not (commit and data):
        return RELEASE
    return f"{RELEASE}~git{data.replace('-', '')}.{commit}"


def title_suffix(root: str | None = None) -> str:
    """Sufixo do título da janela. Vazio quando a build é desconhecida, para não
    poluir a barra de título com um '—' solto."""
    info = build_info(root)
    return f"  ·  {info}" if info else ""
