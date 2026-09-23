# Sombrero File Search — Technical Documentation

*Versão em português: [TECHNICAL_DOCUMENTATION.pt-BR.md](TECHNICAL_DOCUMENTATION.pt-BR.md).*

> Reference document for **evaluating and debugging** the project. It describes the architecture,
> each module, the data flow, the concurrency model, the boolean search grammar,
> the documents mode, the media player, the theme system and the per-distro dependency matrix.
>
> **Document version:** 2026-09-22 (updated from 2026-07-14) · **Author:** Rodrigo Toledo (with Andrômeda/Claude)
>
> **Map of the 2026-09-22 update:** §1–§14 are the July document, corrected
> where it was wrong (§1, §2, §3.2, §5, §10, §11). The later phases are in
> **§15–§18 (F9)**, **§19 (F10)**, **§20 (F11)**, **§21 (F12)**, **§22 (review of
> 09-2026-09-21-22)** and **§23 (handoff × code, open items)**. Where an old passage and a
> new one disagree, the new one wins.
> **License:** GNU GPL v3 or later (`SPDX-License-Identifier: GPL-3.0-or-later`)

---

## 1. Overview

**Sombrero File Search** is a **Linux-native** file searcher with no mandatory index
(there is an opt-in `--index` via plocate, §16), with **live** results, in the spirit of Windows'
*Agent Ransack / FileLocator Pro*. It searches
by **name** (glob/regex), by **content** (text/regex), with **boolean expressions**
(`(A OR B) AND C NOT D`) and **inside documents** (PDF/docx/epub/odt/zip). It has a
**PySide6** GUI and an equivalent **CLI** that reuses the same core.

The search engines are mature external binaries — **ripgrep** (`rg`) for content and **fd**
for names — with a **pure-Python fallback** when they are absent, guaranteeing it runs on
any distro. The documents mode uses **ripgrep-all** (`rga`).

### 1.1 Why it exists

- Windows searchers (FileLocator, Everything, UltraSearch) read the NTFS MFT/USN, which
  **does not exist on Linux**; under Wine they only see the prefix. They are useless here.
- Practical origin: the Cinnamon menu was slow because an override of the
  `menu@cinnamon.org` applet did a **synchronous** file search over `/home` and `/mnt` on every keystroke.
  The function was reimplemented here **asynchronously** (thread), without freezing the interface.

### 1.2 Design principles

1. **Qt-free core** (`engine.py`, `boolean.py`) — testable and reusable by both the GUI and the CLI.
2. **External engines, never reimplemented** — portable and maintained by third parties.
3. **Graceful degradation** — without `rg`/`fd`, it falls back to Python; without `rga`, no documents mode;
   without `QtMultimedia`, no player (images still work).
4. **Streaming** — results show up during the search; never block the UI thread.
5. **"Search everything" by default** — `--no-ignore` and hidden files toggleable, like Agent Ransack.
6. **Honesty over completeness** — whatever was left out is STATED, with a reason, in a single funnel
   (§20.3); "0 results" only when that is true.
7. **Reads and exports, never modifies** — non-destructive copy by construction (§17), duplicates
   with no removal API (§19.6).
8. **CLI in English (automation contract), GUI in the user's language**; worldwide reach —
   names and contents in legacy encodings from any region are found (§22.2).

---

## 2. File structure

```
sombrero-file-search/
├── README.md / README.pt-BR.md, MANUAL.md / MANUAL.pt-BR.md   # what the USER needs
├── LICENSE (GPL-3.0-or-later), install.sh, requirements.txt (PySide6>=6.5)
├── VERSION ($Format:%h (%cs)$, filled in by git archive), .gitattributes, .gitignore
├── lfs/                     # code (15 modules; only app.py imports Qt)
├── tests/                   # standalone scripts + 2 shell install matrices
├── packaging/               # build_deb.sh, build_appimage.sh
├── assets/                  # icon.svg, icon{,_48,_64,_128,_256}.png, demo.gif, social_preview.png…
└── docs/                    # for CONTRIBUTORS (guide in docs/README.md)
    ├── DOCUMENTACAO_TECNICA.md (this file)
    ├── campo/               # field tests with raw evidence
    │   ├── 2026-07-bazzite-install.md
    │   └── 2026-09-22-nas-truenas/
    └── historico/           # development log: BRIEFING, HANDOFF_*, REVISAO_PEDIDO_*,
                             #   VEREDITO_*, BRANDING_PROMPTS (reorganized out of the root on 2026-09-22)
```

The launcher no longer lives in the root: `install.sh` generates `sombrero-file-search` (GUI) and
`sfs` (CLI, alias `lfs`) in `~/.local/bin`.

### 2.1 `lfs/`

| Module | Role |
|---|---|
| `engine.py` | Qt-free core: `Query`/`Match`, rg/fd/rga detection (`_which`), fd/rg/Python iterators, root plan and gate (F12 `planejar_raizes`, F9a `_live_roots`), per-disk partitioning (F11), snapshots + dedup (`_Entrega`/`_Colapso`), incompleteness funnel, legacy encodings and NFC/NFD, classification of user mounts (`classifica_montagens`, `user_mounts`, `network_mounts`), `search()` |
| `boolean.py` | Boolean search: `tokenize` → `parse` (AST `Term/Not/And/Or`) → sets with `rg -l` (progressive AND, parallel OR with a per-disk lock, `_Phase`), `_display_lines`, `search_boolean()`; same F9a/F12 gate |
| `disks.py` | Disk topology, stdlib only: mount by path, `rotational`, `path_needs_serial`, `search_profile` → `IOProfile`, `mount_status`/`mount_alive` probe in a child process, `mounts_under`, `list_search_targets`, destination capabilities (`dest_caps`), removable/LUKS/eject, link speed |
| `cli.py` | `sfs` CLI (argparse, always in English): text, NDJSON (`--json`), grep-style exit, `--index`, `--nice-io` |
| `app.py` | PySide6 GUI: `MainWindow`, tabs (`SearchTab`), `SearchWorker`, `ResultModel`/`ResultFilterProxy`, text/media preview, copy (`CopyWorker`, `PreflightDialog`, `ConflictDialog`), `PropertiesDialog`, `DuplicatesPanel`/`DupWorker`, themes, "Discos ▾" menu (`preenche_menu_discos`) |
| `fileops.py` | Copy engine, **non-destructive by construction**: `preflight`, `probe_write`, `decide_strategy`, `copy_to` (§17) |
| `copyjobs.py` | Copy queue persisted in `config.json` (survives closing the app and `kill -9`) |
| `dupes.py` | Duplicate hunter (F10c): finds, shows and exports, **never deletes** (§19.6) |
| `searches.py` | Saved searches, history, CSV/JSON export (`celula_csv` anti-formula) |
| `resultfilter.py` | Filter over the results: a mini-language compiled into a pure predicate (`compile_filter`) |
| `indexed.py` | `--index` via plocate, opt-in, which **refuses** if there is any pruning (§16) |
| `humane.py` | `human_error()`: errno/exception → translated human sentence (§18) |
| `i18n.py` | `t()`, `set_lang`, `current_lang`; English is the source language; override via `SFS_LANG` (legacy `LFS_LANG`) |
| `xdg.py` | freedesktop integration: mime, "Open with" (`apps_for`, `launch`), file manager / `ShowItems` |
| `version.py` | Installed build (`build_info`, `deb_version`, `title_suffix` in the window title) |

### 2.2 `tests/`

All **standalone**: `python3 tests/<file>.py` from the root (the ones that import
`app.py` require the venv's Python, with PySide6). **Do not use `pytest`.** Each script exits ≠ 0
on failure; everything runs in a tempdir, without touching the collection.

| File | Covers |
|---|---|
| `test_audit.py` | Main suite: B1–B14, N1–N3, opt#1–#4, F7–F12 etc. (128 tests, own runner) |
| `test_cli_flags_2026_09_21.py` | `--max-size`, `--depth`, `--follow`; invalid values → exit 2; `--index --follow`; symlink loop |
| `test_correcoes_2026_09_10.py` | Findings from 09-10 (real and refuted), preview × engine identity, same-FS gap |
| `test_funil_incompleto.py` | `stats['incompleto']` as the single channel for loss of completeness |
| `test_honestidade.py` | Engine × loss-of-completeness table (negation, invalid root, truncation, cancellation) |
| `test_legado_mundo_2026_09_22.py` | Content in legacy encodings (14 languages/encodings), zero false hits, NFD, parity |
| `test_leva_motor_2026_09_09.py` | Physical disk as a set of platters (LVM/RAID/LUKS) |
| `test_montagens_opcao_b_2026_09_22.py` | Option B, Network section, probe with `statvfs`, network root without `stat` |
| `test_motor_falhou.py` | An engine that exits with an error does not turn into "nothing found" |
| `test_nome_legado_2026_09_22.py` | Name in a legacy encoding; 4+ globs without losing a non-UTF-8 name; NFD |
| `test_nome_nao_utf8_2026_09_21.py` | GUI: non-UTF-8 name readable; Open/Copy path land on the right file |
| `test_paralelo_por_disco.py` | Per-disk partitioning, streaming, shutdown; ostree bind |
| `test_parity_rg_python.py` | rg/fd × Python fallback parity (slow, ~3 min) |
| `test_revisao_fable_2026_09_21.py` | Regressions from the Fable review (45 checks) |
| `test_snapshots.py` / `test_snapshots_fallback.py` | Snapshot pruning in all three engines; "live first" + dedup |
| `test_topologias.py` | Disk classification on synthetic topologies |
| `soak_local.py`, `stress_local.py` | Memory soak (offscreen GUI) and stress on the metal — outside the fast suite |
| `dummy_nas.py` | Tool: fake FUSE NAS with controlled latency/hangs |
| `test_install_matrix.sh`, `test_install_matrix_containers.sh` | `install.sh` on simulated immutable systems and in containers (apt/dnf/pacman/zypper) |

### 2.3 Packaging and installation

| File | Role |
|---|---|
| `install.sh` | No root: static rg/fd/rga/pandoc in user space first (package manager as the alternative; never `sudo` on ostree), system PySide6 or a venv, copies `lfs/` + `assets/`, generates launchers, icons and `.desktop`; migrates from the old name |
| `packaging/build_deb.sh` | Lean `.deb` (`Depends: python3`, rg/fd as Recommends) |
| `packaging/build_appimage.sh` | Self-contained AppImage (python-build-standalone + PySide6 + static rg/fd) |

---

## 3. Core — `lfs/engine.py`

A module with no Qt dependency. It defines the data types, detects binaries and implements four
search iterators (two by name, two by content) plus the public `search()` API.

### 3.1 Binary detection

```python
_APP_BIN = ~/.local/share/sombrero-file-search/bin   # bundled binaries (rga/pandoc)
_which(*names)   # shutil.which + fallback in _APP_BIN (os.access X_OK)
RG  = _which("rg")                    # ripgrep
FD  = _which("fd", "fdfind")          # fd (Debian/Mint rename it to fdfind!)
RGA = _which("rga", "ripgrep-all")    # ripgrep-all
engine_info() -> {"ripgrep":…, "fd":…, "rga":…}   # text "(ausente …)" if missing
```

`_which` looks **in PATH first** and then in the bundled-binaries directory, so that
the installer can supply static `rga`/`pandoc` without root.

### 3.2 Data types

**`Query`** (dataclass) — all the search parameters:

| Field | Type | Meaning |
|---|---|---|
| `paths` | `list[str]` | folders to search in |
| `name_patterns` | `list[str]` | globs (list) OR 1 regex |
| `name_is_regex` | `bool` | interpret `name_patterns[0]` as a regex |
| `content` | `str` | text/regex to contain (empty ⇒ name-only search) |
| `content_is_regex` | `bool` | content is a regex (otherwise `--fixed-strings`) |
| `documents` | `bool` | search inside documents via `rga` (F4) |
| `case_sensitive` | `bool` | case sensitive (insensitive by default) |
| `whole_word` | `bool` | whole word (`--word-regexp`) |
| `recursive` | `bool` | descends into subfolders |
| `max_depth` | `int?` | maximum depth |
| `include_hidden` | `bool` | includes hidden files |
| `follow_symlinks` | `bool` | follows links |
| `respect_gitignore` | `bool` | `False` = search everything (`--no-ignore`) |
| `one_file_system` | `bool` | does not cross mounts (`--one-file-system`) |
| `min_size`/`max_size` | `int?` | bytes |
| `modified_after`/`modified_before` | `float?` | epoch |
| `max_results` | `int` | cap (default 100000) |
| `skip_snapshots` | `bool` | prunes snapshot trees (F11, default `True`; §20.1) |
| `excluded_paths` | `tuple` | dead mounts under the roots, which no engine touches (F12b, §21.5) |
| `rg_threads` | `int?` | pool inside rg (boolean per disk group, §20.2) |

**`Match`** (dataclass) — one result: `path`, `size`, `mtime`, `is_dir`, `lines:
list[(lineno, text)]` (up to 200; **logical** text, without `\r\n` — the CRLF contract of 07-23),
`nmatch` (number of matches), `ident` (`(st_dev, st_ino)` from lstat), `snapshot` (source
tree, or `None` = live tree) and `copies` (identical copies absorbed by the dedup, §20.1).

### 3.3 Common filters

- `_name_matcher(q)` → returns `function(basename)->bool` (regex or list of globs;
  case-insensitive by default, à la Agent Ransack).
- `_passes_meta(q, st)` → applies min/max size and modified_after/before over an `os.stat_result`.

### 3.4 NAME search

- **`_iter_names_fd(q, cancel)`** — uses `fd`/`fdfind`. One `fd` process **per glob** (multi-glob),
  with `--absolute-path --type f`, plus gitignore/hidden/symlink/one-fs/depth flags. Deduplicates via
  `seen`. `stat` + `_passes_meta` per file. Cancellation via `proc.terminate()`.
- **`_iter_names_python(q)`** — universal fallback: `os.walk` with control over depth,
  hidden files, symlinks and metadata. Prunes `dns[:]` so it does not descend where it should not.

### 3.5 CONTENT search

- **`_iter_content_rg(q, cancel)`** — the main path. It builds `rg --json` (or `rga --json`
  in documents mode) and does **streaming event parsing**:
  - `begin` → resolves the path, applies the name-regex filter (the glob already goes to rg as `--glob`),
    `stat` + `_passes_meta`; stores `cur = Match(...)`. **In documents mode**, if the path is
    internal to a container (e.g. `package.zip/inner.pdf`) and has no `stat` on the FS, it emits
    `Match(path, 0, 0)` so as **not to lose the hit**.
  - `match` → accumulates `nmatch += len(submatches)` and keeps up to 200 lines `(line_number, text)`.
    `line_number` may come in as **`null`** (rga text adapters) → treated as `0`.
  - `end` → `yield cur`.
  - In documents mode it does **not** pass `--encoding auto` (rga already delivers UTF-8).
  - If the `Popen` fails (`OSError`), it falls back to the Python fallback.
- **`_iter_content_python(q, cancel)`** — walks names (via `_iter_names_python`) and does a "grep"
  in Python: reads line by line, aborts the file if it finds `\x00` (binary), accumulates lines/nmatch.

### 3.6 Public API

```python
search(q, on_result, cancel=lambda:False, on_progress=lambda n:None) -> (total, seconds)
```

It picks the iterator: if there is `content`, it uses `rg` (or `rga` for documents), otherwise Python; if it is a
name-only search, it uses `fd`, otherwise Python. It calls `on_result(Match)` in streaming fashion, `on_progress(n)` every
25, and respects `cancel()` and `max_results`.

---

## 4. Boolean search — `lfs/boolean.py` (signature feature, F3)

Implements `(A OR B) AND C NOT D` by resolving over **sets of files**.

### 4.1 Grammar and semantics

- **Terms**: a raw word (up to a space/operator/parenthesis) or `"in quotes"` (preserves spaces).
- **Operators**: `AND OR NOT` (words, case-insensitive) and the symbols `& && | || !`.
- **Adjacency** = implicit AND (`foo bar` ≡ `foo AND bar`).
- **Precedence**: `NOT` (unary) > `AND` > `OR`. Parentheses group.
- **Binary NOT**: `A NOT B` ≡ `A AND (NOT B)`.

### 4.2 Pipeline

```
expr ──tokenize──▶ tokens ──_P.parse (recursive descent)──▶ AST
AST ──_eval (sets)──▶ result files
files + positive terms ──_display_lines (rg --json)──▶ lines for the preview
```

**AST**: `Term(text)`, `Not(node)`, `And(a,b)`, `Or(a,b)`. Errors ⇒ `BooleanError(ValueError)`.

**Parser** (`_P`), recursive-descent grammar:
```
parse_or   := parse_and ( OR parse_and )*
parse_and  := parse_not ( (AND parse_not) | (NOT parse_not→Not) | (TERM|'(' →adjacency) )*
parse_not  := NOT parse_not | parse_atom
parse_atom := '(' parse_or ')' | TERM
```

### 4.3 Set-based evaluation

- **`_files_with_term(term, q, cancel)`** → `set` of files containing the term, via `rg -l`
  (fast); fallback `_files_with_term_py` (reuses `_iter_content_python`).
- **`_universe(q, cancel)`** → all candidates, via `rg --files` (or `_iter_names_python`).
  **It is only computed if there is a `NOT`** (lazy, via `universe_box`).
- **`_eval`**: `And` = intersection `&`, `Or` = union `|`, `Not` = `universe − set`.
  A per-term cache avoids re-querying the same text.
- **`_display_lines(pos_terms, files, q, cancel)`** — final pass: runs a single `rg --json`
  with all the **positive** terms (`positive_terms`, which ignores the negated ones) over only the
  result files, to fill in `Match.lines` for the preview.

`search_boolean(q, expr, on_result, cancel, on_progress) -> (total, seconds)` orchestrates everything,
applying `_passes_meta` at the end (size/date) and respecting `max_results`/`cancel`.

---

## 5. CLI — `lfs/cli.py`

The **`sfs`** command (alias `lfs`). Output is **always in English** (`i18n.set_lang("en")`: the
`detail` field of `--json` is an automation contract). First line on stderr:
`# engine: rg=… fd=… rga=…`.

| Flag | Effect (→ `Query` field) |
|---|---|
| `path…` (1+) | folders → `paths` |
| `-V`, `--version` | version + GPL notice, exits |
| `-n`, `--name TEXT` | name **contains** the term (`as_name_globs`); with `*`/`?` it is a glob over the whole name; **brackets only** (`[2019]`) searches both ways, glob and literal (2026-09-22); several separated by `,` or `;` → `name_patterns` |
| `--name-regex` / `--content-regex` | treat as a regex |
| `-c`, `--content TEXT` | text/regex to contain → `content` |
| `-b`, `--bool EXPR` | boolean search |
| `-D`, `--docs` | inside documents via `rga` (without rga: `# warning` and falls back to rg) |
| `-i`, `--ignore-case` | accepted, **no effect** (the default is already insensitive — §23.2) |
| `-s`, `--case-sensitive` | → `case_sensitive` |
| `-w`, `--word` | whole word → `whole_word` |
| `--hidden`, `--gitignore` | hidden files / respect `.gitignore` |
| `--one-fs` | does not cross mounts (and disables the F12 expansion) |
| `--snapshots` | always searches snapshot trees too → `skip_snapshots=False` |
| `--min-size SIZE`, `--max-size SIZE` | size (`500K`, `10M`, `1.5G`); invalid, or minimum > maximum → exit 2 |
| `--depth N` | maximum depth (1 = the given folder only); N < 1 → exit 2 |
| `--follow` | follows symlinks (a loop is cut, without any alarm) |
| `--days N` | modified in the last N days → `modified_after` |
| `-0`, `--print0` / `-l`, `--files-only` | NUL separator / paths only |
| `--json` | NDJSON: `{path,size,mtime,is_dir,nmatch,lines,snapshot,copies}`, `{copy,of,snapshot}` and `warn`/`error` (`mount_dead`, `denied`, `incomplete`, `index_used`, `index_coverage`, `boolean_expression`) |
| `--nice-io` | `nice 19` + `ionice -c 3` (children inherit it) |
| `--index` | name via plocate; refuses (exit 2) with `-c`/`-b`, `--follow`, without an index, or with pruned coverage |

**Output.** Raw name bytes (`os.fsencode`, safe for non-UTF-8); `--json` with
`surrogatepass`. **Exit codes:** 0 found something; 1 nothing; 2 usage error or **fatal** loss
(`resumo_incompleto`, §20.3); 130 Ctrl-C. A **closed pipe** (`| head`) cancels the search,
with no traceback. **Warnings on stderr:** `# warning: mount not responding`,
`# warning: N directories without permission`, `# note: N kernel filesystem(s) not searched`,
`# incomplete: …` and the final line `# N files · Xs`.

Examples:
```bash
sfs ~/projetos -n '*.py' -c "def main"
sfs ~/docs -c laudo --docs
sfs ~/notas -b '(nota OR laudo) AND paciente NOT rascunho'
sfs /dados -c erro -l --print0 | xargs -0 du -h
sfs /var/mnt/Toledo -n '*' --depth 2 --max-size 1M --json
```

---

## 6. GUI — `lfs/app.py` (PySide6)

### 6.1 Structure

- **`SearchWorker(QThread)`** — runs the search off the UI thread. Signals: `batch(list[Match])`,
  `progress(int)`, `done(int, float)`, `error(str)`. It **throttles** the results: it emits a
  batch every 100 ms **or** every 200 items (`_flush`). Boolean branch vs. engine branch; a `BooleanError`
  becomes an `error.emit` without breaking the thread. Cancellation via the `_cancel` flag.
- **`ResultModel(QAbstractTableModel)`** — columns File/Folder/Matches/Size/Modified.
  `append(matches)` uses `beginInsertRows` (incremental growth). Roles: Display, right alignment
  (count/size), ToolTip (full path), UserRole (the `Match`).
- **`MainWindow(QMainWindow)`** — builds the UI in `_build()`:
  - **Header** (`QFrame#header`): logo (icon_64), title/subtitle, **engine badges** (a green/gray
    dot per rg/fd/rga) and the **theme button**.
  - **Search bar**: content field (large) + `Search`/`Cancel`.
  - **Name + folder**: name glob, folder(s) separated by `;`, `Browse…` button.
  - **Option chips** (`QCheckBox` styled as pills): Aa, word, boolean, documents,
    content regex, name regex, subfolders, hidden, .gitignore, 1 disk, `Size ≥`, `Last N d`.
  - **Vertical splitter**: results table on top, **preview** at the bottom.
  - **Status bar** (QLabel).

### 6.2 Concurrency (flow)

```
start_search → _build_query → SearchWorker(q, boolexpr).start()
   worker.batch    → ResultModel.append   (the table grows live)
   worker.progress → status "N found · Xs"
   worker.error    → status "invalid expression: …"
   worker.done     → status "✔ N results · Xs"
Esc → cancels the search / clears the filter ; Ctrl+L focuses folders ; Ctrl+F focuses the filter ;
F3/Shift+F3 navigate matches in the preview ; ↑/↓ history ; Ctrl+R repeats ; Ctrl+T theme
```

The UI thread never does search I/O. `_cancel` is read by the iterator between items; external
processes get a `terminate()`.

### 6.3 Theme system

- `THEMES = {"dark": {...}, "light": {...}}` — palettes with ~15 keys (bg0..bg3, alt, border,
  txt, muted, accent, on_accent, green/amber/red…).
- `_STYLE_TMPL` — a Qt stylesheet with `{key}` placeholders; `build_style(pal)` does
  `.format(**pal)`.
- `apply_theme(name)` applies the stylesheet, adjusts the status and the button, and calls `_refresh_badges`.
- `toggle_theme()` flips it and **persists** it in `~/.config/sombrero-file-search/config.json`
  (`load_cfg`/`save_cfg`). The preference is read in `__init__`.
- **Debugging note:** the badges are rebuilt in `_refresh_badges`; when clearing the layout,
  use `w.setParent(None)` **before** `deleteLater()` (otherwise, in a headless `grab()`, the old
  widgets still show up overlapping the new set).

### 6.4 Text ↔ media preview (with player)

`_build_preview()` returns a **`QStackedWidget`** with two pages:

- **Page 0 — text** (monospaced `QPlainTextEdit`): shows the matched lines (`Match.lines`,
  with line numbers) or, if there are none, a "peek" at the first 80 lines of the file (aborts on
  binary).
- **Page 1 — media**: a `QFrame#mediastage` with an inner `QStackedWidget` of 3 screens
  (image `QLabel` / audio `♪` / video `QVideoWidget`) + a **transport bar**
  (`QFrame#mediabar`): `⏮` `▶/⏸` `⏭`, file name, **position slider** and time `m:ss / m:ss`.

Detection by extension in `media_kind(path)` → `"image" | "video" | "audio" | None`
(`_IMG_EXT`, `_VID_EXT`, `_AUD_EXT`). Routing in `on_select`:

- **image** (always, it is just `QtGui`): `QPixmap` scaled with `KeepAspectRatio`; rescaled on
  `resizeEvent`; transport disabled (label "image").
- **video/audio** (only if `HAS_MEDIA`): `QMediaPlayer` + `QAudioOutput` (+ `QVideoWidget` for video),
  `setSource` + `play()`. Signals: `playbackStateChanged` (▶/⏸ icon), `positionChanged`
  (slider+time, respecting scrubbing), `durationChanged` (range), `mediaStatusChanged` (auto-advances
  on `EndOfMedia`).
- **prev/next** (`_nav_media(±1)`): navigates between the **media rows** of the results
  (`_media_rows()`), with **wrap**; `selectRow` triggers `on_select`.

**Portability**: if `from PySide6.QtMultimedia import …` fails, `HAS_MEDIA=False` — images
keep working and audio/video fall back to the text preview.

### 6.5 Context actions

Context menu and double-click: **open file**, **open folder** (`QDesktopServices`),
**copy path(s)** (clipboard). Multi-selection is supported (up to 10 on "open").

---

## 7. Documents mode (F4) — ripgrep-all

`rga` exposes the **same CLI as rg** and, for PDF/docx/epub/odt/zip/tar, **extracts the text** and
passes it along in identical `--json`. That is why `engine._iter_content_rg` only swaps the binary
(`rg`→`rga`) and the rest of the parsing is reused. Adapters:

| Format | Adapter |
|---|---|
| PDF | poppler (`pdftotext`) |
| docx, epub, odt, html, ipynb | **pandoc** |
| zip, tar, gz | built into rga |

`line_number` may come in as `null` (text adapters) → treated as 0. A path internal to a
container has no `stat` → `Match(path, 0, 0)` so the hit is not lost.

---

## 8. Dependencies and per-distro matrix

| Dependency | Role | Mandatory? |
|---|---|---|
| Python ≥ 3.9 | runtime | yes |
| **PySide6** | GUI (brings QtMultimedia for the player) | yes (for the GUI) |
| **ripgrep** (`rg`) | content search | recommended (otherwise the Python fallback) |
| **fd** (`fd`/`fdfind`) | name search | recommended (otherwise the Python fallback) |
| **ripgrep-all** (`rga`) | documents mode | optional |
| **pandoc** | docx/epub/odt in rga | optional |
| **poppler** (`pdftotext`) | PDF text in rga | optional |

**Package name per manager:**

| Logical | apt (Debian/Ubuntu/Mint) | dnf (Fedora/RHEL) | pacman (Arch) | zypper (openSUSE) |
|---|---|---|---|---|
| ripgrep | `ripgrep` | `ripgrep` | `ripgrep` | `ripgrep` |
| fd | `fd-find` (bin `fdfind`) | `fd-find` | `fd` | `fd` |
| poppler | `poppler-utils` | `poppler-utils` | `poppler` | `poppler-tools` |
| ripgrep-all | `ripgrep-all`¹ | `ripgrep-all`¹ | `ripgrep-all` (AUR) | `ripgrep-all`¹ |
| pandoc | `pandoc` | `pandoc` | `pandoc` | `pandoc` |
| PySide6 | `python3-pyside6`² | `python3-pyside6`² | `pyside6` | `python3-PySide6` |

¹ Not every repository ships `ripgrep-all`; the installer then downloads the **static binary** (musl,
x86_64) from GitHub. ² If the system PySide6 is missing, the installer creates a **venv** and runs
`pip install PySide6`.

---

## 9. Installation

### 9.1 Universal installer (recommended)

```bash
./install.sh
```

Flow (5 steps): detects the package manager; **lists all dependencies and asks for confirmation**;
installs system packages (with `sudo`, only if authorized); downloads static `rga`+`pandoc` if
they are missing; prepares PySide6 (system or a venv in `$PREFIX/venv`); copies the app to
`~/.local/share/sombrero-file-search/`, creates the `sombrero-file-search` (GUI) and `lfs` (CLI) launchers,
hicolor icons and a `.desktop` entry. No root is needed for the app itself (everything under `~/.local`).

### 9.2 Manual

```bash
sudo apt install ripgrep fd-find poppler-utils   # Debian example
pip install PySide6
python3 lfs/app.py     # GUI    |    python3 lfs/cli.py --help    # CLI
```

---

## 10. Testing and debugging

- **Suite:** 17 standalone scripts in `tests/` (list and coverage in §2.2). Run each one with
  the venv's Python (`~/.local/share/sombrero-file-search/venv/bin/python tests/<file>.py`)
  — **not** with `pytest` (several call `sys.exit()` and pytest raises INTERNALERROR). The ones that
  import `app.py` need PySide6. `test_parity_rg_python.py` is the slow one (~3 min).
- **Field evidence** (real NAS, `--json` + kernel log): `docs/campo/`.
- **Module self-test**: `python3 lfs/engine.py <folder> <term>` and
  `python3 lfs/boolean.py <folder> '<expr>'` print the AST/results.
- **Headless GUI** (no display): `QT_QPA_PLATFORM=offscreen` + `MainWindow().grab().save(png)`
  to capture screens; populating `model.append([...])` with fabricated `Match` objects avoids depending on I/O.
- **Boolean edge cases already validated**: leading NOT, quotes, the `| & !` symbols, syntax error.
- **Player validated headless**: image/video/audio routing, transport enablement,
  prev/next navigation with wrap, return to the text preview.
- **Known pitfalls**:
  - `fd` becomes `fdfind` on Debian/Mint — handled in `_which`.
  - Claude Code's `rg` is a **shell function**, not a binary — `shutil.which` does not see it; install
    the real `ripgrep`.
  - `line_number` `null` in rga; a path internal to a container with no `stat`.
  - badges: `setParent(None)` before `deleteLater()` (see §6.3).

---

## 11. Limitations and backlog

- **F5 (tabs, saved searches, history, export) and F6 (`.deb`, AppImage) are implemented**
  (§19.4, §2.3) — they left the backlog. Flatpak remains discarded (the sandbox would fight
  reading the whole filesystem; rationale in `packaging/build_appimage.sh`).
- Pre-compiled `rga` only for `x86_64`; on other architectures, install it via the package manager.
- Preview highlighting and emphasis only apply to **literal** terms; content regexes are not highlighted.
- Column sorting is enabled at the end of the search (during the search, arrival order).
- User content regexes get no legacy-encoding variants and no NFD (§22.2).
- Small pending items raised on 2026-09-22: §23.2.

---

## 12. Quick symbol reference

| Module | Key symbols |
|---|---|
| `engine.py` | `Query`, `Match`, `search`, `engine_info`, `_which`, `_iter_content_rg`, `_iter_names_fd`, `_iter_content_python`, `_iter_names_python`, `_passes_meta`, `_name_matcher`, `_glob_to_regex`, `_merge_globs`, `_reap`, `_walk_onerror` |
| `boolean.py` | `parse`, `tokenize`, `search_boolean`, `positive_terms`, `_eval`, `_files_with_term`, `_universe`, `_display_lines`, `_term_set`, `_or_operands`, `_max_workers`, `_under_mount`, `_Phase`, `_all_terms`, `_reap_stats`, `_merge_denied`, `BooleanError`, `Term/Not/And/Or` |
| `cli.py` | `main` (argparse) |
| `app.py` | `MainWindow`, `SearchWorker`, `ResultModel`, `THEMES`, `build_style`, `media_kind`, `_build_preview`, `_show_media`, `_nav_media`, `apply_theme` |

---

## 13. Fable 5 audit — fixes applied

A debug audit (`LinuxFileSearch_Auditoria_Debug.md`, 2026-07-14) found 14
proven/under-review bugs plus optimizations. All the fixes below are
implemented and covered by `tests/test_audit.py` (whatever is not GUI) and by a
headless smoke test (GUI).

| # | Problem | Fix | Where |
|---|---|---|---|
| **B1** | orphan rg/fd when the search is cut off or abandoned (keeps walking `/mnt` in the background) | `try/finally` + `engine._reap()` (terminate→wait→kill, idempotent) | `engine._iter_content_rg`/`_iter_names_fd`; `boolean._files_with_term`/`_universe`/`_display_lines` |
| **B2** | case-sensitive name glob in rg (the contract is case-insensitive) | `--glob-case-insensitive` when `not case_sensitive` | `engine._iter_content_rg`, `boolean._rg_base` |
| **B3** | boolean mode ignored the REGEX name filter | `re.search` post-filter on the basename | `boolean.search_boolean` |
| **B4** | silent loss of lines due to ARG_MAX (60k paths → `{}`) | batches of ~400 paths per rg invocation, merging dicts | `boolean._display_lines` (`_BATCH`) |
| **B5** | crash when closing the window with a live search (`QThread destroyed`) | `closeEvent`: `cancel()` → `wait(3000)` → `_stop_media()` | `app.MainWindow.closeEvent` |
| **B6** | boolean + documents do not combine (illusion of searching inside PDFs) | ~~mutual exclusion in the GUI~~ **revoked**: boolean mode today searches inside documents via rga (terms, the NOT universe and the lines) — see the comment in `app._on_bool_toggled` | `app._on_bool_toggled` |
| **B7** | preview without term emphasis (signature feature) | amber `QTextEdit.ExtraSelection` over literal positive terms | `app._apply_highlight` |
| **B8** | no heartbeat/counters (a long search looks frozen) | 0.5 s `QTimer` + count of "inaccessible" items via `stderr` (`stats["denied"]`) | `app._heartbeat`; `engine._reap(..., stats)` |
| **B9** | `one_file_system` ignored in the Python fallback (crosses mounts) | compares the root's `st_dev` and prunes `dns` | `engine._iter_names_python` |
| **B10** | argv hygiene in fd (missing `--`) | `--` before the pattern and the paths | `engine._iter_names_fd` |
| **B11** | a new search did not stop the media | `_stop_media()` + preview back to page 0 | `app.start_search` |
| **B12** | a huge image decoded synchronously freezes the UI | `QImageReader.setScaledSize` (decodes already downscaled) + 64 MB cap | `app._load_image` |
| **B13** | video autoplay WITH AUDIO on selection (embarrassing) | starts **muted** by default; 🔇/🔊 button persisted in the config | `app._toggle_mute`, `cfg["muted"]` |
| **B14** | columns without sorting | `QSortFilterProxyModel` + numeric `SORT_ROLE`, wired up at the end of the search | `app.ResultModel.SORT_ROLE`, `app.proxy` |

**§5 optimization applied**: `parse_size` unified into `engine.parse_size`
(it was duplicated in `app.py` and `cli.py`); fd's `seen` only when there are multiple
patterns.

### 13.1 v2 verification (`LinuxFileSearch_v2_Verificacao.md`)

The re-audit by execution confirmed the 14 fixes and found two real issues,
already corrected:

| # | Problem | Fix | Where |
|---|---|---|---|
| **N1** | fd uses *smart-case*: with "Aa" ON, a lowercase pattern still matched `N1.TXT` (rg was sensitive → the engines diverged again) | forces `--case-sensitive` when `case_sensitive` | `engine._iter_names_fd` |
| **N2** | inaccessible-item counter missing in boolean mode (`stderr=DEVNULL`) and in the Python fallback (`os.walk` swallowed the errors) | stderr capture + thread-safe `_reap_stats`; `os.walk(onerror=…)` and file `PermissionError` | §13.6 |
| **N3** | the image cap only applied when the dimensions did not come from the header; a large PNG/TIFF with a header decoded the whole raster in the UI | **unconditional** 64 MB cap → "open externally" placeholder | `app._load_image` |

Remaining pending item (not urgent): N4 (review minutiae) — see §11.

### 13.2 Optimization #1 — AND with progressive restriction (implemented)

The biggest optimization from §3 of the audit. Before, each term of an `AND` walked the
**whole tree** with `rg -l`; now the partial result of the left side becomes the
`restrict` of the right side, which then walks **only those files** (in batches of
`_BATCH`, reusing the B4 mechanism). The leftmost term is the only full walk;
the following ones read just the accumulated set.

- **Where**: `boolean._eval` (propagates `restrict` through AND/OR/NOT), `boolean._term_set`
  (cache of the full set × restricted walk), `boolean._files_with_term(..., restrict=)`.
- **Correctness**: preserved because intersection distributes — `(X∘Y)∩R = (X∩R)∘(Y∩R)` —
  and an `AND` with an empty left side **short-circuits** (it does not walk the right one).
  The cache stores only FULL sets; restricted results never pollute it.
- **Gain**: in `rare AND common` over a large tree, the 2nd walk drops from
  *the whole tree* to *only the files of `rare`* — from minutes to milliseconds,
  and **far less disk I/O** (crucial on SMR — see §14).
- **Tests**: `test_and_progressive_correctness` (same results in AND/OR/NOT) and
  `test_and_progressive_restricts` (proves the 2nd part walked 1 file, not 51).

### 13.3 Optimization #2 — independent terms in parallel, with an SMR lock (implemented)

The operands of an `OR` are **independent** walks (none depends on the other),
so they run in parallel in a `ThreadPoolExecutor` — but **only when the disk can take it**.

- **Where**: `boolean._eval` gained the `pool` parameter; the `Or` branch flattens the chain
  (`_or_operands`) and does a `pool.submit` for each operand. `search_boolean` creates the pool
  only when `_max_workers(q) > 1`.
- **SMR lock** (`_max_workers` + `_path_needs_serial`): if **any** path of the search
  is under `/mnt`, `/media` or `/run/media` **on a rotational or unknown disk**,
  it returns **1 worker** (serial) — the heads of the same disk would fight over
  *seek*. Outside that (`~`, `/tmp`, SSD), it uses `_WORKERS` (3 by default, tunable via
  `LFS_WORKERS`). Matching is by **whole path component**, so `/mntx` does not
  count as `/mnt`.
- **v3 refinement — `rotational`** (Fable 5's final opinion): serializing ALL of `/mnt`
  needlessly penalized an SSD/NVMe mounted there. Now `_path_needs_serial` resolves
  the path → device node (longest-prefix mount in `/proc/mounts`, via
  `_dev_for_path`) → whole disk → reads `/sys/block/<disk>/queue/rotational` (`_rotational`,
  walking up from the partition to the disk). **`0` (SSD) allows parallelism even under `/mnt`**; `1`
  (rotational) or unknown (`None`) **serializes** — a safe default, since *drive-managed*
  SMR (the Seagate USB units) report themselves as ordinary disks and there is no honest
  SMR detection via sysfs. Validated on the real disks: `/mnt/optane`, `/mnt/SSD128Gb` (rot=0) →
  parallel; `/mnt/HDInternoBaixo`, `/mnt/DiscoQ` (rot=1) → serial.
- **No nested-pool deadlock**: submitted subtasks get `pool=None`, so
  only the `OR` level reached by the main thread parallelizes; an `OR` nested inside
  another does not try to grab more workers (which could lock up the pool with all
  workers waiting on workers).
- **Thread-safe**: cache and universe are protected by `_cache_lock`; the heavy I/O
  (`_files_with_term`/`_universe`) runs **outside** the lock and the write uses `setdefault`
  (in the worst race, it recomputes the identical value — idempotent).
- **Correctness preserved**: each parallel `_files_with_term` still `_reap`s its own
  process (B1), and opt#1 (the AND restriction) stays intact — the pool only distributes
  the `OR` siblings.
- **Tests**: `test_mnt_serializes` (mocks sysfs: rotational/unknown under
  `/mnt|/media|/run/media` serializes, **an SSD under `/mnt` parallelizes**, `/mntx` does not count,
  a mix containing a rotational drags everything to serial but an SSD-only mix does not) and
  `test_or_parallel_correctness` (parallel OR == serial OR, including OR inside AND/NOT).

### 13.4 Optimization #3 — fd multi-glob → one alternating regex (implemented)

In **name-only** mode, `fd` was invoked **once per glob** (a loop over `name_patterns`),
with dedup via `seen`. With N globs, that walked the tree **N times** — N× the I/O, bad
on SMR in particular. Now, when there are **>3 globs** (`_MERGE_GLOBS_MIN = 4`), they are
merged into a **single alternating regex** and **one single `fd`** runs.

- **Where**: `engine._glob_to_regex` (basename glob → regex anchored as `^…$`,
  equivalent to `fnmatch`: `*`→`.*`, `?`→`.`, `[...]` classes with `!`→`^`),
  `engine._merge_globs` (joins with `(?:a|b|…)`) and `engine._iter_names_fd` (decides
  whether to merge and swaps `--glob` for a regex).
- **Correctness**: the regex is anchored on both sides, so it matches the **whole basename**
  like the glob does. `test_glob_to_regex` compares case by case against `fnmatch.fnmatchcase`.
- **Safety guards**: it only merges **basename** globs (no `/` — a path glob
  stays in multi-fd mode, where `fd` matches the whole path); and the merged regex is
  **validated with `re.compile`** beforehand — if it fails, it falls back to the old path (one fd per
  glob). It never degrades silently into "nothing found".
- **`rg` did not need it**: in name+content mode, `rg` already receives all the `--glob`s
  in a **single process** (one pass); the N-walks problem was `fd`'s alone.
- **Gain**: searching `*.jpg *.png *.gif *.webp *.heic` over a collection goes from **5
  walks** to **1** — 5× less directory I/O (see §14).
- **Tests**: `test_glob_to_regex` (equivalence to fnmatch + rejection of globs containing `/`) and
  `test_fd_merge_single_pass` (5 globs → **only 1** `fd` process, correct union).

### 13.5 Optimization #4 — `on_phase` callback in boolean mode (implemented)

A heavy boolean search (`(note OR report) AND patient NOT draft`) performs several
`rg -l` walks — before, the UI only said "Searching…". Now
`search_boolean(..., on_phase=cb)` reports the stage: **"step 2/4: term 'patient'"**
and, at the end, **"step 4/4: extracting lines"**.

- **Where**: `boolean._Phase` (**thread-safe** step counter), `boolean._all_terms`
  (counts the distinct terms in the AST, positive and negated), `_eval`/`_term_set`/
  `_universe_cached` receive the `phase` and announce **only when they are about to walk the disk**
  (a cache hit is instantaneous and does not become a step). In the GUI: the `SearchWorker.phase`
  signal → `MainWindow.on_phase` → text in the status bar (shown by the B8 heartbeat).
- **Total steps**: distinct terms + 1 (the extraction of lines from the positives).
  Each term is announced **once** (dedup by name), even if opt#1 walks it
  restricted later.
- **Compatible with opt#2**: the counter is serialized by a `Lock` of its own, so the
  numbering comes out coherent even with the `OR`s evaluated in parallel (it is the I/O that runs
  concurrently, not the counting).
- **Backward compatible**: `on_phase` is optional (default `None`); the CLI, which calls
  `search_boolean(q, expr, out)`, stays the same.
- **Tests**: `test_on_phase_reports` (steps 1..total, correct total, last step is
  "extracting lines", each term once) and `test_on_phase_optional` (without the callback,
  the search works the same).

### 13.6 N2 — counting inaccessible items in boolean mode and in the fallbacks (implemented)

The "N inaccessible" counter (B8) only worked in simple search: **boolean**
mode passed `stderr=DEVNULL` and the Python fallback swallowed the errors from
`os.walk`. Now `stats['denied']` is filled in on every path.

- **Boolean mode**: `_files_with_term`, `_universe` and `_display_lines` now
  **capture stderr** (tempfile) and count via `_reap_stats`. `search_boolean` gained
  the `stats` parameter and propagates it through `_eval`/`_term_set`/`_universe_cached`. The GUI already
  passes `SearchWorker.stats`.
- **Thread-safe (opt#2)**: `_reap_stats` counts into a **local** dict per process and merges
  into the shared `stats` under `_cache_lock` (`_merge_denied`) — no race even with
  parallel `OR`s. The Python fallbacks use the same pattern (local → merge under lock).
- **Python fallback**: `engine._iter_names_python` now passes `onerror=_walk_onerror(stats)`
  to `os.walk` (counting directory `PermissionError`s), and `_iter_content_python` also counts
  the `PermissionError` when opening a file. `engine.search` forwards `stats` to those
  fallbacks (before, only the `rg`/`fd` path received it).
- **Backward compatible**: `stats` is optional (default `None`); whoever does not pass it (the CLI) does not count.
- **Tests**: `test_walk_onerror_counts_denied` (a `chmod 000` directory in the fallback counts
  ≥1) and `test_boolean_stats_denied` (boolean mode over the same tree fills in `denied`,
  where before it stayed 0). Both are skipped as root (which ignores permissions).

---

## 14. Care with SMR disks (and how they differ from CMR)

Sombrero File Search is built to run over large collections spread across many
HDDs — including **SMR** and external USB disks. That drives several engine decisions.

### 14.1 What SMR and CMR are

- **CMR** (*Conventional Magnetic Recording*, also PMR): the tracks **do not
  overlap**. Each sector can be rewritten in place. Random writes are
  predictable and fast. This is the "normal" disk.
- **SMR** (*Shingled Magnetic Recording*): the tracks are written **overlapping
  like roof shingles** (hence *shingled*), which raises density/capacity at a price:
  rewriting one sector forces rewriting the whole surrounding band (*zone*). The disk
  uses a cache zone (CMR) and does *garbage collection* afterwards. Practical
  consequences:
  - **Sequential reads**: similar to CMR (good).
  - **Random writes/rewrites**: can collapse to a few MB/s when the
    cache saturates, with **stalls** while the disk rearranges the shingles.
  - **Concurrent seeking** (several readers at once, or reading while writing)
    is especially bad: the heads start jumping around and real *throughput* drops a lot.
  - **Device-managed SMR** drives hide all of this from the OS — you cannot "see" the
    zone; you can only **avoid the bad access pattern**.

Many off-the-shelf high-capacity HDDs (and several external USB units) are SMR without
saying so on the box. In the ServidorCedro collection, the large mechanical disks tend to be
SMR; the reference CMR is the WD Purple (DiscoL).

### 14.2 How the program handles it

The principle is simple: **read the minimum, once, without unnecessary concurrency, and
never leave I/O hanging**. In practice:

- **No orphan rg/fd** (B1): a cut-off search or a window closed midway
  **kill the process** (`engine._reap`). Without that, an abandoned `rg` would keep
  walking the whole disk in the background — exactly the concurrent *seek* that
  kills SMR, and it would also compete with the collection's daemons.
- **AND with progressive restriction** (opt#1, §13.2): the second term of an `AND`
  reads **only the files the first one already selected**, not the whole tree. Fewer
  files opened = less I/O = less punishment on SMR.
- **Merged multi-glob** (opt#3, §13.4): searching for several file types
  (`*.jpg *.png *.gif …`) does **a single `fd` walk**, not one per pattern —
  N× less directory I/O on a disk that hates *seek*.
- **`--one-file-system` / the "1 disk" chip**: keeps the walk from **crossing into
  another mount point** unintentionally (honored in the Python fallback too — B9).
  Useful to keep the search inside a single USB disk and not wake up every drive.
- **A large image is not decoded synchronously** (B12/N3): 64 MB cap → placeholder.
  A 200 MB TIFF on SMR would take seconds to read and **freeze the UI**.
- **Streaming, not slurping**: the engine consumes rg/fd output line by line and emits
  results live; it does not accumulate the whole disk in memory before showing anything.
- **Metadata via `os.stat`** only on candidates that already passed the name filter —
  nothing is `stat`ed wholesale.

### 14.3 Conscious parallelism (opt#2, implemented)

Optimization **#2 (independent terms in parallel)** is already in the code (§13.3) and is
turned on **when the paths are NOT under `/mnt` / `/media` / `/run/media` on a
rotational/unknown disk**: on CMR/SSD, 2–3 concurrent `rg`s make use of the i7's CPU; on
SMR/rotational USB, concurrent *seek* would do more harm than good, so there the search stays
**serialized** on purpose (`_max_workers` returns 1). The **v3 refinement** looks at
sysfs's `rotational`, so an SSD/NVMe mounted under `/mnt` (e.g. `/mnt/optane`) is **not**
serialized for nothing — only the rotational one (or the unknown one, to be safe) is. This is the
project's golden rule: **parallelize where the disk can take it, serialize where it suffers**. The degree of
parallelism is tunable via `LFS_WORKERS` (default 3; `1` serializes everything).

---

## 15. F9a — Network mounts: classification and descent gate

Goal: **a dead network mount must never freeze the search nor leave it silent.**
Classify without touching the network, probe in a disposable process, skip with a warning.

### 15.1 Read classification — `disks.search_profile(path, mounts=None) -> IOProfile`

Pure: fstype of the longest-prefix mount + the device's `rotational`; it does not
probe the network. `mounts` is injectable for the tests.

| `klass` | When | `is_network` | `max_workers` | `enumerate_default` |
|---|---|---|---|---|
| `network` | fstype in `_NET_FSTYPES` (nfs/nfs4/cifs/smb3/smbfs/smb, sshfs, davfs/webdav, 9p, virtiofs, ncpfs, afs, gluster, lustre, ceph, beegfs) | yes | `NET_WORKERS_PER_MOUNT` = 4 | yes |
| `gvfs` | `fuse.gvfsd-fuse`; **and MTP too** (`_MTP_FSTYPES`: jmtpfs, simple-mtpfs, mtpfs) | yes | 4 | **no** |
| `autofs` | `autofs` (the placeholder would wake up every automount) | yes | 4 | **no** |
| `rotational` | `rotational=1` on any prefix; or unknown under `/mnt`, `/media`, `/run/media`, `/var/mnt` | no | global pool | yes |
| `ssd` / `unknown` | `rotational=0`; or no `/dev/*` node (app FUSE, tmpfs, ZFS) | no | global pool | yes |

`serialize` stays tied to the collection prefix (`_under_mount`) on purpose
(comment from 2026-09-08).

### 15.2 Liveness probe — `disks.mount_status(mp, timeout=3.0, _stat, _statvfs)`

Returns `'alive' | 'no_response' | 'broken_mount'`; `mount_alive()` is the boolean
wrapper (only `alive` = `True`).

- **Process, not thread (finding F1).** A `stat` on a dead NFS/FUSE sits in uninterruptible
  D-state; a stuck thread prevents `exit_group` and the CLI turns into a hanging
  zombie. The parent does `os.fork()`; the child closes **all** inherited fds except the
  write end of the pipe (finding R1: the stuck child held the parent's stdout and
  whoever read `--json` through a pipe never got EOF), does `_stat(mp)` + `_statvfs(mp)`,
  writes 1 byte (`A`/`D`) and `os._exit(0)`. The parent waits with `select` until the deadline and
  **abandons** the child that did not answer.
- **Opportunistic reap.** `_reap_abandoned()` does `waitpid(WNOHANG)` only on the PIDs that the
  function itself forked (`_abandoned_pids`), on every new probe.
- **2026-09-22: `stat` + `statvfs`.** The `stat` of the mount point was answered
  by the NFS/SMB client's **attribute cache** (measured, on a real NFS with the server
  powered off: "OK" in 0.0 s). `statvfs` goes to the server on every call (FSSTAT on
  NFS, QUERY_FS_INFO on SMB, statfs on the FUSE daemon): EIO in 9.1 s on a *soft* mount, hangs
  on a *hard* one — the deadline catches both.

| Child's result | Verdict |
|---|---|
| `stat` and `statvfs` OK | `alive` |
| `stat` → `_DEAD_MOUNT_ERRNOS` = {ENOTCONN, ESTALE, EHOSTDOWN, ENODEV} | `broken_mount` |
| `stat` → another errno (EACCES, EPERM, ENOENT, **EIO**) | `alive` (it answered) |
| `statvfs` → `_DEAD_STATVFS_ERRNOS` = the 4 above + {**EIO**, ETIMEDOUT, EHOSTUNREACH, ENETUNREACH, ECONNREFUSED, ECONNRESET, ECONNABORTED} | `broken_mount` |
| no byte within the deadline, or the pipe closed empty | `no_response` |

### 15.3 Where the probe runs

1. **`engine.planejar_raizes`** (F12, §21): each mount under a root becomes a root
   of its own; `stat` only on a local block disk — network and FUSE belong to the probe. Since
   2026-09-22 this applies to the typed root as well (a frozen TrueNAS NAS as the root
   used to hang for 150 s). With `--one-fs` there is no expansion, but every mount under the root is
   probed and the dead ones are condemned.
2. **`engine._live_roots(paths, stats, probe_timeout=3.0, …)`** — the gate. It probes the
   root if `prof.is_network` **or** if it came from the expansion (any class: a portal FUSE
   stuck in D hangs just the same). The existence test (`_raiz_existe`, H3) only runs
   **after** the probe. It fills in `classes` (root → `IOProfile`, used by
   `_jobs_para_classe`) and emits `root_scanning`.
3. **`engine._condena_montagem`** records the dead mount on three channels —
   `stats['skipped_mounts']` (`{path, mount, fstype, reason}`), the funnel
   (`dead_mount`) and the `root_skipped` event — and adds it to `mortas`, which becomes
   `Query.excluded_paths` (`_query_planejada`): no engine touches it, not even with a `stat`.
4. Both engines go through the gate: `engine.search` and `boolean.search_boolean`.

### 15.4 Visibility

- **Text CLI:** `# warning: mount not responding — skipped: <mount> (<fstype>)`,
  `# note: N kernel filesystem(s) not searched` and, from the funnel, `# incomplete: …`.
- **CLI `--json`:** `{"warn":"mount_dead","path","mount","fstype"}` and
  `{"warn":"incomplete",…}` in the same stream.
- **Exit code:** from `engine.resumo_incompleto` (§20.3).
- **`disks.list_search_targets(paths, probe_timeout=3.0, …)`** (pure, runs in a worker):
  which mounts the search is going to touch, with class and liveness (only for network ones); the same
  bind deduplication by `(st_dev, st_ino)`, only on local disks.
- **"Disks ▾" menu** (2026-09-22): local ones via Option B and Network in a separate section —
  see §22.3.

## 16. F9b — `--index` (plocate) and `--nice-io`

### 16.1 The rule (Fable's decision A, `lfs/indexed.py`)

**Explicit opt-in; pruning = a clear error; never automatic.**

1. The only trigger is `--index`, and only for name searches.
2. Coverage is checked **before** searching; a hole → refusal with `IndexError_`.
3. Zero candidates with intact coverage: trust the zero, with the index date visible.
4. Staleness: every candidate goes through `lstat` and only comes out if it still exists.

### 16.2 Coverage — `index_coverage(root, conf, mounts, include_hidden)`

`parse_updatedb_conf` reads `/etc/updatedb.conf` (shell quotes group: it strips the
quotes and splits the content — `shlex.split` would give a single token; bug fixed).

| Source of the hole | `reason` |
|---|---|
| root under a PRUNEPATH | `prunepath` |
| fstype of the root's mount in PRUNEFS | `prunefs:<fs>` |
| PRUNEPATH inside the root | `prunepath` |
| child mount (`disks.mounts_under`) with fstype in PRUNEFS | `prunefs:<fs>` |
| PRUNENAMES (R3), unless **all** of them start with `.` and the search does not include hidden items | `prunename` |

Coverage runs over the root's `realpath` (R4: plocate returns resolved
paths); the results come back translated to the typed prefix.

### 16.3 `search_indexed(q, …)`

- Refuses `q.content`.
- `plocate -0 -- <pattern>`; `_padrao_plocate` escapes `\ * ? [ ]` and asks for `<root>/*`
  when the root has a metacharacter (2026-09-21: `/acervo/[2019] Laudos` turned into a character
  class → a false zero).
- The same filters as the live search: subtree (`_under`), hidden component below the root
  (2026-09-21), `engine._name_matcher` (includes the legacy and NFD variants, §22.2),
  depth in fd's sense, `lstat`, `engine._passes_meta`.
- `_run`, `_lstat`, `mounts` and `_conf_text` are injectable.

### 16.4 Flow in the CLI

| Situation | Output |
|---|---|
| `--index` with content or boolean | `# error: …`, exit 2 |
| `--index --follow` (updatedb does not traverse symlinks) | exit 2 |
| plocate or `/var/lib/plocate/plocate.db` missing | exit 2 |
| OK | `# index: results as of the index built on <date>`; `{"warn":"index_used","index_date"}` in the json |
| coverage hole | `{"error":"index_coverage"}` / `# error:`, exit 2 |
| end | exit 0 found, 1 not found |

### 16.5 `--nice-io` (F9b §3.5)

`os.nice(19)` + `ionice -c 3 -p <pid>` (the `ionice` binary, if it exists — the stdlib has no
ioprio). The `rg`/`fd` children inherit both priorities; failures are swallowed.

## 17. F9c — Copy engine (`lfs/fileops.py`, `lfs/copyjobs.py`)

### 17.1 Principle

Non-destructive by construction: the source is opened only with `"rb"`; the module has no
delete/move/rename/chmod of the source. The only removal is `_rm_partial` (the partial file that
the process itself created at the destination). By default nothing is overwritten.

### 17.2 Destination capabilities — `disks.dest_caps(path) -> DestCaps`

`_caps_for(fstype, path, mountpoint)` is pure. On gvfs the profile comes from the **scheme** of the
first component (`mtp:host=…` → `mtp`), never from the fstype — the same
`fuse.gvfsd-fuse` serves mtp, sftp, smb and dav.

| Profile | fstypes / schemes | Limit | symlink | perms | times | forbidden charset | `net` |
|---|---|---|---|---|---|---|---|
| FAT32 | vfat, fat, msdos | 4 GiB−1 | no | no | yes | `"*:<>?\|` + DOS reserved names | – |
| exFAT | exfat, fuse.exfat | – | no | no | yes | same, without the reserved names | – |
| NTFS | ntfs, ntfs3, fuseblk, fuse.ntfs-3g | – | no | no | yes | same + reserved names | – |
| MTP | jmtpfs, simple-mtpfs, go-mtpfs, mtpfs; gvfs `mtp`/`gphoto2`/`afc` | – | no | no | **no** | same | – |
| NFS | nfs, nfs4, 9p, virtiofs | – | yes | yes | yes | – | yes |
| SMB | cifs, smb3, smbfs, smb; gvfs `smb-share` | – | no | no | yes | DOS | yes |
| SFTP | fuse.sshfs, sshfs; gvfs `sftp`/`ssh` | – | yes | yes | yes | – | yes |
| WebDAV | gvfs `dav`/`davs` | – | no | no | no | – | yes |
| network (conservative) | unknown gvfs scheme | – | no | no | no | – | yes |
| ISO9660 | iso9660 | – | yes | no | no | – | read-only |
| POSIX (default) | ext4, xfs, btrfs… | – | yes | yes | yes | – | – |

FAT/exFAT/NTFS/MTP carry `maxchars=255` (UTF-16 units; vfat's `f_namemax` says
1530 — measured on a real FAT32: 254 characters pass, 259 do not) and `utf8_only` (a non-UTF-8
name gives EINVAL on a real flash drive). `dest_caps` adds `namemax` and
`ST_RDONLY` from `statvfs`, `removable` (`is_removable`: the `removable` flag or a
USB bus, on any disk of a VG/RAID) and `link_mbits` (the lowest negotiated USB
speed). `DestCaps.name_problem` returns a stable key (`charset`,
`encoding`, `length`, `reserved`, `trailing`); `DestCaps.sanitize` only with "adapt
names" checked.

### 17.3 Preflight — `fileops.preflight(sources, dest_dir)`

It writes nothing into the collection (the only write is the probe):

- `disks.mount_ok`: under `/mnt`, `/media`, `/run/media`, `/var/mnt`, it requires a real
  mount (an empty folder would fill up the NVMe). Since 2026-09-21 it accepts NFS/SMB/ZFS — before, it required
  a `/dev/*` source and blocked copying to a NAS prior to F9c.
- `dest_caps`, `free_bytes`.
- `probe_write`: creates, writes 16 bytes, fsyncs and deletes `.sombrero-probe-<pid>-<hex>`
  — only if the mount exists and is not read-only.
- The strategy (§17.4).

The walk (`_walk_entries`) cuts cycles by `(st_dev, st_ino)`, does not descend into
the destination itself (`SKIP_LOOP`) and enumerates `too_big`, `bad_names` (component by
component), `links_degraded`, `links_broken`. `fits` requires
`free ≥ copy_bytes × 1.02` (excluding the `too_big` ones). `blocked` = mount missing,
read-only or `STRAT_BLOCKED`.

### 17.4 Strategies — `decide_strategy(caps, probe, has_gio)` (pure)

| Strategy | Condition | How it writes |
|---|---|---|
| `ATOMIC` | probe OK, profile with replace | `<name>.sombrero-part` → fsync → `os.replace` |
| `GUARDED` | probe OK, `label=="MTP"` without gvfs (jmtpfs) | part → fsync → `unlink(dst)` → `rename` |
| `GIO` | probe failed, `via_gvfs` (gvfs-MTP) and `gio` present | `gio copy -- src mtp://HOST/…` per file |
| `BLOCKED` | everything else | blocks before the first byte |

`_part_path` shortens the stem when `.sombrero-part` would blow past `namemax`/`maxchars`.
If the promotion fails, the part file is **not** deleted: the error cites its name, and it holds
the new content intact.

### 17.5 Write pacing

`BLOCK` = 4 MiB. With `caps.removable` **or** `caps.net` (F9c §4.2), `_copy_stream`
calls `_drain` every `PACE` = 16 MiB: `fdatasync` + `posix_fadvise(DONTNEED)` over the
written range (and over the source) — this limits global dirty pages and keeps progress
honest. Reference in the comment: a SanDisk Cruzer Fit on USB 2.0 at 11.8 MB/s; 512
MiB of *dirty* pages would be 46 s of stalling. An internal disk gets no pacing; every
file ends with an `fsync`.

### 17.6 MTP via gvfs (`_gio_copy`)

FUSE path → URI (`_mtp_uri`, components byte-encoded). Overwrite:
`gio remove` first. Cancel: `terminate` + `gio remove` of the partial file. `rc≠0` →
`OSError(EIO)`. Progress per whole file. The GUI warns when the strategy is
GIO and, on `net`, that the space estimate is not very reliable
(`PreflightDialog.strategy_note`).

### 17.7 Execution — `copy_to(sources, dest_dir, on_progress, on_conflict, cancel, sanitize_names, plan)`

- Without `on_conflict`: `skip`. Answers `skip` / `rename` (`name (1).ext`) /
  `overwrite` / `cancel`; a tuple with `True` applies to all.
- A collision created by the sanitize itself (`a?b` and `a*b` → `a_b`) is numbered (A3).
- `EFBIG` → `SKIP_TOO_BIG`; `ENOSPC` → stops the batch, `out_of_space`.
- Cancelling removes the partial file; `_apply_meta` (utime/chmod) only where `times`/`perms`
  exist; progress at most 10×/s.

### 17.8 Persistent queue and resume (`copyjobs.py`, F10b #5)

A job = `(sources, dest, sanitize)` in `config.json`, key `copy_queue`. `snapshot`
writes on each **transition** (queued/started/finished), not on each file;
`pending` validates and discards malformed entries; `clear` is the "Discard" action. Resuming is safe
because the copy is idempotent (ATOMIC never exposes a half-file; what is already finished becomes a
conflict → Skip; an orphan part file is recognizable garbage). In the GUI, `_maybe_resume_copies`
asks on startup; the `CopyWorker` is a single `QThread` per session (preflight →
dialog → `copy_to`).

## 18. Human errors — `lfs/humane.py` (F10b #6)

Every error string that reaches the screen goes through `human_error(err, context="",
target="")`; the raw errno and `strerror` are left for the log and `--json`. Buckets with an English
source phrase (translated in `i18n._PT`):

| Bucket | errnos | Category |
|---|---|---|
| network | ENOTCONN, EHOSTDOWN, EHOSTUNREACH, ENETUNREACH, ENETDOWN, ENETRESET, ECONNREFUSED, ECONNRESET, ECONNABORTED, ETIMEDOUT, ESTALE | `network` |
| space | ENOSPC, EDQUOT | `space` |
| the rest | EACCES/EPERM, ENOENT, EROFS, ENAMETOOLONG, EIO ("the disk may be failing"), EBUSY/ETXTBSY, EMFILE/ENFILE, EEXIST, EISDIR, ENOTDIR, ELOOP | `file` |

A context clause in `_CLAUSES[(context, cat)]` for `search`, `copy`, `mount`
(e.g. network + search → "The search continued in the other locations"). A non-`OSError` exception
passes its own text through; an `OSError` without an errno becomes the generic phrase. `SOURCE_STRINGS`
derives from the tables and feeds the i18n guard.

---

## 19. F10 — The final human mile, confidence and duplicates

### 19.1 F10a — Search narrative panel (`on_event`)

The engine narrates the search **per root** through the `on_event(ev, info)` callback,
accepted by `engine.search()` and `boolean.search_boolean()` (no-op by default). Since
H12 the boolean engine emits the **same** narrative (`_atribuidor` factored out for both
engines; `search_boolean` closes each root with `root_done`).

| Event | Payload | Emitter |
|---|---|---|
| `root_scanning` | `{path, klass, mountpoint}` | `_live_roots` when the root passes the gate; `_estende_snapshots` for the owner of a pruned tree |
| `root_skipped` | `{path, mount, fstype, klass, reason}` (+`erro` in partitioned mode) | `_raiz_existe`/`_raiz_montada` (`invalid_root`, `not_mounted`), `_condena_montagem` (`no_response`, `broken_mount`), `planejar_raizes` (`not_entered`), `_rodada._grupo_terminou` (`error`) |
| `root_done` | `{path, found}` | `_rodada`: in partitioned mode, **as soon as that group's disk finishes**; at the end, for whatever is left |
| `snapshots_skipped` / `snapshots_searched` | `{path, ostree, trees}` | `_plano_extensao` (§20.1) |
| `copy` | `{path, of, snapshot}` | `_Entrega.entrega` when dedup absorbs a copy (the GUI ignores it; `--json` publishes it) |

`engine.REASON_TEXTO` translates a `reason` into an EN-US sentence (the i18n key); the
GUI runs it through `t()` **at event time**, not at import time.

**GUI** (`MainWindow._on_root_event` / `_render_narrative`): `QFrame#narrative`
between the filter bar and the results, with a header
(`"{verb} {done}/{total} locations · {found} found · {sec}"`) and one line per root
with a dot (green = done, red = skipped, accent = scanning) and a class badge
(`_KLASS_TAG`: HD/SSD/MTP/auto/network). State (`tab.roots`, `tab.root_order`)
lives **in the tab**; a single widget only draws the visible tab; the volume label
(`disks.volume_label`) is resolved once, at event time — rendering does no I/O.
Dead mount = **red line in the panel, no popup**; a 0.5 s heartbeat updates the
clock. Snapshots show up as an annotation next to the root.

### 19.2 F10a — Filtering within the results (`lfs/resultfilter.py`)

Pure core, no I/O: `compile_filter(text) -> Predicate(name, path, mtime)`.

| Token | Semantics |
|---|---|
| space | AND (every term must match) |
| `*.odt` / `.odt` | extension, case-insensitive (`_EXT_RE`) |
| `>2019-01` / `<2020` / `>2019-01-05` | mtime after / before the **whole period** (`_period_bounds`) |
| anything else | substring in name **or** path, case-insensitive |

An invalid date (month 13) falls back to substring; an empty filter accepts
everything. In the GUI, `ResultFilterProxy(QSortFilterProxyModel)` applies the
predicate over the loaded `Match`, using `engine.nome_exibivel` (2026-09-22: "médico"
matches a non-UTF-8 name); natural ordering in `lessThan`; filter is **per tab**
(`tab.ed_filter`).

### 19.3 F10a — Keyboard end to end

The `QShortcut` objects are bound to the **window** (`MainWindow.__init__`), not to
the table — with tabs, the table changes underneath the shortcut.

| Key | Action |
|---|---|
| Esc | `_on_escape`: cancels if the tab is searching **or sitting in the SMR queue** (`tab.pending`); otherwise clears the filter |
| ↑ / ↓ in the Name field | `eventFilter` → `_history_step` (only when the field has focus) |
| Ctrl+F / Ctrl+L | focuses the tab's filter / the path field |
| F3 / Shift+F3 | `_preview_match(±1)`: steps through the matches in the preview |
| Ctrl+R | `repeat_last`: a "virgin" tab (`searches.is_empty`) uses the top of the history (2026-09-21 fix) |
| Ctrl+N / Ctrl+W | new tab / close tab |
| Ctrl+Return | `start_search(True)` |
| Ctrl+E / Ctrl+S | export / save the search |
| Ctrl+C, Ctrl+Shift+C, Alt+Return, Ctrl+T | copy selection, copy paths, properties, theme |

### 19.4 History, saved searches, tabs and export (`lfs/searches.py`)

- **Form snapshot:** `DEFAULTS` defines the keys; `normalize()` fills in the gaps and
  **discards** unknown keys (an older or newer config does not break anything).
  `"snapshots"` was added to `DEFAULTS` on 2026-09-21.
- **History:** `add_history` inserts at the top; repeating an entry **reorders** it
  without duplicating; cap `HISTORY_CAP = 30`; an empty form is not recorded.
- **Saved searches:** the same name **overwrites in place** (`save_search`);
  `delete_search`, `saved_list`.
- **Tabs:** `title_for(form, maxlen=22)` (name → content → last folder); during the
  search `"(n…)"` (`_tab_badge`); every `SearchWorker` signal carries its originating
  tab, so a background search writes only into that tab's model.
- **Export** (`export`): `.json` → JSON, everything else → CSV; writes to
  `path + ".sombrero-part"` and promotes it with `os.replace` (on failure the temporary
  file is deleted); `errors="surrogateescape"` (a non-UTF-8 name goes back to its
  original bytes). The GUI exports **in screen order** (sorted and filtered).
  - CSV (`export_csv`): `;`, one line per snippet,
    `path;folder;name;size;modified;matches;snapshot;copies;line;text`.
  - **Anti-formula** (`celula_csv`, 2026-09-21): a **text** cell starting with
    `= + - @ TAB CR` (`_CSV_GATILHOS`) gets a `'`; numbers are left intact; JSON raw.
  - JSON (`export_json`): one object per **file**, with `lines[]`, `snapshot`, `copies[]`.

### 19.5 F10b — After the copy: "safe to remove" and Eject

- `disks.removable_dest(path, mounts=None) -> (removable, mountpoint, dev)` (pure):
  `is_removable` = `removable=1` flag **or** USB bus, on any disk of the volume
  (`_sys_disks`).
- `disks.luks_backing(dev, sysfs=…)`: an open dm-crypt (`dm/uuid` "CRYPT-" + a single
  `slaves/`) → `/dev/<encrypted partition>`; otherwise `None`.
- `disks.eject_command(mp, dev, *, which=None, backing=None)` → **a list of STEPS**
  or `None`: with `gio`, `[["gio","mount","-e",mp]]` (one step: flush, lock the LUKS,
  power off); without `gio`, `udisksctl unmount` → `lock` (LUKS only) → `power-off`;
  with neither, `None` and the button does not appear.
- **GUI:** `on_copy_done` keeps `_safe_eject` if the copy actually wrote something, did
  not stop for lack of space, the destination is removable and a command exists;
  `on_copy_all_done` keeps *"Copied and synced — safe to remove."* with **⏏ Eject**
  (the sentence rests on ATOMIC's per-file `fsync`). `_eject_dest` runs the steps in
  order (`timeout=30` each) and stops at the first error; if `unmount` succeeded and
  `power-off` failed, it says the device can already be pulled.
- A copy longer than 30 s with the window minimized/inactive → `_notify` (`notify-send`,
  else the Qt tray, else silence).
- Validated on real hardware (a flash drive with 2 LUKS + 1 ext4, 2026-09-21): udisks
  refuses to power off while a neighboring partition is mounted; `gio` ejects the
  **whole flash drive** (like Nautilus), unmounting and locking the neighbors.

### 19.6 F10c — Duplicate hunter (`lfs/dupes.py`)

**Hard rule:** it finds, shows and exports; **there is no removal API**
(`test_dupes_no_delete_api` checks the AST).

Two entry points into the same `_dedup(cands, …)` funnel: `find_duplicates(roots)`
(`_walk`, `os.walk`) and `find_duplicates_in_files(files)` (`_collect`, exact list, no
descending into folders); `test_dupes_in_files_matches_walk` guarantees the same result.

| Stage | What it does | Constants |
|---|---|---|
| 0 — identity | collapses `(st_dev, st_ino)`: **hardlink = 1 candidate** with several `paths`; symlinks and zero-size files are out (`include_zero` turns them on); `min_size` | — |
| 1 — size | only those with ≥ 2 files of the same size | — |
| 2 — head | BLAKE2b of the first bytes, queued in `(dev, path)` order | `HEAD_BYTES` = 64 KiB, 16 B digest |
| 3 — full | full BLAKE2b, **sequential per device**, cancellation per block, progress in **bytes** | `FULL_BLOCK` = 1 MiB, 32 B digest |

- `_fadvise_dontneed` after reading (does not evict the cache of whoever is using the
  machine).
- 2026-09-21: `_head_and_full` — a head read that hits EOF (file < 64 KiB) already
  yields the full digest, with no reopen.
- Cancel → `[]`, no state left behind. `DupGroup` (`size`, `digest`, `members`,
  `wasted = size·(n−1)`) sorted by `wasted`; `summary()` → `(groups, bytes)`.
- **`name_verdicts(files, groups)`**: "copy vs. version" **with no new hashing** —
  collapses hardlinks via `lstat`, groups by basename → `IDENTICAL` / `DIVERGENT` /
  `MIXED` (a different size already means "version").
- **Export** (`dupes.export`): CSV `group,hash,size,path` (with `celula_csv` on the
  path) and JSON `hash,size,wasted,paths`, both `surrogateescape`.
- **GUI:** `DuplicatesPanel` = the "⧉ Duplicates" page of the `workspace`;
  `DupWorker(roots=… | files=…)`; "results" mode builds the tree by name with
  🟢/🟠/🟡 badges; "wide scan", by content. The "Disks ▾" menu is shared with the
  search (`preenche_menu_discos`, 2026-09-22).

## 20. F11 — Snapshots, per-disk partitioned search and the incompleteness funnel

### 20.1 Snapshot trees: pruning, fallback and dedup

**Pruning** (`engine.EXCLUSOES_SNAPSHOT`) — globs **per path component**, not substrings
(`meus_timeshift_backups/` is not a victim):

`timeshift/snapshots*` · `timeshift-btrfs` · `.snapshots` · `.zfs/snapshot` · `@GMT-*` · `ostree/repo` · `ostree/deploy`

- `eh_snapshot(path)` matches the components in sequence; `_globs_snapshot()` generates
  `**/{m}/**` and `**/{m}` for fd's `--exclude` and rg's `!glob` — pruning happens **in
  the engine**, because the cost is the walk.
- Noise (`node_modules`, `.git`, `/nix/store`) **never** enters: system copies only.
- `_achados_snapshot(root)` → `(pattern, path)` for every tree the root hosts,
  **including on mounts below it** (via `user_mounts()`), derived from
  `EXCLUSOES_SNAPSHOT`. `tem_snapshot` is the `bool` of that. (On the TrueNAS NAS of
  2026-09-22: `.zfs/snapshot` exposed over SMB, skipped and annotated.)
- `_pula_snapshot(paths, base)`: a root pointing **inside** a snapshot turns pruning off
  **only within its own group** (F11 bug3).

**"Live first, pruned ones only if nothing turns up"** (decision of 2026-09-09):
`search()` and `search_boolean()` always run the live round **pruned**; afterwards
`_estende_snapshots` → `_plano_extensao` decides **per TYPED root**:

| Mode | Condition | Extend? | Reason in the funnel |
|---|---|---|---|
| `stopped` | the live round stopped (cap/cancellation) | no | `snapshots_skipped` |
| `requested` | `skip_snapshots=False` (`--snapshots` or the checkbox) | yes | `snapshots_searched` |
| `searched` | zero live hits in the typed root | yes | `snapshots_searched` |
| `skipped` | there was a live hit | no | `snapshots_skipped` |
| `no_fallback` | only a tree from `EXCLUSOES_SEM_FALLBACK` (`ostree/repo`) | never | `snapshots_skipped` |

Text in `_TEXTO_PODA[(type, mode)]` (type `ostree` when every pattern comes from
`_PADROES_OSTREE`). `_query_extensao`: the roots become the trees, pruning is off,
mounts under the tree are excluded (on ostree, `/var` is a bind of `deploy/<os>/var`).
`_arvores_podadas` ignores any tree under a dead/non-live mount and deduplicates by
`realpath`.

**Result dedup** (`_Colapso` inside `_Entrega`, shared by search, boolean, CLI and GUI):
- Identity: `Match.ident = (st_dev, st_ino)` from **lstat** (a symlink is a different
  object).
- Identical copy: `(live path, size, int(mtime))`; for a snapshot hit,
  `_caminho_vivo(path, tree, pattern)` reconstructs the live path from the layout
  (Timeshift `…/<date>/localhost/<rel>`, btrfs `@`/`@x`, snapper `<n>/snapshot`, ZFS,
  `@GMT-*`, `ostree/deploy/<os>/deploy/<hash>/`).
- First arrival wins: the **live one takes precedence by construction**; the absorbed one
  goes into `dono.copies` and the `copy` event is emitted; a snapshot hit gets
  `m.snapshot = <tree>`. GUI: "+N copies" on the name and the copies in the tooltip.
- Risk declared in the code: two different files at the same live path, with the same
  size and the same mtime second, will collapse.

### 20.2 Per-disk partitioned search

Motivation (comment in `engine.py`): a single `fd` with 10 roots has one global pool,
blind to the mounts — measured on the collection, 9 disks finished in < 1.4 s while the
4TB-Portable alone took 168 s.

| Piece | Role |
|---|---|
| `_chave_de_disco(root)` | identity of the **physical disk**: `("disco", frozenset(disks._sys_disks(dev)))`; ZFS → `("zpool", pool)`; composefs inherits via the `datadir` (`disks._backing_dev`); fallback `("dev", st_dev)` |
| `_grupos_por_disco(paths)` | roots on the same platter in the same group; intersecting sets (a VG across 2 PVs) are **merged**; no `stat` → isolated `("?", r)` group |
| `_separa_raizes_com_mortas` | a root with a dead mount underneath gets its own process (fd's `--exclude` anchors to the 1st root — F12b) |
| `_iter_particionado` | one thread per group (`sfs-disco-N`), queue with `_FILA_MAX = 4096` backpressure, `ao_fim(paths, stats)` **after** that group's hits; early exit → `terminate` in a loop for up to 5 s; a group with no `FIM` → `interrupted` (H9) |
| `_rodada` | 1 group → serial; more → partitioned; the same factory picks rg/rga/fd/Python (the Python fallback also partitions) |
| `_funde_stats` | sums the workers' stats; the funnel is **re-annotated** (H7), preserving `args` |

**Threads per process** (`_jobs_para_classe(classes, conteudo)` → fd/rg's `--threads`
and the boolean engine's `rg_threads`):

| Situation | jobs |
|---|---|
| network / gvfs / autofs | `disks.NET_WORKERS_PER_MOUNT` (4) |
| **content** (local) | `None` (engine default; a deep queue helps even on SMR) |
| name, profile `serialize=True` | 1 |
| name, `ssd` / `unknown` | `None` |
| `rotational` (`_JOBS_POR_CLASSE`) | 1 |

A mixed group takes the concrete minimum. Measurements cited in the comments: an NVMe
with `--threads 1` costs 12.5×; an SMR with 1.15 M inodes gains 21% with `--threads 1`;
an 8 TB SMR by name: 1 thread 38 s vs. pool 48 s; by content: pool 35 s, 4 threads
38 s, 1 thread 52 s.

**`path_needs_serial`** (a disk under `/mnt|/media|/run/media|/var/mnt` **and**
`rotational != "0"`, unknown = serial): in the GUI, `_serial_paths` → `_must_wait`
puts the tab in the queue (`tab.pending`, released by `_start_pending`); in the boolean
engine, `boolean._path_needs_serial` (a mirror kept for the mocks) feeds `_max_workers`
(the OR pool **per disk group**). `NOT` computes the universe per group (correct: the
partition is disjoint).

### 20.3 Single incompleteness funnel

Single channel: `stats["incompleto"]`, a list of `{motivo, onde, detalhe, n, args?}`.
The old channels (`denied`, `skipped_mounts`, `engine_errors`, `erros`) are still
populated, but they are a **view**, not the source.

- `anota_incompleto(stats, motivo, onde, detalhe, n, args)` aggregates by
  `(motivo, onde)`; cap `_INCOMPLETO_MAX = 200` (the overflow goes to
  `incompleto_omitidos`); `detalhe` truncated at `_DETALHE_MAX = 300`. `detalhe` is the
  **literal** EN-US sentence (the i18n key); whatever varies goes in `args`. The boolean
  engine uses `_anota` (the same thing, under `_cache_lock`).
- `texto_detalhe(e, tr)` translates first and only then applies `.format(**args)`.
- `resumo_incompleto(stats, tr) -> (fatal, lines)`: **the single source** for the GUI
  status bar and the CLI exit code. `fatal` = a reason in `MOTIVOS_GRAVES` **or** an
  entry flagged `grave` (`anota_incompleto(..., grave=True)`; the partitioned merge
  preserves the flag). One-page contract for scripts: `docs/FUNNEL_CONTRACT.md`.
- `MOTIVOS_GRAVES = {engine_failed, engine_missing, disk_failed, invalid_root, not_mounted}`
  — "the result may be **wrong**".

| Reason | Main origin | Fatal |
|---|---|---|
| `engine_failed` | `_reap`: rc ∉ {0,1,−15,143}, except when the complaint is only permissions/symlink loop, only a per-path error (`_RX_ERRO_MOTOR`, 2026-09-22), or the process was killed by us | ✔ |
| `engine_missing` | Popen failed (fd/rg, `boolean`) | ✔ |
| `disk_failed` | exception in an `_iter_particionado` worker | ✔ |
| `invalid_root` | `_raiz_existe`: does not exist or is not a folder | ✔ |
| `not_mounted` | `_raiz_montada`: it is in `/etc/fstab` and is not mounted | ✔ |
| `permission_denied` | stderr "ermission denied" (`_reap`), `_walk_onerror`, Python fallback | — |
| `read_error` | any other per-file stderr line; a read error in the fallback | — |
| `dead_mount` | `_condena_montagem` (gate); errno 107/116/112/19 in stderr (`_linha_de_montagem_morta`) | ✔ **only on the typed root** (sets the entry's `grave` flag, 2026-09-22); expanded under `/`: — |
| `mount_not_entered` | `planejar_raizes`: gvfs/autofs/MTP (`enumerate_default=False`) | — |
| `empty_mountpoint` | an empty mount slot that is not a mountpoint (a hint) | — |
| `stat_failed` | the engine listed it, `stat` failed (H5) | — |
| `batch_failed` | a boolean batch failed | — |
| `truncated` | `_Entrega` hit `max_results` | — |
| `interrupted` | the disk did not respond to cancellation in time (H9) | — |
| `snapshots_skipped` / `snapshots_searched` | `_plano_extensao` | — |

**How it surfaces:**
- **CLI:** each line becomes `# incomplete: …` on stderr; with a fatal reason,
  `results are INCOMPLETE — this is not 'nothing was found'`. Under `--json`,
  `{"warn"|"error": "incomplete", reason, where, detail, count}` ("error" when fatal),
  alongside `mount_dead`, `denied` and the `pruned_mounts` notes.
- **Exit codes** (grep style): **0** found something; **1** nothing; **2** fatal or a
  usage error (invalid size/depth, `--min-size` > `--max-size`, invalid boolean
  expression, `--index` failures); **130** Ctrl-C (`_main_protegido`). Permission denial
  does **not** change the code.
- **GUI:** `on_done` → `_funil_para_barra` (✔/⚠/■, up to 3 lines + `(+N more)`). Reasons
  the panel already draws for the root (`_MOTIVOS_NO_PAINEL`: snapshots_*, dead_mount,
  invalid_root, not_mounted, mount_not_entered) are dropped from the bar, but `grave` is
  computed over the **whole** funnel.

---

## 21. F12 — Root expansion

> Code: `engine.planejar_raizes`, `_live_roots`, `_query_planejada`,
> `_condena_montagem`, `_separa_raizes_com_mortas`, `_excludes_fd`,
> `rg_flags_comuns`, `_iter_names_python`; topology in `disks.mounts_under`,
> `search_profile`, `mount_status`. The two callers are identical:
> `engine.search()` and `boolean.search_boolean()`.

### 21.1 The problem

The F9a gate (`_live_roots`) only probed what the user **typed**: on a search in `/`,
the root passed as a local disk and `fd` descended on its own into a dead network
mount — the very freeze the gate exists to prevent (decision of 2026-09-09). F12 gives
a different meaning to "search in `/`" or "in `/mnt`": **everything living underneath,
including NFS/SMB**.

### 21.2 Pipeline (the same for simple and boolean search)

```
planejar_raizes(q.paths, q.one_file_system, stats, on_event, mortas=mortas)
      → (roots, expandidas, forca_one_fs)
_live_roots(roots, stats, ..., expandidas=expandidas, mortas=mortas)   # F9a gate per root
      → live roots
_query_planejada(q, roots, forca_one_fs, mortas)
      → Query(paths=roots, one_file_system |= forca_one_fs, excluded_paths=dead mounts under the roots)
_rodada(...) → _separa_raizes_com_mortas(_grupos_por_disco(roots), q.excluded_paths)
```

The boolean engine runs `parse(expr)` **before** `planejar_raizes` (2026-09-21): a
syntax error should not wait for every NAS to be probed.

### 21.3 `planejar_raizes(paths, one_fs, stats=None, on_event=..., mounts=None, mortas=None, probe_timeout=3.0)`

Returns `(roots, expandidas: set, forcar_one_fs: bool)`; `mounts` is injectable.

1. Removes duplicates from `paths`, preserving order.
2. If `disks` cannot be imported: returns `(roots, set(), False)`.
3. **Explicit `one_fs`** (`--one-fs` / "1 disk"): **no expansion**. Even so, every mount
   under the root that is not a pseudo-fs goes through `mount_status`; anything not
   `"alive"` is condemned (§21.5) — a walker with `--one-file-system` still `stat`s each
   mountpoint to compare `st_dev`, and that hangs in D-state (F12b).
4. **Expansion**, for each mount `mp` under each root:

| Condition | Treatment | Channel |
|---|---|---|
| already a typed root, or already seen | ignored | — |
| fstype in F12's `_PSEUDO_FS` (proc, sysfs, devtmpfs, devpts, cgroup/2, securityfs, pstore, efivarfs, bpf, debugfs, tracefs, configfs, fusectl, hugetlbfs, mqueue, binfmt_misc, nsfs, rpc_pipefs, selinuxfs) | pruned | `stats['pruned_mounts']` (a note; the CLI prints `# note: N kernel filesystem(s) not searched`) |
| `search_profile(mp).enumerate_default == False` (gvfs, autofs, MTP) | not entered | funnel `mount_not_entered` (non-fatal) + `root_skipped` `reason="not_entered"` |
| local block device and `st_dev(mp) == st_dev(parent root)` | bind of the **same FS**: does not become a root | — |
| everything else | candidate `(mp, ident)`; `ident = (st_dev, st_ino)` only if it is a local block device — network/FUSE keep `ident=None` and get **no `stat` at all** | — |

`tmpfs`, `squashfs` and `overlay` **stay** in the expansion ("there are real files
there"). A btrfs subvolume has its own `st_dev` and becomes a root.

5. **Bind of the same directory between siblings (ostree/Bazzite).** `/var` is a bind of
   `/sysroot/ostree/deploy/default/var`; both have an `st_dev` different from `/`'s
   (composefs), so `/var` was being scanned twice. Candidates with the same
   `(st_dev, st_ino)` identity enter **once**: the typed one wins; among expanded ones,
   the **shortest path** (`(len(mp), mp)`) — the name the user knows. Nothing is lost
   (the directory is scanned under the other name), which is why it does not go through
   the funnel.
6. The winners go into `roots` and `expandidas`; `forcar_one_fs = bool(expandidas)` —
   the parent's walker runs with `--one-file-system` so it does not enter them again.

**2026-09-22 (`dd85092`, real TrueNAS NAS):** the `stat` of the **root itself**
(`_st_dev(r)`, `_ident(r)`) ran before the probe; with the root being a frozen NAS, the
search hung (150 s measured). Now the root is only `stat`ed when `raiz_segura`
(`search_profile(r)` local and an fstype that does not start with `fuse`). Covered in
`test_montagens_opcao_b_2026_09_22.py` (the engine's own `stat` turns into a pitfall).

### 21.4 Gate for expanded roots (`_live_roots`)

- An expanded root is **always** probed, whatever its class (a portal FUSE stuck in D
  hangs just like an NFS): the test is `prof.is_network or root in expandidas`.
- A dead expanded root becomes `dead_mount` (non-fatal), not `invalid_root`; a live
  expanded root does not go through `_raiz_existe` (it is mounted by definition).

### 21.5 F12b — a dead mount is never touched (`Query.excluded_paths`)

`_condena_montagem` records the dead mount in `stats['skipped_mounts']`, in the funnel
(`dead_mount`, `"{fstype}: {status}"`), in the `root_skipped` event and in `mortas`,
which `_query_planejada` filters down to those **under** some live root and stores in
`Query.excluded_paths`.

| Engine | Mechanism | Where |
|---|---|---|
| `fd` | `--exclude '/<rel>'` relative to the root; fd 10.4 anchors `/x` only to the **first** root of the process (measured), so each root with a dead mount underneath gets **its own process** | `_excludes_fd`, `_separa_raizes_com_mortas` |
| `rg` | `--glob '!**<abs>'` (in rg 14.1 `!/abs` does not anchor — measured) | `rg_flags_comuns` |
| Python | prunes `os.walk`'s `dns[:]` **before** descending, with no `stat` | `_iter_names_python` |
| snapshots | the extension receives `excluded_paths` | `_query_extensao`, `_estende_snapshots` |

Late detection in `_reap`: a stderr line carrying a dead-mount errno
(`_ERRNO_MONTAGEM_MORTA` = 107/116/112/19, `_linha_de_montagem_morta`) becomes
`dead_mount` for that path, not `read_error`.

### 21.6 Declared gap

`test_diferenca_conhecida_preview_lista_montagem_do_mesmo_fs`
(`test_correcoes_2026_09_10.py`) pins this down on purpose: the
`disks.list_search_targets` preview does **not** apply the "same `st_dev` as the parent"
rule, so the preview's number may be **larger** than the number of effective roots.

### 21.7 Tests

`test_audit.py` (`test_planejar_expande_montagens`, `test_excluded_paths_todos_os_backends`),
`test_paralelo_por_disco.py` (ostree bind), `test_correcoes_2026_09_10.py`
(identity shared with the preview, the §21.6 gap),
`test_revisao_fable_2026_09_21.py` (parse before the gate),
`test_montagens_opcao_b_2026_09_22.py` (network root with no `stat`).

---

## 22. Review of 21–2026-09-22 (Fable + fix session)

Fable's review report (2026-09-21, 17 defects, 3 commits) followed by a series of
items, one at a time, each with a test that **fails** on the previous code. Full
flow, with measurements, in the field report and in commits `50c2cf9`…`7179468`.
Raw evidence of the test with a real NAS in `docs/campo/2026-09-22-nas-truenas/`.

### 22.1 Engine and cancellation (`engine.py`)

| Change | Where | Why (measured) |
|---|---|---|
| Watchdog thread per fd/rg process calls `terminate()` when `cancel()` turns True | `_vigia_cancel` | `cancel` was only seen between pipe reads; on Toledo, cold cache: 8.15 s → 1.02 s |
| Death by a signal WE sent is not a failure | `_reap` (`nos_matamos`) | kill −9 of a process in D-state turned into `engine_failed` |
| `rg --json` with `{"bytes": b64}` (non-UTF-8 path/line) | `_rg_caminho`, `_rg_linha` | a content hit in a non-UTF-8 name was silently dropped |
| Boolean reads `rg -l --null` as bytes | `boolean._le_caminhos_nul` | a mangled name turned into an invalid `restrict` → exit 2 |
| Symlink loop (`File system loop found`) is a benign complaint | `_reap` (`benigna`) | with `--follow`, "search engine failed" + exit 2 with no loss at all |
| A complaint about a PATH only (`<path>: … (os error N)`) is `read_error`, not `engine_failed` | `_reap` (`so_por_arquivo`) | 6 DOS reserved names that the NAS lists but will not open brought down the whole search |
| `_rodada` closes the generator in `try/finally` | `_rodada` | an exception in `on_result` (pipe, Ctrl-C) left fd/rg alive until GC |

### 22.2 Legacy encoding — content AND name, any language (`engine.py`)

Rodrigo's decision: always on, worldwide coverage. `LEGADAS` table (~30
encodings: Windows 1250–1258/874, ISO-8859-x, KOI8-R/U, DOS 850/866, Mac
Roman/Cyrillic; Shift-JIS/EUC-JP/GBK/Big5/EUC-KR only for a term with
ideograph/kana/hangul).

- **`legado_variantes(termo)`** → the BYTES the term would have in each encoding
  that can represent it, with case folding for the accented bytes
  (`(?-u:[\xC7\xE7])`). Always derived from the NFC form.
- **Criterion against false positives in UTF-8** (`_possivel_em_utf8`): the variant is
  included if it is impossible in valid UTF-8, or possible only at the edges but
  long (≥ 4 bytes) or anchored to an ASCII letter. "é" on its own (`E9`, the start
  of an ideograph) is left out. For a NAME, the criterion applies **per literal
  chunk between wildcards** (`_encs_do_glob`) — `*` anchors nothing.
- **`rg_padroes(termos, q)`**: single source of the pattern at the 3 points that
  call rg (content, term and the boolean's lines). ASCII term and user regex: as
  before (`--fixed-strings`/raw regex). Measured cost: +1% to +6%.
  **In the boolean, on a mechanical HD** (note 5 of Fable's review report 2), 5 accented terms,
  cold cache on every round, 2.3 GB of a Ren'Py game on Toledo (2026-09-22): median **11.4 s with
  variants × 12.0 s without** — noise; the unaccented control (same code in both modes) swung
  10.5–13.9 s. On a cold HD the time belongs to the disk; the byte regexes weigh on the CPU, which
  is waiting on the disk.
- **Name** (`_glob_to_regex(rust=True)`, `_merge_globs`): the fd dialect in which `*`
  matches ANY byte (`(?s-u:.)*`). It also fixed the merging of 4+ globs, which
  silently lost every non-UTF-8 name. A glob with a non-ASCII letter always goes to
  the merged regex (Unicode case — fd's glob only folds ASCII).
- **Python fallback** (`casa_legado`, `_name_matcher`): the same encodings —
  parity checked by `test_parity_rg_python.py`.
- **`formas_unicode`**: term and glob also in NFD form (macOS name).
- **Display**: the matched line in the encoding in which the term appears
  (`texto_para_termos`); with no term (name, preview), in the REGION's legacy
  encoding (`codificacao_legada`, from the locale; `SFS_LEGACY_ENCODING` forces it).
  cp1258 (Vietnamese) with a combining tone (`_forma_cp1258`) + NFC on output.

### 22.3 Mounts and network (`engine.py`, `disks.py`)

- **`classifica_montagens`** (Option B of the July reports): a user disk is the one
  that is NOT a system disk. `user_mounts()` (local) and `network_mounts()` (NFS,
  SMB, sshfs, WebDAV, rclone). The list of non-user fs is `_FS_NAO_USUARIO` —
  a name of its own: the homonymous `_PSEUDO_FS` from F12 overwrote it on import and
  zram/overlay with a `/dev` source passed as a disk (`7179468`).
- **`mount_status`**: the child does `stat` **and** `statvfs` — `stat` was being answered
  by the attribute cache with the server dead; `statvfs` goes to the server.
  `statvfs` errnos that mean "server is mute" → dead (`_DEAD_STATVFS_ERRNOS`).
- **`planejar_raizes`**: a network/FUSE root does not get a `stat` (the probe comes later).
- **`mount_ok`** no longer requires a `/dev/*` source (copying to a NAS/ZFS under /mnt).
- **Eject** (`eject_command` → STEPS; `luks_backing`): without `gio`, it unmounts →
  locks the LUKS → powers off; the GUI stops at the first failure and tells the truth.

Measured with a real TrueNAS (VM, SMB over the tailnet): frozen NAS → skipped in 3.4 s
with `dead_mount`; the kernel (cifs) stays mute for 180 s. **Testing with a "fresh"
NAS**: the second round is misleading, the client has already flagged the server.

### 22.4 CLI (`cli.py`)

- Speaks **English in any locale** (the `detail` of `--json` is an automation contract).
- `| head` and Ctrl-C exit cleanly (a closed pipe cancels the search; Ctrl-C → 130).
- New: `--max-size`, `--depth N` (≥ 1), `--follow`. An invalid size and a minimum >
  maximum = exit 2 (previously `--min-size 10X` was silently ignored). `--index --follow`
  is refused.

### 22.5 GUI (`app.py`)

- Ctrl+R in a virgin tab falls back to the last search in the history (`searches.is_empty`).
- Non-UTF-8 name: readable (region encoding), in **italics**, tooltip with the
  encoding (`nome_exibivel`, `nota_nome_antigo`) — table, filter, sorting,
  Properties, duplicates, preview, player, messages.
- Every local QUrl goes through `url_local()` (bytes → percent-encoding): Open,
  Open folder and the player were landing on a nonexistent file with `QUrl.fromLocalFile`.
- "Copy path" and the text of Ctrl+C/drag: terminal form
  (`caminho_para_shell`) for a non-UTF-8 name.
- "Disks ▾" menu: a single function `preenche_menu_discos`; a separate **Network**
  section, outside "All disks" (Rodrigo's decision).
- `_peek` only reads a regular file, at most 256 KiB (a FIFO froze the window).
- **Invisible characters in the name** (RLO and the other direction controls, ZWSP, WJ,
  BOM, soft hyphen — `engine._INVISIVEIS`): they show up as an `⟦RLO⟧` marker at the
  exact spot, in italics, with a tooltip (RLO made `fatura_\u202Etxt.exe` look like
  "fatura_exe.txt"); "copy path" writes them as `\u202E` in the terminal form.
  Name search ignores them (fd: optional invisibles between each letter of the regex,
  cost in the noise; Python/`--index`: `sem_invisiveis`). With this, **every basename
  glob goes to the merged regex** (the old 4-glob threshold is gone). Rodrigo's
  decisions; test `test_invisiveis_2026_09_22.py`.

### 22.6 Export and duplicates (`searches.py`, `dupes.py`)

- Formula-safe CSV (`celula_csv`: `= + - @ TAB CR` → `'`), search and
  duplicates; raw JSON. Rodrigo's decision (OWASP).
- `export` with `surrogateescape` + temporary file/`os.replace`.
- `snapshots` goes into `searches.DEFAULTS` (saved search and history remember the checkbox).
- Duplicates: a file < 64 KiB is read once (the full digest comes out of the head);
  head in `(dev, caminho)` order.

### 22.7 New tests

`test_revisao_fable_2026_09_21.py`, `test_cli_flags_2026_09_21.py`,
`test_nome_nao_utf8_2026_09_21.py`, `test_legado_mundo_2026_09_22.py`,
`test_nome_legado_2026_09_22.py`, `test_montagens_opcao_b_2026_09_22.py`, and
new cases in `test_audit.py` (Ctrl+R, CSV, eject in steps). All are
standalone scripts: `python3 tests/<file>.py`.

### 22.8 Open items

See §23.2 (includes the invisible characters in the name and the `-i` with no effect).

---

## 23. Handoff × code, and known pending items

Surveyed while updating this document (2026-09-22), reading the code against the
`HANDOFF_*.md` files (today in `docs/historico/`). **The code rules**; the handoffs are the history of the decision.

### 23.1 Where the handoff fell behind

| Topic | The handoff said | The code today |
|---|---|---|
| Network probe | `mount_alive` with `os.stat` in a daemon thread (HANDOFF_F9a) | fork + pipe (F1) and, since 2026-09-22, `stat` **+ `statvfs`** |
| EIO in the probe | "EIO stays alive" (HANDOFF_F9_F1F2) | holds for `stat`; in `statvfs`, EIO/ETIMEDOUT/connection errors = `broken_mount` |
| Who gets probed | "local roots pass straight through" (HANDOFF_F9_Avanco) | since F12, expanded ones of any class; gate also in `planejar_raizes` (including `--one-fs`) |
| Network destination on copy | network capabilities "delivered in July" | until 2026-09-21 `mount_ok` blocked NFS/CIFS/sshfs under `/mnt` (it required `/dev/*`) |
| MTP in search | not mentioned | classified as `gvfs` (`enumerate_default=False`) |
| Eject | "`gio mount -e` **or** `udisksctl power-off`" (HANDOFF_F10) | STEPS; without gio, it unmounts first and locks the LUKS (2026-09-21) |
| Duplicates, head | read "per size group" | single queue in `(dev, path)` order; < 64 KiB is not reopened (2026-09-21) |
| Decision B (flock between processes, `--no-serial-wait`) and `--no-index` | planned | **do not exist** in `lfs/*.py` |
| B6 (boolean × documents) | mutual exclusion in the GUI (July audit, §13) | revoked: the boolean combines with documents; the lock is gone |

### 23.2 Pending code items — outcome (2026-09-22)

| # | Pending item | Outcome |
|---|---|---|
| 1 | `-i/--ignore-case` accepted and ignored | ✅ now **beats `-s`** (explicit request) |
| 2 | `human_error(context="eject")` with no clause | ✅ `_CLAUSES[("eject", …)]` = "The disk was not ejected." (+ pt) |
| 3 | `dupes.export` wrote straight to the destination | ✅ temporary file + `os.replace` via **`searches.grava_atomico`** (single source for both exports; it lives outside `dupes.py`, whose hard rule forbids replace/unlink in the module). The separator stays `,` (do not change the format for people already using it) |
| 4 | `dupes.py` does not write `stats["incompleto"]` | **not a defect**: the duplicates bar already shows "N unreadable" via `denied`; there is no other loss to record |
| 5 | `mount_dead` with no `reason`; text always "not responding" | ✅ `reason` in `--json`; text "mount broken" when `broken_mount` |
| 6 | out-of-date comments (`_MOTIVOS_NO_PAINEL`, `raiz_invalida`) | ✅ fixed |
| 7 | `--index` with multiple roots printed before refusing | ✅ **all** roots are covered before the first result |
| 8 | autofs/gvfs probed under `--one-fs` | **known behavior, kept**: the walker itself with `--one-file-system` already does a `stat` on the mount point (that is how it compares `st_dev`), so removing the probe would not avoid waking the automount |
| 9 | invisible characters in the name | ✅ §22.5 |
| 10 | `test_audit.py` docstring suggested pytest | ✅ fixed |

Test for the pending items: `tests/test_pendencias_2026_09_22.py` (fails on the previous code).

### 23.3 Numbers quoted only in the handoffs (not re-verified)

115/115 tests, old commit SHAs, "Δ 0.0 MiB RSS" from the soak, "the CLI dies in
~3 s in 7/7" and "the parent exits in 1.04 s" (HANDOFF_F9_F1F2). The "0.7 ms per probe" of the
`--one-fs` branch is a code comment, not re-measured.
