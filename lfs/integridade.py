#!/usr/bin/env python3
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Sombrero File Search — verificação de integridade da distribuição.

Detecta corrupção acidental, extração incompleta ou mistura de arquivos entre
versões (ex.: extrair um .zip novo por cima de uma pasta antiga no Windows)
comparando os arquivos instalados contra o `MANIFEST.sha256` gerado no build.

Política (somente leitura por construção):
  - Leitura estritamente em blocos (CHUNK_SIZE), sem carregar arquivos inteiros
    em memória.
  - Nunca apaga, move, substitui ou "conserta" arquivo nenhum.
  - Sem Qt: usado pela CLI (`sfs --verify`), pelo arranque congelado da GUI
    (checagem rápida só dos executáveis de `bin/`) e pelos testes headless.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from typing import Callable, Optional

try:                       # pacote (GUI) e flat (cli.py/testes)
    from . import plat, version
except ImportError:
    import plat, version                     # type: ignore

MANIFEST_NAME = "MANIFEST.sha256"
CHUNK_SIZE = 1 << 18                         # 256 KiB por bloco

_RX_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")


def package_root() -> str:
    """Pasta raiz da instalação onde `MANIFEST.sha256` mora.

    Em build congelado (PyInstaller onedir), é a pasta do executável
    (`SombreroFileSearch.exe` / `sfs.exe`). Fora dele, é `version._ROOT`."""
    if plat.frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(version._ROOT)


def _valid_rel(rel: str) -> bool:
    """Aceita apenas caminho relativo canônico com `/`, sem drive nem `..`."""
    if not rel or rel == MANIFEST_NAME:
        return False
    if "\\" in rel or rel.startswith("/") or rel.endswith("/"):
        return False
    partes = rel.split("/")
    if any(p in ("", ".", "..") for p in partes):
        return False
    if ":" in partes[0]:
        return False
    return True


def parse_manifest(manifest_path: str) -> tuple[dict[str, str], list[str]]:
    """Lê `MANIFEST.sha256` no formato `sha256sum` (`<64hex>  <rel/path>`).

    Devolve `(entries, invalid_lines)`, onde `entries` mapeia `rel -> sha256_lower`.
    Linhas em branco são ignoradas; qualquer linha fora do formato, com caminho
    inseguro ou entrada duplicada é registrada em `invalid_lines`."""
    entries: dict[str, str] = {}
    seen_keys: set[str] = set()
    invalid: list[str] = []
    with open(plat.longpath(manifest_path), "r", encoding="utf-8", errors="replace") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n")
            if not line:
                continue
            m = _RX_LINE.match(line)
            if not m:
                invalid.append(f"line {lineno}: malformed entry")
                continue
            digest, rel = m.group(1).lower(), m.group(2)
            if not _valid_rel(rel):
                invalid.append(f"line {lineno}: invalid path {rel!r}")
                continue
            key = rel.lower() if plat.IS_WIN else rel
            if key in seen_keys:
                invalid.append(f"line {lineno}: duplicate entry {rel!r}")
                continue
            seen_keys.add(key)
            entries[rel] = digest
    return entries, invalid


def _sha256_file(path: str, deadline: Optional[float] = None) -> Optional[str]:
    """SHA-256 em blocos de `CHUNK_SIZE`. Devolve None se `deadline` expirar."""
    h = hashlib.sha256()
    with open(plat.longpath(path), "rb") as f:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                return None
            blk = f.read(CHUNK_SIZE)
            if not blk:
                break
            h.update(blk)
    return h.hexdigest()


def _key(rel: str) -> str:
    return rel.lower() if plat.IS_WIN else rel


def verify_package(
    root: Optional[str] = None,
    *,
    predicate: Optional[Callable[[str], bool]] = None,
    include_extras: bool = True,
    budget_s: Optional[float] = None,
) -> dict:
    """Confere os arquivos sob `root` contra `MANIFEST.sha256`.

    Parâmetros:
      root           Pasta da instalação (padrão: `package_root()`).
      predicate      Filtro opcional sobre o caminho relativo (`rel -> bool`),
                     usado pela checagem rápida do arranque (só `bin/`).
      include_extras Se True, lista arquivos em disco que não estão no manifesto
                     (exceto o próprio `MANIFEST.sha256`).
      budget_s       Teto opcional de tempo em segundos (para não atrasar o
                     arranque da GUI). Se estourar, marca `timed_out=True`.
    """
    t0 = time.monotonic()
    deadline = (t0 + budget_s) if (budget_s is not None and budget_s > 0) else None
    base = os.path.abspath(root or package_root())
    manifest_path = os.path.join(base, MANIFEST_NAME)
    res = {
        "root": base,
        "manifest": manifest_path,
        "has_manifest": False,
        "ok": False,
        "checked": 0,
        "total": 0,
        "missing": [],
        "modified": [],
        "unreadable": [],
        "extra": [],
        "invalid": [],
        "timed_out": False,
        "elapsed_s": 0.0,
    }
    if not os.path.isfile(plat.longpath(manifest_path)):
        res["elapsed_s"] = time.monotonic() - t0
        return res

    res["has_manifest"] = True
    try:
        entries, invalid = parse_manifest(manifest_path)
    except OSError as e:
        res["invalid"].append(f"could not read manifest: {e}")
        res["elapsed_s"] = time.monotonic() - t0
        return res

    res["invalid"] = invalid
    selected = {rel: dig for rel, dig in entries.items()
                if predicate is None or predicate(rel)}
    res["total"] = len(selected)

    for rel, expected in selected.items():
        if deadline is not None and time.monotonic() >= deadline:
            res["timed_out"] = True
            break
        full = os.path.join(base, *rel.split("/"))
        if not os.path.isfile(plat.longpath(full)):
            res["missing"].append(rel)
            continue
        try:
            got = _sha256_file(full, deadline=deadline)
        except OSError as e:
            res["unreadable"].append(f"{rel} ({e.strerror or e})")
            continue
        if got is None:
            res["timed_out"] = True
            break
        res["checked"] += 1
        if got != expected:
            res["modified"].append(rel)

    if include_extras and not res["timed_out"]:
        known = {_key(rel) for rel in entries}
        known.add(_key(MANIFEST_NAME))
        base_io = plat.longpath(base)
        for dp, _dns, fns in os.walk(base_io, followlinks=False):
            if deadline is not None and time.monotonic() >= deadline:
                res["timed_out"] = True
                break
            rel_dir = os.path.relpath(dp, base_io)
            for fn in fns:
                rel = fn if rel_dir == "." else (rel_dir.replace("\\", "/") + "/" + fn)
                if predicate is not None and not predicate(rel):
                    continue
                if _key(rel) not in known:
                    res["extra"].append(rel)
        res["extra"].sort()

    res["elapsed_s"] = time.monotonic() - t0
    res["ok"] = (
        res["has_manifest"]
        and not res["timed_out"]
        and not res["missing"]
        and not res["modified"]
        and not res["unreadable"]
        and not res["invalid"]        # arquivo a MAIS é aviso, não erro (Rodrigo, 24/11/2026)
    )
    return res


def is_bundled_bin_exe(rel: str) -> bool:
    """Seleciona executáveis auxiliares empacotados em `bin/` (usado na
    checagem rápida de arranque congelado)."""
    low = rel.lower()
    if not low.startswith("bin/"):
        return False
    if plat.IS_WIN:
        return low.endswith(".exe")
    # Fora do Windows (ex.: AppImage ou testes no Linux), qualquer arquivo direto em bin/
    return "/" not in rel[4:]


def verify_bundled_bins(root: Optional[str] = None, budget_s: float = 1.5) -> dict:
    """Checagem rápida no arranque congelado: confere apenas os executáveis de
    `bin/` listados no `MANIFEST.sha256`, respeitando `budget_s`."""
    return verify_package(
        root=root,
        predicate=is_bundled_bin_exe,
        include_extras=False,
        budget_s=budget_s,
    )


def format_report(res: dict) -> tuple[int, str]:
    """Formata resultado de `verify_package()` para a CLI (EN-US).

    Devolve `(exit_code, text)`:
      0 = íntegro
      1 = divergência / corrupção / manifesto malformado
      2 = instalação sem MANIFEST.sha256 (ex.: dev, pip/venv, .deb)
    """
    if not res["has_manifest"]:
        return 2, (
            f"Sombrero File Search {version.RELEASE}: no {MANIFEST_NAME} found in "
            f"{res['root']}.\n"
            "Package verification is available for packaged builds that ship a manifest "
            "(source checkouts, venv/pip and .deb installs are verified by git or the system package manager)."
        )
    if res["ok"]:
        texto = (f"OK: {res['checked']} files verified against {res['manifest']} "
                 f"({res['elapsed_s']:.2f}s).")
        if res["extra"]:
            # Rodrigo, 24/11/2026: arquivo a mais na pasta (nota do usuário, desktop.ini,
            # sobra de uma versão anterior) não é corrupção: avisa e segue íntegro.
            texto += (f"\nWARNING: {len(res['extra'])} file(s) in the folder are not part of "
                      "this package (left over from another version, or added later):")
            texto += "".join(f"\n  EXTRA: {item}" for item in res["extra"])
        return 0, texto
    lines = [f"FAILED: integrity check found problems in {res['root']}:"]
    for item in res["missing"]:
        lines.append(f"  MISSING: {item}")
    for item in res["modified"]:
        lines.append(f"  MODIFIED: {item}")
    for item in res["unreadable"]:
        lines.append(f"  UNREADABLE: {item}")
    for item in res["extra"]:
        lines.append(f"  EXTRA: {item}")
    for item in res["invalid"]:
        lines.append(f"  INVALID MANIFEST: {item}")
    if res["timed_out"]:
        lines.append("  TIMED OUT: check stopped before finishing all files")
    lines.append(
        f"Summary: checked={res['checked']}/{res['total']} missing={len(res['missing'])} "
        f"modified={len(res['modified'])} unreadable={len(res['unreadable'])} "
        f"extra={len(res['extra'])} invalid={len(res['invalid'])} ({res['elapsed_s']:.2f}s)."
    )
    return 1, "\n".join(lines)
