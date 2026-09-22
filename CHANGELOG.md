# Changelog

All notable changes to **Sombrero File Search**. Dates are YYYY-MM-DD.
The project follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

Detailed rationale and measurements live in the commit messages and in
[`docs/DOCUMENTACAO_TECNICA.md`](docs/DOCUMENTACAO_TECNICA.md) (Portuguese).

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
  characters, so `zerowidth` finds `zero​width.txt`.
- **CLI:** `--max-size`, `--depth N`, `--follow`.
- **Network shares in the "Disks ▾" menu** (NFS, SMB, sshfs, WebDAV, rclone), in
  their own section, deliberately *not* included in "All disks" — everyday
  searching is local and cheaper.
- `docs/CONTRATO_FUNIL.md`: the incompleteness contract for scripts (every
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
