# Sombrero File Search — User Manual

**Language:** **English** · [Português (BR)](MANUAL.pt-BR.md)

An **index-free** file searcher with **live** results, in the spirit of Windows'
*Agent Ransack / FileLocator Pro*, but native to Linux. The engine is **ripgrep**
(`rg`) for content and **fd** for names, with a pure-Python fallback when the
binaries are missing. Runs on any distro.

Two faces, one engine:

- **GUI** — `sombrero-file-search` (or *Sombrero File Search* in your menu).
- **CLI** — `lfs`, built for scripts and pipelines (`| xargs`, `| wc`, `| fzf`).

Whatever the GUI finds, the CLI finds too: they share the same engine.

**Interface language.** English is the source language and the fallback for every
locale that is not Portuguese, so the GUI is in English unless your system is set to
Portuguese; the CLI is English-only. To force it either way, regardless of the system
locale: `SFS_LANG=en sombrero-file-search` or `SFS_LANG=pt sombrero-file-search`.

---

## 1. Concepts common to both interfaces

**Search by NAME.** The term is *contained* in the name: `report` finds
`annual report.txt`. If you use glob wildcards (`*`, `?`, `[`), they apply as
typed: `*.pdf`, `IMG_????.jpg`, `[Rr]eport*`. Several patterns separated by commas
act as **OR**: `note,*.txt` matches either.

**Search by CONTENT.** Text or a regular expression the file must contain. Results
show the matching line (the GUI highlights the snippet; the CLI prints
`file:line:text`).

**BOOLEAN content search.** `(A OR B) AND C NOT D`. Also accepts the short forms
`|` `&` `!` and `"quotes"` for exact phrases. Precedence: `NOT` > `AND` > `OR`,
with parentheses to group. It resolves by **file sets** (one `rg -l` per term,
then combined), so it stays fast even on large collections.
Real example: `(invoice OR receipt) AND client NOT draft`.

**Inside documents.** The *docs* mode enables [ripgrep-all](https://github.com/phiresky/ripgrep-all)
(`rga`), which searches **inside** PDF, docx, epub, odt and zip files. Requires
`rga` (optional in every channel; `install.sh` downloads it, the AppImage does not bundle it).

**Filters** (apply to name, content and boolean searches):

| filter | what it does |
|---|---|
| minimum size | files ≥ N only (`10M`, `1G`, `500K`, or raw bytes) |
| last N days | modified within the last N days |
| case sensitive | search **ignores** case by default; turn on to distinguish |
| whole word | `note` won't match `notebook` |
| hidden | include files/folders starting with `.` |
| respect `.gitignore` | skip what `.gitignore` hides |
| don't cross mounts | don't descend into other mounted filesystems |
| name regex | treat the name term as a regex, not a glob |

**Don't cross mounts** (`--one-file-system`) is handy to search only the current
disk without entering USB drives/external disks mounted below the folder.

**Snapshots: live tree first, snapshot trees only if nothing.** Timeshift, snapper,
ZFS, Samba shadow copies and ostree deployments are copies of the system that can
multiply a walk tenfold, so they are pruned while the live tree is searched. If a
folder you typed comes back empty, the search extends itself to the snapshot trees
under it and says so; results from there are marked (tooltip in the GUI, `snapshot`
in exports and `--json`). Identical copies — same file, or same path + size + mtime
between the live tree and a snapshot — collapse into one row, live copy first, with
"+N copies". *Include snapshots* / `--snapshots` extends without waiting for an empty
result. Extending by name is cheap; by content it means reading each snapshot in full.

---

## 2. The GUI

### The form
At the top: the **Name** and **Content** fields, the **In** field (folders to
search, separated by `;`) and the filter toggles. **Search** starts; **Cancel**
stops (search is live — the table grows as it runs).

### Results and preview
The table lists *File · Folder · Size · Modified · Matches*. Click a column header
to sort. The preview panel shows:

- **Images** — a thumbnail.
- **Audio/video** — a player with transport (⏮ ▶/⏸ ⏭), a position slider and
  navigation between the media in the result set.
- **Text/code** — the matching lines, with the snippet **highlighted**.

### Search tabs *(F5)*
Each tab is an independent search: its own form and its own results. Switching
tabs restores **that** search's form — you never look at one search's results with
another search's form in front of you.

| shortcut | action |
|---|---|
| `Enter` | run the search (from any search field) |
| `Esc` | cancel a running search; with none running, clear the results filter |
| `↑` / `↓` | *(in the name field)* walk back/forward through your search history |
| `Ctrl+F` | jump to the **results filter** box |
| `Ctrl+L` | jump to the **paths** field (and select it) |
| `F3` / `Shift+F3` | next / previous match **inside the preview** |
| `Ctrl+R` | repeat the tab's search |
| `Ctrl+N` | new tab |
| `Ctrl+W` | close tab (the last one doesn't quit — it just empties) |
| `Ctrl+Enter` | search in a **new** tab (keeps the current one) |
| `Ctrl+S` / `Ctrl+E` | save current search / export results |
| `Ctrl+T` | toggle light / dark theme |
| `Ctrl+C` / `Ctrl+Shift+C` | copy selected file(s) / copy path(s) |
| `Alt+Enter` | properties of the selected result |

### Saved searches + history *(F5)*
In the **Searches ▾** menu (next to *Disks*):

- **Save current search** (`Ctrl+S`) — stores the **whole** form (not just the
  term: folders, filters, everything). Reopening reproduces the result. Saving
  with an existing name **overwrites** in place.
- **Recent** — your latest searches, de-duplicated (repeating moves it to the top).
- **Remove saved** / **Clear history**.

Opening a saved search **opens a new tab** — it doesn't replace what you're viewing.

A search saved with *include snapshots* ticked behaves differently since
September 2026: the box no longer means "one sweep with no pruning", it means
"always extend to the snapshot trees after the live one". The results are the
same files, now deduplicated, with the snapshot copies folded into the live row.

### Export results *(F5)*
**Searches ▾ → Export** (`Ctrl+E`) writes what's on screen, **in the order shown**
(if you sorted by size, the file comes out by size):

- **CSV** — one row per matched snippet, with a header and `;` delimiter (opens in
  a spreadsheet with two clicks). Columns:
  `path;folder;name;size;modified;matches;snapshot;copies;line;text` (`snapshot` = the
  snapshot tree the file came from, empty for the live tree; `copies` = identical copies
  collapsed into that row).
- **JSON** — one object per **file**, with the snippets nested (`jq -r '.[].path'`
  stays trivial) and the same `snapshot` / `copies` fields.

> **Column change (September 2026).** `snapshot` and `copies` were inserted
> **before** `line` and `text`. A script that reads the CSV by column *position*
> needs updating; one that reads it by header name does not.

The format is chosen by the filename's extension (`.json` → JSON, anything else → CSV).

### Copy files *(F7)*
Select results and either:

- **Drag** them to another app/file manager, or
- **Copy** them to a destination folder.

Before copying, LFS runs a **destination pre-check**: free space, the FAT32 4 GiB
file limit, filenames illegal on the destination filesystem, and whether the mount
is actually mounted. On a **USB stick / removable** drive the write is **paced**
(synced every 16 MiB) so it doesn't hijack the system's page cache and freeze the
machine — on an internal disk this doesn't happen, the kernel handles it well.

> **When two files collapse into one.** Two results are treated as the same file
> when they share an inode (hard link, bind mount, `rsync` between snapshots) or
> when the live path, the size and the whole second of the mtime all match. The
> declared trade-off: two genuinely different files at the same live path, with
> the same size and the same second, would collapse into one row. In practice
> that is the same file.

> **Never destroys the source.** LFS reads and copies; it never moves, renames or
> deletes the source. If a copy is cancelled, the partial destination is removed.

> **MTP devices (phones, media players).** Writing over a mounted MTP device
> (gvfs) is limited by the protocol itself; for those destinations, prefer the
> device's own app or `gio copy`.

### Theme
`Ctrl+T` toggles light/dark; the preference is saved.

---

## 3. The CLI — `lfs`

```
lfs [options] FOLDER [FOLDER ...]
```

One or more folders as positional arguments; the options say **what** to look for.
With no criteria, it lists everything under the folder(s) (like `ls -R` with filters).

### Options

| option | long form | what it does |
|---|---|---|
| `-n TERM` | `--name` | name CONTAINS the term; globs (`* ? [`) apply as typed; comma-separate several = OR |
| `-c TEXT` | `--content` | text/regex the file must contain |
| `-b EXPR` | `--bool` | boolean content search: `'(A OR B) AND C NOT D'` (`| & !` and quotes) |
| `-D` | `--docs` | search INSIDE documents (PDF/docx/epub/zip…) via `rga` |
| | `--name-regex` | treat `-n`'s term as a **regex** (not a glob) |
| | `--content-regex` | treat `-c`'s term as a regex |
| `-i` | `--ignore-case` | ignore case (already the default) |
| `-s` | `--case-sensitive` | distinguish upper/lower case |
| `-w` | `--word` | whole word |
| | `--hidden` | include hidden (`.`) entries |
| | `--gitignore` | respect `.gitignore` |
| | `--one-fs` | don't cross mount points |
| | `--min-size N` | minimum size (`10M`, `1G`, or bytes) |
| | `--days N` | modified within the last N days |
| | `--snapshots` | ALWAYS search snapshot trees too (by default only when the live tree gives nothing for that folder) |
| | `--json` | NDJSON for automation: one object per match, warnings in the same stream |
| | `--nice-io` | lower CPU + I/O priority (nice 19 + ionice idle) for cron/background searches |
| | `--index` | name search through the `plocate` index; refuses if the index has holes, every hit verified live |
| `-0` | `--print0` | separate paths with NUL (for `xargs -0`) |
| `-l` | `--files-only` | path only (no match lines) |
| `-V` | `--version` | version + license |
| `-h` | `--help` | help |

### Output and pipelines
- **Paths go to `stdout`**; the `# engine: …` header and the `# N files · Ns`
  footer go to `stderr`. So `2>/dev/null` gives you a clean, pipe-ready list.
- With `-l` you get just the path; without `-l`, content searches print
  `path:line:text`.
- With `-0` paths are NUL-separated — the safe way to pass names with spaces or
  newlines to `xargs -0`.
- With `--json` every line is one object: a match (`path`, `size`, `mtime`, `is_dir`,
  `nmatch`, `lines[]`, `snapshot`, `copies[]`), a `{"copy","of","snapshot"}` for a
  duplicate absorbed after its owner was printed, or a warning
  `{"warn"|"error": "incomplete", "reason", "where", "detail"}` — the `reason`
  identifiers are listed in the README.
- When the search could not look somewhere, `stderr` gets `# incomplete: …`; if the
  result may be *wrong* (root missing, disk not mounted, engine failed) the exit code is 2.

### Examples

```bash
# every PDF under ~/docs, paths only
lfs ~/docs -n '*.pdf' -l 2>/dev/null

# files containing "invoice" (shows the line)
lfs ~/docs -c invoice

# boolean, inside documents (PDF/docx…)
lfs ~/docs -D -b '(invoice OR receipt) AND client NOT draft' -l

# large videos modified in the last week
lfs /mnt/Disk -n '*.mp4,*.mkv' --min-size 500M --days 7 -l 2>/dev/null

# feed another command safely (names with spaces)
lfs ~/photos -n '*.jpg' -0 2>/dev/null | xargs -0 -n1 identify

# count how many files match
lfs ~/projects -c 'TODO' -l 2>/dev/null | wc -l

# pick interactively
lfs ~ -n '*.md' -l 2>/dev/null | fzf
```

### Notes
- Search is **case-insensitive by default**; use `-s` when case matters.
- **Exit code:** `0` found something, `1` nothing found, `2` the result may be wrong
  (a root that does not exist, a disk that should be mounted and is not, the engine
  failed) — grep-style. Losses that only make the result *incomplete* (a folder that
  denied reading) do not change it.
- `-n` uses globs by default; for a regular expression on the name, add
  `--name-regex` (e.g. `--name-regex -n 'IMG_\d{4}\.jpg$'`).

---

## 4. Installation (summary)

| | when to use | GUI |
|---|---|---|
| **AppImage** | any distro, nothing to install (Python + PySide6 + `rg` + `fd` bundled; `rga` not) | yes |
| **.deb** | Debian/Ubuntu/Mint, apt-integrated | needs PySide6 (`--setup-gui`) and `libgl1` on minimal systems |
| **install.sh** | any distro, installs into `~`, no root | uses the system's or builds a venv |

Details for each path and the optional dependencies (`rg`, `fd`, `rga`) are in
[`README.md`](README.md).

---

*Sombrero File Search — free software under the GNU GPL v3 or later. No index, no
service, no nag: you search, it finds.*
