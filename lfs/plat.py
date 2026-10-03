# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
"""Costura de plataforma (Linux ↔ Windows) — desenho do Fable, 02/10/2026.

Uma base, um repo: o que muda de SO mora AQUI, e só aqui. No Linux todas as
funções devolvem exatamente o que o código fazia antes (mesmas variáveis XDG
lidas na hora da chamada, mesmo módulo `disks`), então nada medido muda.

Regra de ouro: `disks()` devolve o objeto-módulo real, e não um wrapper — os
testes que fazem `disks._le_rotational = mock` continuam valendo.
"""
from __future__ import annotations
import os, subprocess, sys
from typing import Optional

IS_WIN = os.name == "nt"

# Executáveis que o Windows aceita sem extensão explícita no shutil.which; o
# fallback de bin/ precisa tentá-los à mão (os.access não completa extensão).
EXE_SUFFIXES = (".exe",) if IS_WIN else ("",)


def exe_candidates(name: str) -> list:
    """Nomes de arquivo a testar para o binário `name` numa pasta."""
    if IS_WIN and not name.lower().endswith(".exe"):
        return [name + ".exe", name]
    return [name]


_NICE = False         # ligado por background_mode(): os filhos herdam a prioridade baixa


def popen_flags(nice_io: Optional[bool] = None) -> dict:
    """kwargs extras para todo subprocess de motor (rg/fd/rga/plocate).

    Windows: CREATE_NO_WINDOW — sem isso, cada busca da GUI pisca um console
    preto. Com nice_io, BELOW_NORMAL_PRIORITY_CLASS (o filho; o próprio processo
    entra em modo background por background_mode()). Linux: {} — nada muda."""
    if not IS_WIN:
        return {}
    flags = subprocess.CREATE_NO_WINDOW
    if _NICE if nice_io is None else nice_io:
        flags |= subprocess.BELOW_NORMAL_PRIORITY_CLASS
    return {"creationflags": flags}


def background_mode() -> bool:
    """Windows: PROCESS_MODE_BACKGROUND_BEGIN no próprio processo — CPU, I/O e
    memória em prioridade baixa (é o `ionice -c3` do Windows). O modo background
    não passa para os filhos: popen_flags() passa a pedir BELOW_NORMAL para cada
    rg/fd. False se não deu."""
    global _NICE
    if not IS_WIN:
        return False
    _NICE = True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        PROCESS_MODE_BACKGROUND_BEGIN = 0x00100000
        return bool(k32.SetPriorityClass(k32.GetCurrentProcess(),
                                         PROCESS_MODE_BACKGROUND_BEGIN))
    except Exception:
        return False


# ------------------------------------------------------------ pastas do usuário
APP_DIR_NAME_WIN = "Sombrero File Search"
APP_DIR_NAME_XDG = "sombrero-file-search"


def config_base() -> str:
    """Base da configuração: %APPDATA% no Windows, XDG_CONFIG_HOME no Linux."""
    if IS_WIN:
        return os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    return os.path.expanduser(os.environ.get("XDG_CONFIG_HOME") or "~/.config")


def cache_base() -> str:
    """Base do cache: %LOCALAPPDATA% no Windows, XDG_CACHE_HOME no Linux."""
    if IS_WIN:
        return os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    return os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")


def app_dir_name() -> str:
    return APP_DIR_NAME_WIN if IS_WIN else APP_DIR_NAME_XDG


def config_dir() -> str:
    return os.path.join(config_base(), app_dir_name())


def cache_dir() -> str:
    return os.path.join(cache_base(), app_dir_name())


def rga_user_config() -> str:
    """Onde o rga do usuário guarda config.jsonc (o rga usa a pasta de config
    do SO: %APPDATA%\\ripgrep-all no Windows)."""
    return os.path.join(config_base(), "ripgrep-all", "config.jsonc")


# -------------------------------------------------------- caminhos longos
_LONG = 240          # margem abaixo de MAX_PATH (260) para o nome do .part


def longpath(p: str) -> str:
    """Prefixo \\\\?\\ para I/O em caminho longo no Windows (independe da
    política LongPathsEnabled). Identidade no Linux e em caminho curto."""
    if not IS_WIN or len(p) <= _LONG or p.startswith("\\\\?\\"):
        return p
    p = os.path.abspath(p)
    if p.startswith("\\\\"):                       # UNC: \\srv\share -> \\?\UNC\srv\share
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def displaypath(p: str) -> str:
    """Tira o prefixo \\\\?\\ para mostrar ao usuário."""
    if p.startswith("\\\\?\\UNC\\"):
        return "\\\\" + p[8:]
    if p.startswith("\\\\?\\"):
        return p[4:]
    return p


# ------------------------------------------------------- comparar caminhos
def path_key(p: str) -> str:
    """Chave de COMPARAÇÃO de caminho (nunca para abrir/mostrar). Windows: o
    NTFS não diferencia caixa, então `C:\\Fotos` e `c:\\fotos` são a mesma
    pasta — normcase baixa a caixa e troca `/` por `\\`; realpath expande nome
    curto 8.3 (`PROGRA~1`) e junções. Linux: abspath puro, como sempre foi
    (realpath lá mudaria a semântica de symlink do acervo)."""
    p = os.path.abspath(p)
    if IS_WIN:
        p = os.path.normcase(os.path.realpath(p))
    return p


def same_or_under(path: str, root: str) -> bool:
    """`path` é `root` ou está dentro dele? Pelas chaves de path_key. Cobre a
    raiz do volume (`/`, `C:\\`), onde `root + os.sep` nunca casaria."""
    a, b = path_key(path), path_key(root)
    if a == b:
        return True
    if not b.endswith(os.sep):
        b += os.sep
    return a.startswith(b)


# ---------------------------------------------------------- módulos por SO
def disks():
    """O módulo de topologia de disco da plataforma (contrato de disks.py)."""
    if IS_WIN:
        try:
            from . import disks_win as m
        except ImportError:
            import disks_win as m            # type: ignore
        return m
    try:
        from . import disks as m
    except ImportError:
        import disks as m                    # type: ignore
    return m


def shell():
    """O módulo de 'abrir/revelar/abrir com' da plataforma (contrato de xdg.py)."""
    if IS_WIN:
        try:
            from . import shell_win as m
        except ImportError:
            import shell_win as m            # type: ignore
        return m
    try:
        from . import xdg as m
    except ImportError:
        import xdg as m                      # type: ignore
    return m


def frozen() -> bool:
    """Rodando de dentro de um executável congelado (PyInstaller)?"""
    return bool(getattr(sys, "frozen", False))
