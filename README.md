<div align="center">

<img src="assets/icon_128.png" width="96" alt="Sombrero File Search">

# Sombrero File Search

**Native file search for Linux — by name, by content, boolean, and inside documents.**
*A live, index-free search tool in the spirit of Agent Ransack / FileLocator Pro.*

![Python](https://img.shields.io/badge/Python-3.9%2B-3776ab)
![PySide6](https://img.shields.io/badge/GUI-PySide6-41cd52)
![ripgrep](https://img.shields.io/badge/engine-ripgrep%20%2B%20fd-orange)
![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)

**English** · [Português (BR)](README.pt-BR.md)

</div>

---

## What it is

An **index-free** file searcher with **live** results, in the spirit of Windows'
*Agent Ransack / FileLocator Pro* — but native to Linux and portable across distros.
The engine is **ripgrep** (`rg`) for content and **fd** for names; both are faster than
the commercial searchers. Without `rg`/`fd` it falls back to pure Python, so it runs
anywhere.

The Windows searchers are **useless on Linux**: they read the NTFS MFT/USN, which does
not exist here. This project reimplements the job natively.

> 📖 **Full manual:** [MANUAL.md](MANUAL.md) (English) · [MANUAL.pt-BR.md](MANUAL.pt-BR.md) (Português) — GUI usage and every CLI capability.

## Features

- 🔎 **Name + content** — glob (`*.py`) or regex, plain text or regex, with highlighting in the preview.
- 🧩 **Boolean search** — `(note OR report) AND patient NOT draft`. Also accepts `| & !` and
  `"quotes"` for phrases. Precedence `NOT > AND > OR`, parentheses supported. Resolved over
  file sets (`rg -l`).
- 📄 **Inside documents** — searches **PDF, docx, epub, odt, zip** via
  [ripgrep-all](https://github.com/phiresky/ripgrep-all) (optional).
- 🎬 **Media preview** — image thumbnails and an audio/video **player** with transport
  controls (⏮ ▶/⏸ ⏭), a position slider, and navigation across the media in your results.
- 🌗 **Light/dark theme** — toggle with `Ctrl+T`, preference persisted.
- 🎛️ **Filters** — minimum size, modified in the last N days, hidden files, `.gitignore`,
  don't cross mount points (`--one-file-system`), whole word, case sensitivity.
- ⚡ **Live** — the table grows *during* the search (streaming `rg --json` on a worker thread).
- 🗂️ **Search tabs** — several searches open at once, each with its own form and results
  (`Ctrl+N` new, `Ctrl+↵` search in a new tab, `Ctrl+W` close).
- ⭐ **Saved searches + history** — save a whole search (not just the term) and reopen it
  later; recent searches live in the **Searches ▾** menu (`Ctrl+S` save, `Ctrl+R` repeat),
  and `↑`/`↓` in the name field walk the history.
- 📤 **Export** — results to **CSV** (one row per matched snippet) or **JSON** (one object
  per file), in the order shown on screen (`Ctrl+E`).
- 📁 **Copy files** — drag to another app or copy to a folder, with destination pre-flight
  checks (free space, FAT32 limits, illegal names) and **paced writing to removable media**
  so it never hijacks the system cache. It never moves or deletes the source.
- 💻 **Matching CLI** — same engine, with `--print0` for pipelines.

## Installation

Three routes, in the order you probably care about:

| | when to use | does the GUI work? |
|---|---|---|
| **AppImage** | any distro, nothing to install | yes — Python and PySide6 are bundled |
| **.deb** | Debian/Ubuntu/Mint, apt-integrated | needs PySide6 (see below) |
| **install.sh** | any distro, installs into `~`, no root | yes — uses the system's or builds a venv |

### AppImage — one file, nothing to install

```bash
chmod +x Sombrero_File_Search-*.AppImage
./Sombrero_File_Search-*.AppImage                            # GUI
./Sombrero_File_Search-*.AppImage --cli ~/docs -n '*.pdf'    # the very same CLI
```

Ships Python and Qt inside (~135 MB). Uses **your system's** `rg`/`fd` when present —
it neither hijacks nor duplicates them.

> There is no Flatpak build, on purpose: this program exists to sweep the whole disk, and
> the Flatpak sandbox is the wrong model for that. Granting it `--filesystem=host` would
> void the sandbox and still fight the portals.

### .deb

```bash
sudo apt install ./sombrero-file-search_*_all.deb
lfs ~/docs -n '*.pdf'          # CLI: works right away, only needs python3
sombrero-file-search           # GUI
```

The package is **deliberately thin**: `Depends: python3`, with `ripgrep` and `fd-find` as
*Recommends* (there is a pure-Python fallback, so declaring them mandatory would be a lie).
Debian/Ubuntu/Mint's apt **has no PySide6** — on those distros, the first GUI launch asks
for a single command:

```bash
sombrero-file-search --setup-gui   # creates a venv in YOUR home, no root
```

### install.sh — universal installer

Detects apt/dnf/pacman/zypper and installs the app into `~/.local`, without root:

```bash
git clone https://github.com/Thiopental1976/sombrero-file-search.git
cd sombrero-file-search
./install.sh
```

It installs `ripgrep`, `fd` and `poppler` through your distro's package manager (with your
consent), downloads `ripgrep-all` and `pandoc` (static binaries, for document mode) and sets
up PySide6 (system-wide or in a dedicated venv). When it finishes, launch **Sombrero File
Search** from the menu or run `sombrero-file-search`.

It also works on **immutable distros** (Fedora Atomic, Bazzite, SteamOS-style systems):
fully user-space, no root, no layering.

### Manual

```bash
# system dependencies (Debian/Ubuntu/Mint example)
sudo apt install ripgrep fd-find poppler-utils
pip install PySide6            # or use the venv from install.sh
python3 lfs/app.py             # GUI
```

## CLI usage

```bash
lfs ~/projects -n '*.py' -c "def main"           # name + content
lfs ~/docs -c "report" --docs                    # inside PDF/docx/epub
lfs ~/notes -b '(note OR report) AND patient'    # boolean
lfs /data -c error -l --print0 | xargs -0 ...    # pipeline
lfs /repo -n '*.log' --json                      # NDJSON for automation (cron, scripts)
lfs /repo -c error --nice-io                     # yields CPU/IO to the server's real workload
lfs ~/archive -n report --index                  # NAME search accelerated by plocate
```

`-c` content · `-n` name · `-b/--bool` boolean · `-D/--docs` documents · `-l` paths only ·
`--print0` null separator · `--json` NDJSON · `--nice-io` low priority · `--index` index.
Run `lfs --help` for everything.

**Index acceleration (`--index`, NAME only):** explicitly opt-in — the default mode is always
"what is on disk RIGHT NOW". With `--index`, name searches query `plocate` (fast), but with
**guaranteed honesty**: (1) if any part of the path is **pruned** from the index
(`PRUNEFS`/`PRUNEPATHS` in `updatedb.conf` — typically network mounts, `/mnt`, `/media`,
`/tmp`), SFS **refuses with a clear error** instead of silently returning a missing subtree;
(2) every result is **verified live** (`lstat`) — whatever vanished from disk since the last
`updatedb` does not show up; (3) the **index date** is always displayed. Content is not
indexable → `--index` is rejected for it (use the live search).

**For automation (`--json`):** one JSON object per match, one per line (NDJSON) — fields
`path`, `size`, `mtime`, `is_dir`, `nmatch`, `lines[]` (the same logical `Match.lines`, without
terminators). Warnings travel **in the same stream** (`{"warn":"mount_dead",…}`,
`{"warn":"denied",…}`) and a malformed boolean expression becomes
`{"error":"boolean_expression",…}`. The **exit code** follows `grep`: **0** found, **1** nothing,
**2** error. A filename containing `\n` is escaped by JSON and never breaks line framing.

## `rg` ↔ Python fallback parity (known divergences)

The pure-Python fallback returns the **same result** as ripgrep in the overwhelming majority
of cases — the parity harness runs 500 random boolean expressions × 2000 files and demands zero
divergence (`tests/test_parity_rg_python.py`). The few differences that do exist are
**documented on purpose** — none of them is a surprise:

- **`nmatch` (the "how hot is this file" counter)** — with `rg` it counts per **occurrence**;
  in the fallback, per **matching line**. It only differs when the same line contains the term
  more than once. The file set and the lines (number + text) are identical. It is an indicator,
  not a contract.
- **UTF-16/UTF-32 with BOM** — `rg` detects the BOM and decodes; the fallback opens in text mode
  (UTF-8/locale) and **does not find** the term. Affects only the **no-ripgrep** mode, on files
  of Windows origin. Installing `ripgrep` (it is a *Recommends*) fixes it.
- **CRLF (`\r\n`) — SOLVED.** `rg` used to hand back the line **with** its trailing `\r` while
  the fallback (universal-newline reading) did **not**. Now **both** engines normalise a trailing
  `\r` via `engine._logical_line`: `m.lines` carries the **logical** text of the line, free of
  terminator artefacts (what the user reads, copies, and what the CSV/JSON export consumes). The
  parity suite pins the invariant with a **sentinel** (`assert not txt.endswith("\r")` on both sides).
- **Lone CR outside CRLF (classic Mac, `\r\r\n`)** — a **structural** divergence in line
  *segmentation*, not in text: `rg` separates records by `\n` only (a lone-CR file becomes **one
  giant line**), while Python in text mode treats CR as a break (**N lines**). No `rstrip` can fix
  the numbering; it is a pathological pre-OSX case and is **not chased** — it stays documented, and
  a dedicated test **pins** the divergence (`rg=1`, `Python=N`) so that "fixing" one side by accident
  becomes a regression.
- **Legacy encodings without BOM (Shift-JIS, GBK, EUC-KR…)** — here `rg` and the fallback **agree**:
  neither finds anything, because the search term is UTF-8 and the file is not. That is not a
  divergence, it is a shared limitation (of every Unix tool). **CJK in UTF-8** — both filenames and
  content — works 100% on both engines.

## Architecture

```
lfs/engine.py   # Qt-free core: Query/Match + rg (content) / fd (name) backends + Python fallback
lfs/boolean.py  # recursive-descent parser for boolean search (tokenizer → AST → sets)
lfs/app.py      # PySide6 GUI: form, live table, text/media preview, themes
lfs/cli.py      # CLI (same core)
lfs/fileops.py  # non-destructive copy: never moves, renames or deletes
lfs/disks.py    # destination capabilities: FAT/exFAT/NTFS/MTP and their limits
lfs/xdg.py      # mime types, "open with", default file manager
lfs/version.py  # build identity (is what is running what you think it is?)
install.sh      # universal multi-distro installer
packaging/      # build_deb.sh and build_appimage.sh
```

To build the packages yourself:

```bash
./packaging/build_deb.sh        # ~3 s, only needs dpkg-deb
./packaging/build_appimage.sh   # ~10 min the first time (downloads Python + PySide6)
```

## Requirements

- Python 3.9+ and **PySide6** (GUI).
- **ripgrep** and **fd** (recommended; without them, the Python fallback).
- Optional: **ripgrep-all** + **pandoc**/**poppler** (document mode); **QtMultimedia** (player).

## Care with SMR disks

Built to run over large archives, including **SMR** drives and external USB disks. SMR
(*Shingled Magnetic Recording*) writes overlapping tracks "like roof shingles": it reads well
sequentially, but suffers with random writes and, above all, with **concurrent reads** (the
heads start seeking and throughput collapses) — unlike conventional **CMR**, which rewrites in
place. The program is designed to spare those disks:

- it **never leaves an orphan `rg`/`fd`** sweeping the disk in the background (cancelling a
  search or closing the window kills the process);
- the **boolean AND narrows** the second term to the files the first one already found, reading
  far less from the disk;
- **`--one-file-system`** ("1 disk") avoids crossing into another mount by accident;
- **large images** are not decoded on the fly (which would stall on an SMR drive);
- **parallelism is disk-aware**: independent terms (`OR`) run in parallel on SSD/CMR, but the
  search is **serialised automatically** when any path lives under `/mnt` (or `/media`,
  `/run/media`) on a **rotational or unknown** device, sparing SMR from concurrent seeks. An
  SSD/NVMe mounted there (checked via `/sys/block/<dev>/queue/rotational`) is **not** penalised.
  The degree of parallelism is tunable through the **`LFS_WORKERS`** environment variable
  (default `3`; `LFS_WORKERS=1` serialises everything).

## Servers, NAS and network mounts

SFS runs both **on a desktop searching a NAS** (NFS/SMB/SSHFS mounts) and **on the server
itself** (headless, over SSH, across repositories of dozens of TB). What protects you there:

- **Dead-mount watchdog.** An NFS *hard mount* whose server is down freezes `stat()` in
  **uninterruptible D state** — not even `kill` helps, and an ordinary program hangs there with
  no remedy. Before descending into a **network** mount, SFS probes its liveness on a
  *throwaway thread* with a timeout; if it does not answer, the mount is **skipped with a visible
  warning** (never silently, never hanging). If a NAS dies **mid-search**, the result carries the
  warning — **honesty > completeness**.
- **Per-mount I/O class.** Network does not serialise like SMR, but it must not hijack the pool
  either: each network mount gets its own worker ceiling, so a slow link cannot drown out the
  search on local disks. `gvfs` (phones/cameras) and `autofs` stay **out of "search everywhere"**
  by default — they only join if you give the explicit path (otherwise "search `/mnt`" would wake
  every automount in the house).
- **Filenames by protocol.** When **copying** to a network destination, SFS already knows what
  each one accepts: `nfs` is fully POSIX; `cifs`/`smb` forbids `: ? * < > |` and has no symlinks;
  `sshfs` has atomic rename. And it writes **at a measured pace** (as with USB sticks), because a
  slow CIFS/NFS builds up global writeback just the same.
- **Visible boundary.** A "search `/`" can list **up front** which mounts will be touched and of
  what class (disk/network/SMR) — a server with 40 mounts appreciates it.

**What SFS deliberately is NOT:** a **resident indexer** in the style of Everything/Recoll. Its
identity is a **live, stateless tool** — what it shows is what is on disk **now**, not a snapshot
of a database that may be stale. Where the system already has an index (`plocate`), SFS can lean
on it for speed — **but only under an explicit `--index`, and never silently** (it refuses when
coverage has holes; see above). **An indexing daemon of its own, no.** And it does not become a
web service: if you want remote search, use **SSH + `--json`**. (Same reason there is no Flatpak
— see *Installation*.)

And the **duplicate finder** (*Duplicates…* menu) **finds, shows and exports** groups of
byte-identical files — to CSV or JSON — but **never deletes them**. Not with a confirmation, not
"just to the trash", not "only the extra copies". *Reads and exports, never alters* is the whole
identity of the product, and a delete button would be the end of that argument: deciding which
copy dies belongs to the human, in their own file manager, with their eyes on the paths SFS showed
them. The dedup engine is **SFS's own code** (`lfs/dupes.py`), not a dependency on another project,
and it has no removal feature — nor should it ever gain one.

## License

**GNU GPL v3 or later** ([LICENSE](LICENSE)) — `SPDX-License-Identifier: GPL-3.0-or-later`.

Genuinely free software: use it, study it, modify it and redistribute it freely. The only
obligation is reciprocal — anyone distributing a modified version must distribute its source
under the same license. That is what stops someone from closing this work and reselling it as
their own product, and it is also what lets the project enter repositories like Flathub, Debian
and the AUR (a homemade license is accepted by none of them).

Copyright (C) 2026 Rodrigo Toledo. Distributed WITHOUT ANY WARRANTY.
