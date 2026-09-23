# Field test: the 1.2.0 `.deb` GUI on a 12-disk server (2026-09-23)

*Versão em português: [README.pt-BR.md](README.pt-BR.md).*

Verification of the Debian package's **graphical** side on ServidorCedro (Linux Mint,
i7-13700K, 12 mounted disks), after the CLI had already been validated there. Kept because the
machine is a bench no development box reproduces: twelve real disks, a live X11 session reached
over a Tailscale RustDesk link, and a screen whose resolution changes during the session.

## The bench

- **Machine:** ServidorCedro, Linux Mint, 24 threads, 12 disks mounted under `/mnt`
  (eleven ext4 partitions plus one LUKS mapper), one of them an NVMe Optane.
- **Install:** `sombrero-file-search` 1.2.0 from the `.deb`; GUI on the user venv at
  `~/.local/share/sombrero-file-search/venv` (PySide6 6.11.1), since Debian/Mint do not
  package PySide6. System `python3` has no PySide6 — the launcher's fallback is what runs.
- **Display:** X11 on `:0`, reached over RustDesk through a Tailscale link. Monitor native
  mode **3440x1440**; the session was running at **1920x1080**, lowered on purpose to save
  bandwidth on a slow Wi-Fi uplink.

## Files

| File | What |
|---|---|
| `1_montagens_e_menu.txt` | `classifica_montagens()` on 12 real disks, the mount left out, and the "Disks" menu as the GUI builds it |
| `2_tela_e_janelas.txt` | `xrandr` / `xdpyinfo` / `wmctrl`: native mode vs. the root window's real size, and every open window's geometry |
| `3_duas_versoes.txt` | 1.1.0 and 1.2.0 running at the same time, offscreen and on the real display |

## What passed

| Check | Result |
|---|---|
| `import PySide6`, `QApplication` | ok (venv, 6.11.1) |
| `MainWindow()`, `show()`, `processEvents()` | ok — title "Sombrero File Search" |
| Packaged launcher `/usr/bin/sombrero-file-search` | starts and stays in the event loop |
| Name search (6 logs) | 0.01 s |
| Content search (`classifica_montagens`) | 2 files, 6 matches, 0.02 s |
| Mount classification | **12 local disks, 0 false "network"** |
| "Disks" menu | 15 entries: *All disks*, separator, *Home folder*, 12 disks |

The one `/mnt/*` mount the engine left out was `rustdesk-cliprdr-fs` — a read-only FUSE
clipboard filesystem, correctly not a user disk.

## Left open

### 1. A window is not rescued when the screen's resolution shrinks

`_fit_to_screen` (`lfs/app.py`) pulls a window back inside the visible area, and is wired to
run on the first `show()` and on `QWindow.screenChanged` — that is, when the window moves to a
**different** screen. It is never called when the **same** screen changes resolution, which Qt
reports through `QScreen.geometryChanged` / `availableGeometryChanged`.

**Failure:** open the GUI at 3440x1440 with the window toward the right, then let the session
drop to 1920x1080. The window keeps its coordinates, falls outside the root window, and is
alive but invisible — and reopening does not help, because nothing repositions it. On this
machine that shrink is routine: the resolution is lowered on purpose when the link is slow.

Live proof in the same capture: the RustDesk window sits at `x=3240` on a 1920-wide root.

`_fit_geometry` is already pure and unit-tested; only *when* it is called is in question.
Whether the program should move a window the user may have placed deliberately is a design
call, **pending the author's decision** — nothing implemented.

### 2. The disk menu shows the filesystem label, not the mount point

`/mnt/CB69B31B5CC6C5D7` (7.3 TB) appears as **"UnidadeOptane"**, a stale label from an earlier
life of that drive, while the real Optane (`/mnt/optane`, 13.4 GB) appears as "OptaneCache".
SFS is reporting the disk's own data faithfully, but the entry does not match the name the user
works with — and the two look like the same device. Either the label gets fixed on the disk, or
the menu shows label **and** mount point when they disagree. Author's call.

## Note on the reported symptom

The symptom that opened this test — "a second instance would not render while a different
version was open" — **did not reproduce**, neither offscreen nor on the real display: both
versions ran side by side, both windows visible, `config.json` byte-identical before and after.
There is no single-instance mechanism in the code (no `QLocalServer`, `QSharedMemory` or lock
file). The evidence points at item 1 above as the real cause: the window was rendering, outside
the visible area.
