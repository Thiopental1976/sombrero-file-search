# Changelog

All notable changes to **Sombrero File Search**. Dates are YYYY-MM-DD.
The project follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

Detailed rationale and measurements live in the commit messages and in
[`docs/TECHNICAL_DOCUMENTATION.md`](docs/TECHNICAL_DOCUMENTATION.md).

## [Unreleased]

### Added

- **Preview pane on the right, and it can be turned off.** The preview used to
  sit under the result list and take its height: with a photo or a video the
  list was left with a few rows. It now sits to the right, so the list keeps the
  whole window height and a portrait photo or phone video fills the tall pane.
  Drag the divider to size it — there is no low ceiling, on an ultrawide it can
  take half the screen; the list never shrinks below 420 px. In a tall window
  (portrait monitor, half a screen) the pane moves back to the bottom by itself,
  decided by the window's own proportions with a dead band so it does not flip
  while you resize near square; each position remembers its own size. The
  **Preview** button next to the tabs, `Alt+P`, the pane's `×` or dragging the
  divider shut turn it off — off, nothing is read from disk for it. Images are
  re-read at the pane's size when it grows, so they stay sharp.
- **The disk list has a divider.** It still scrolls within 7 lines by default;
  pull the divider to see more disks at once. The choice is remembered, it never
  grows past the content, and it gives way before the result list drops below
  5 rows.

- **A missing program is named, with how to get it.** Some searches need
  programs outside Sombrero: `pdftotext` for PDFs, `rga` for documents, `fd`
  and `ripgrep` for speed. When one was missing, it looked like Sombrero had
  failed: every PDF became a "read error" of its own, and without `fd`/`rg`
  the search quietly used the slower built-in engine. Now a missing program is
  one line, "program missing: pdftotext", with what it cost. The window
  shows a dialog once per session that says this is not a fault in
  Sombrero and how to fix it, with a *Copy command* button. The command line
  prints `# missing:` with the same advice, and `--json` carries a `hint`. For
  `fd`, `rg` and `rga` the advice is to download the complete package, which
  includes them. For `pdftotext` it is your distribution's command (for
  example `sudo apt install poppler-utils`). The `--json` reason is
  `component_missing`, a warning; `where` is the program.
- **The AppImage reads PDFs on any distribution.** It now brings its own
  `pdftotext`, built from Poppler 24.08 as a single static program, like the
  bundled `ripgrep`, `fd` and `rga`. Before, PDFs were read only if the system
  had `poppler-utils` installed. A `pdftotext` installed on the system is still
  used first. The AppImage grows by 1.9 MB. Checked on 60 real PDFs: the same
  text as the system's `pdftotext`. Also checked on a clean Debian 12 without
  Poppler.

### Fixed

- **Emoji in file names shows up in the window.** On newer distributions
  (Fedora 44, Bazzite) the system emoji font was not drawn, so
  `birthday 🎉.jpg` was listed as `birthday .jpg`, a name that differed from
  the real one. The window now uses Twemoji when the system has it, and the
  AppImage brings its own (Twemoji Mozilla, 1.5 MB), so emoji shows on any
  distribution. Searching, copying and exporting already used the real name.
- **Control characters in file names are shown by name.** Linux allows
  almost any character in a name, including TAB, ESC and DEL. The window
  showed DEL and ESC as an empty box and TAB as a wide space, without saying
  so. Now they appear as ⟦TAB⟧, ⟦DEL⟧, ⟦ESC⟧, in italics with a note, the
  same way as the invisible direction marks. Only the screen changes:
  searching, copying and exporting use the real name, and a path pasted into
  the terminal keeps the real character.
- **A disk with a right-to-left name keeps its time in place.** An Arabic or
  Hebrew folder name pulled the "0s" after it into the name.
- **Preview of right-to-left text keeps the line number on the left.** A line
  starting in Arabic, Hebrew or Persian showed its number on the right and
  reversed (`:2`).
- **Windows: accented names survive PowerShell.** When PowerShell captured
  the output of `sfs.exe` (`$r = sfs …`, `| ForEach-Object`), every accented
  path came back mangled: `relatório.txt` arrived as `relat├│rio.txt`, so
  `Test-Path` said False and the script failed. Warnings lost their symbols
  the same way (`·` became `À`). PowerShell reads a captured program in the
  console's code page (850 on a Portuguese Windows), and Sombrero was writing
  UTF-8. Now captured output uses the console's code page. A letter that does
  not exist in it becomes `?` in a path, never a look-alike that could name
  another file. `--json` on Windows is plain ASCII (`ó` for `ó`), so every
  name survives any code page and any JSON reader. Output in the terminal, and
  everything on Linux, is unchanged.
- **A folder you cannot read is no longer "nothing found".** Typing a folder
  that denies reading gave "1 directories without permission — partial
  results" and exit 1, as if the search had looked and found nothing. Nothing
  was looked at, so it is now an error, like a dead network mount you typed:
  exit 2, `"error"` in `--json` (the reason is still `permission_denied`), and
  the disk line says "permission denied". A subfolder without permission is
  still a warning and the search goes on. On Windows the folder's permissions
  (ACL) are checked by opening it.
- **Snapshots deeper in the folder are found when nothing else is.** Sombrero
  skips snapshot trees (Timeshift, snapper, ZFS, Samba) and searches them only
  when the live folders give nothing, or with `--snapshots`. It only looked
  for those trees right at the top of the search location, so a
  `.snapshots` two folders down was skipped and never searched: "0 files",
  exit 1, no note, and `--snapshots` did not reach it either. They are now
  found at any depth, with one extra walk over folders only, and only when it
  matters (no live results, or `--snapshots`).
- **A name filter no longer brings hidden files into a content search.** With
  *Name* and *Content* both filled in, hidden files whose name matched (a
  `.env`, a `.netrc`) came back even with hidden files off, and hidden folders
  whose name matched were searched. ripgrep lets a name pattern override its
  hidden filter. The name-only search and the fallback engine never did this;
  now content, boolean and document searches agree with them. On Windows this
  also covers files and folders marked hidden by their attribute.
- **The command line says when it folded a file's other names.** A file with
  several hardlinks is one result (the same file under another name), and so
  is an identical copy in a snapshot. The window shows "+N copies", `--json`
  lists each path, but the plain text output dropped them without a word, so
  `sfs … -l | xargs cp` lost the other names. It now adds a note such as
  "2 more path(s) to files already listed (hardlink…) not shown; --json lists
  them". The results themselves are unchanged.
- **Document search without `rga` says so everywhere.** Without `ripgrep-all`
  a *documents* search runs as a plain text search, so text inside PDF, docx
  or epub is not read. Only the command line said it; in the window, a saved
  search could tick the greyed-out *documents* box and finish with a green
  check. The search now reports the missing `rga` (see *Added*), and a saved
  search no longer ticks the box when `rga` is missing.

## [1.4.1] — 2026-10-26

Three fixes, each one a case where Sombrero said less than the truth about a
search. Two of them came from a full review of the search code with synthetic
tests.

### Fixed

- **A file typed as the search location is called a file.** Searches take
  folders, and a file in *In:* is still refused, but the summary line said
  "folder not found" about a file that exists. It now says "is a file, not a
  folder", and the command line says "is a file, not a folder — searches take
  folders". For scripts nothing changes: the `--json` reason is still
  `invalid_root` and the exit code is still 2.
- **Your `.ripgreprc` no longer changes Sombrero's results.** ripgrep reads the
  file named by `RIPGREP_CONFIG_PATH` on every run (and `rga` passes it on), so
  a line such as `--glob=!*.txt` there silently hid files from content,
  boolean and document searches, with no warning. Sombrero now runs ripgrep
  and `rga` with `--no-config`. Name searches (fd) were never affected.
- **One unreadable document no longer fails a whole document search.** A
  damaged PDF, a .docx that is not a zip, or an encrypted file made the whole
  *documents* search report "search engine failed" (exit 2, warning sign in
  the window), although every other result was right. That file is now
  reported on its own as a read error, with the reason the reader gave
  ("Couldn't read xref table", "not a valid zip container"), and the search
  ends normally.

## [1.4.0] — 2026-10-25

A progress bar per disk, so a long multi-disk search shows how far each disk
has gone and how fast it is reading.

### Added

- **Progress bar per disk.** Each disk line in the search summary now opens
  with a bar and a percentage, followed by the time that disk took, live hits,
  MB/s and the folder being walked, so a multi-disk search shows the disks
  advancing in parallel. `fd` and `rg` only report matches, so the percentage
  is an estimate against the last complete pass over the same disk; the first
  pass shows a moving bar ("first pass here"). A cancelled search leaves the
  bar stopped in amber. Boolean search has no bar. Measured on a 7.3 TB HDD:
  no change in search time and identical disk reads.

## [1.3.0] — 2026-10-23

A Windows build (beta), an update checker, and document search that works out
of the box in every Linux package.

### Added

- **Windows build (beta).** A portable package for Windows 10/11 (x64): unzip
  and run `SombreroFileSearch.exe`, no installer and no administrator rights;
  `ripgrep`, `fd` and `rga` are bundled. It is new and still being tested;
  Linux remains the primary platform. Steps in `README-Windows.txt`, attached
  to the release.
- **Update checker.** The installed version is always shown in the header;
  clicking it opens *Versions and updates* (installed build, latest release,
  its notes). Once a day, at startup and in the background, Sombrero asks
  GitHub for the latest **release** — commits on `main` and pre-releases never
  count. An *Update to vX.Y.Z* button appears only when a newer release exists.
  It updates in place where it can: installs made with `install.sh` run the
  release's own installer (`--app-only`, dependencies untouched), an AppImage
  replaces its own file (same name, so shortcuts keep working). The .deb and
  the Windows build are downloaded to *Downloads* and handed to the system.
  Downloads are checked against the size and sha256 GitHub publishes; a cut or
  corrupted download never replaces a working install. A git checkout is never
  updated by the app. The daily check can be turned off in the same dialog.
- `install.sh --app-only`: install or refresh the app without touching
  dependencies.

### Fixed

- **Dark theme, everywhere.** The results area of the *Duplicates* tab was
  white in the dark theme (the tree had no style rule), the tabs were white,
  and error/message boxes were unreadable (light text on the system's white
  background). Trees, lists, tabs, dialogs, message boxes and progress bars
  now follow the theme.
- **No more blank icons on Fedora-based distros.** Color emoji (📂 🔍 🌐 🔊 and
  the 🟢🟠🟡 verdict dots of the duplicate finder) depend on the distro's emoji
  font, and Qt does not draw the COLRv1 Noto Color Emoji shipped by
  Fedora/Bazzite — they rendered as nothing. They were replaced by plain
  symbols and text, and the verdict dots are now drawn by the app in the theme
  colors. A test keeps color emoji out of the interface.
- **Results are visible on 768-pixel-high screens.** On a 1366×768 laptop (or
  1024×768) the snippet panel took the space and the results table showed
  zero rows. Now the snippet yields first: it shrinks to about three lines and
  then folds away (drag the divider to bring it back), and it returns when the
  window grows. The table keeps 5 rows at 1366×768.
- **The tab close button follows the theme.** It was a blue box on Windows
  and an orange one on Linux; it is now a plain × in the theme colors.
- **Folders with a `~` in the path are shown in full.** The results table
  wrapped text, and a path like
  `C:\Windows\servicing\LCU\Package_for_RollupFix~…` broke right after `C:`,
  so the *Folder* column read just "C:...". Cells are now a single line,
  cut at the end.
- **The search summary follows a theme switch.** Switching to the light theme
  after a search left the disk names in the dark theme's light text, almost
  invisible on white; the summary is now redrawn in the new colors.
- **A finished search keeps its time.** The summary's elapsed time kept
  counting whenever it was redrawn (switching tabs, for instance): a 7-second
  search could later read "1m40s". It now stops when the search ends.
- **Monospaced text uses a modern monospace font**: Consolas on Windows
  (it was Courier New), the distro's monospace font on Linux — in the *Disk*
  column of *Duplicates* and in the snippet panel.
- **Closing the window during a slow update check no longer crashes.** The
  network timeout does not cover name resolution; with a slow network the
  window froze for 9 seconds on close and then the process aborted. The check
  now runs in a background thread that is simply dropped on close.
- **Failed update checks can be diagnosed.** The dialog still shows a plain
  sentence, but the technical error now goes to `queda.log` in the cache
  folder.

- **Bundled engines are found in every channel.** The engine only looked for
  bundled binaries under `~/.local/share/sombrero-file-search/bin` (the
  `install.sh` location); it now also looks in `bin/` next to its own code.
- **`rga` no longer fails when `rg` is bundled but not on `PATH`.** `rga` looks
  for `rg` only on `PATH`; the engine now adds `rg`'s folder when running `rga`.

### Changed

- **Document search works out of the box in every channel.** `ripgrep-all`
  (`rga`) is now bundled in the AppImage and in the .deb (it is not packaged by
  Debian/Ubuntu/Mint, so with the .deb the *docs* mode simply did not exist).
  Pinned to v0.10.10, sha256-checked at build time; license and source link
  shipped alongside (AGPL-3.0-or-later).
- **docx, odt and epub no longer need pandoc.** Sombrero reads them itself
  (`lfs/docs_text.py`, Python standard library only), registered as an `rga`
  custom adapter. pandoc is ~160–200 MB; bundling it would have made the .deb
  ~20× larger. When installed, pandoc still covers the rarer formats (fb2, ipynb,
  html). Checked against pandoc on 101 real documents: no text lost. The user's
  own `rga` configuration is kept: their custom adapters are copied in, ahead of
  Sombrero's; an unreadable configuration is left alone (Sombrero then passes none).
- **The .deb is now per architecture** (`amd64`, `arm64`) instead of `all`,
  because the bundled `rga` is native code. It now recommends `poppler-utils`
  (PDF) and `pandoc` (rare formats); `ripgrep-all` left *Suggests*.
- **The command line is documented as `sfs`.** The manuals and the .deb
  messages now use `sfs`; `lfs` (the development name) still works as an alias,
  so existing scripts keep running.

## [1.2.0] — 2026-09-22

Search that stops losing files it should have found — legacy encodings, odd file
names, dead network mounts — plus new CLI filters.

### Added

- **Legacy-encoded text is searched, in any language.** A term with non-ASCII
  characters now also matches the bytes it would have in the legacy encodings of
  every region (Windows 1250–1258/874, ISO-8859-x, KOI8-R/U, DOS, Mac, and
  Shift-JIS/EUC-JP/GBK/Big5/EUC-KR for CJK terms). One `ripgrep` pass; measured
  cost +1% to +6% on SSD and within noise on a cold mechanical disk. No false
  positives in UTF-8 files by construction.
- **File names in legacy encodings are found too** (`médico` finds
  `laudo_m\xe9dico.txt`), including the decomposed form macOS writes (NFD).
- **Names with invisible characters** are shown with a visible marker
  (`fatura_⟦RLO⟧txt.exe`) in italics with a tooltip — the RLO trick used to
  disguise executables no longer fools the list — and the search ignores those
  characters, so `zerowidth` finds `zero\u200bwidth.txt`.
- **CLI:** `--max-size`, `--depth N`, `--follow`.
- **Network shares in the "Disks ▾" menu** (NFS, SMB, sshfs, WebDAV, rclone), in
  their own section, deliberately *not* included in "All disks" — everyday
  searching is local and cheaper.
- `docs/FUNNEL_CONTRACT.md`: the incompleteness contract for scripts (every
  `reason`, which ones are fatal, exit codes).

### Changed

- **A dead mount that is the folder you asked for is now fatal** (exit `2`,
  `"error"` in `--json`) instead of "nothing found" (exit `1`). A dead mount
  *found under* a broader search stays a warning. **Scripts that check the exit
  code of a search on a network path should be reviewed.**
- Disks are now recognized by what they are *not* (system mounts), so `/data`,
  `/srv`, ZFS datasets, mergerfs pools and disks mounted inside your home show up
  in the menu.
- Invalid `--min-size`/`--max-size` values are now an error instead of being
  silently ignored; `--index` refuses `--follow`.
- A name typed with brackets and no `*`/`?` (e.g. `[2019]`) is searched both as a
  glob and as plain text, so `[2019]` finds the folder `[2019] Reports`.
- Exported CSV is formula-safe: text cells starting with `= + - @`, TAB or CR get
  a leading `'` (JSON export stays raw, for scripts).
- The CLI speaks English in every locale (the `--json` `detail` is a contract).

### Fixed

- **Cancel releases the engines immediately** (measured on a cold mechanical
  disk: 8.15 s → 1.02 s), and closing the window no longer leaves `fd`/`rg`
  scanning the disk.
- **Dead NAS no longer freezes the search:** the liveness probe was being
  answered by the client's attribute cache; it now also asks the server
  (`statvfs`). A frozen NAS is skipped in ~3 s, with a warning.
- Opening a file, opening its folder and the media player reached a *nonexistent*
  path for non-UTF-8 names; "Copy path" now yields a form the terminal accepts.
- A single unreadable file no longer turns the whole search into "search engine
  failed"; a symlink loop with `--follow` is no longer reported as an error.
- `sfs … | head` and Ctrl-C exit cleanly, without a traceback.
- Eject without `gio` now unmounts (and locks LUKS) *before* powering the drive
  off; saved searches remember the "snapshots" box; Ctrl+R on a fresh tab repeats
  the last search from history.

## [1.1.0] — 2026-09-09

Per-disk partitioned search, snapshot trees searched only when the live tree is
empty, duplicate finder, persistent copy queue, `--index` (plocate, opt-in),
`--json`, and the single incompleteness funnel behind the GUI bar, the CLI
warnings and the exit codes.

## [1.0.0] — 2026-08

First stable release: name and content search over `fd`/`ripgrep` with a Python
fallback, boolean expressions, documents via `ripgrep-all`, PySide6 GUI and an
equivalent CLI, disk-aware I/O policy, and the universal installer.
