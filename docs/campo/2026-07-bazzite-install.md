# Installing Sombrero File Search on immutable distros (Bazzite / Fedora Atomic)

*Versão em português: [2026-07-bazzite-install.pt-BR.md](2026-07-bazzite-install.pt-BR.md).*

**Field report — 2026-07-30**
Environment: Bazzite 44.20260721.0 (Silverblue), GNOME/Wayland, x86_64, ASUS GL553VD.
Commit tested: `907085f` (2026-07-25), branch `main`.

---

## Executive summary

`install.sh` **does not complete** on a clean Bazzite installation. It does not fail with
an error — it **hangs indefinitely on the first dependency** and opens a browser
window on the user's screen. Nothing gets installed.

The cause is not that the script is wrong: it is that the script assumes a premise that
holds on traditional Debian/Fedora/Arch and **stops holding on immutable-image distros** —
"a package manager existing in PATH means packages can be installed."
On Bazzite, `dnf` exists, is in PATH, and is a pitfall.

Three independent problems, in order of severity:

| # | Problem | Effect | Severity |
|---|---|---|---|
| 1 | `dnf` is a *stub* that opens the browser and blocks | **Installer hangs forever** | 🔴 Blocker |
| 2 | `/usr` read-only | No system package installable without a reboot | 🟠 Structural |
| 3 | `rg` and `fd` missing on a clean install | **Both engines** of the app fall back to Python | 🟠 Performance |

All of them have a fix, and it already exists in the script itself — it is just not being
applied to these packages. Details in the *Proposed fixes* section.

---

## 1. 🔴 Bazzite's `dnf` hangs the installer

### What happened

```
[1/5] Dependências de busca (ripgrep, fd, poppler)
Instalando ripgrep (via dnf)…
ERROR: Fedora Atomic images utilize rpm-ostree instead (and is discouraged to use).
Please, read our documentation
https://docs.bazzite.gg/Installing_and_Managing_Software/
```

…and the script **stopped here**. Six minutes later it was still alive, consuming no CPU,
making no progress. At the same time, **a Firefox window opened on its own** on the
desktop, showing the Bazzite documentation. The user asked for none of that.

### Why it hangs

`/usr/sbin/dnf` on Bazzite is not dnf — it is a 19-line wrapper:

```bash
# Show the error if we attempt to use the install/uninstall commands
for arg in "$@"; do
    if [[ $arg == "install" || $arg == "in" || $arg == "remove" || $arg == "rm" ]]; then
        echo -e "ERROR: Fedora Atomic images utilize rpm-ostree instead..." >&2
        ${SUDO_USER:+sudo -u $SUDO_USER dbus-launch} bash -lc 'xdg-open "https://docs.bazzite.gg/..."'
        exit 1
    fi
done
exec /usr/bin/dnf5 "$@"     # qualquer outro subcomando passa adiante
```

The `xdg-open` line runs **synchronously**. In an interactive terminal it returns
quickly; called from inside a script with output redirected, `dbus-launch` leaves a
daemon holding the inherited file descriptor and `dnf` never returns. `install.sh` sits
waiting for a command that never finishes.

### Exact trigger conditions — they matter for the fix

- It only fires on `install`, `in`, `remove`, `rm`. **Queries pass through** to the real
  `dnf5` and work normally (`dnf info`, `dnf search`). This is relevant: the installer's
  `pkg_exists()`, which uses `dnf -q info`, **is safe**.
- The browser is only opened when **`SUDO_USER` is set**, that is, when dnf is called
  via `sudo`. And `install.sh` builds `INSTALL="sudo dnf install -y"` — it falls exactly
  into the path that hangs.
- There is no *timeout* anywhere in the chain. The hang is permanent.

### Where the script is vulnerable

Two spots, both through `$INSTALL`:

1. **`sys_install()`** — `[1/5]`, for `ripgrep`, `fd`, `poppler`.
   It is only reached if the binary is missing (`has "$probe"` returns early if it is
   already there). On a clean Bazzite, `rg` and `fd` **are** missing → it hangs here.
2. **`setup_python()`** — `[4/5]`, when trying to install `python3-pyside6` from the
   system. `ask()` automatically answers "yes" outside a TTY, so the only obstacle
   between the script and `$INSTALL` is `pkg_exists()`.

   ⚠️ **On this Bazzite the second hang did NOT fire — by accident.**
   `dnf -q info python3-pyside6` returns **1**, because the image does not ship the
   Fedora repository metadata. `! pkg_exists` becomes true, the script logs
   *"não existe no repositório desta distro — usando venv"* ("not available in this
   distro's repository — using venv") and diverts to the venv without ever calling the
   package manager.

   The stated reason is wrong — the package **does** exist in Fedora; what is missing is
   the local metadata — but the detour saved the installation. **It is an accidental
   safeguard, not designed behavior.** On any immutable system with populated
   repositories (or on this same machine after a `dnf makecache`), `pkg_exists` would
   return 0 and the script would hang here.

In other words: **fixing only `[1/5]` is not enough**, and fix 5.1 remains necessary even
though this installation completed without it.

---

## 2. 🟠 `/usr` is read-only — the installation model changes

```
$ touch /usr/lib/systemd/system-sleep/.teste
touch: cannot touch ...: Read-only file system
```

On Fedora Atomic, system packages come in through `rpm-ostree install`, which **assembles
a new image and requires a reboot**. That is incompatible with the promise of a
single-pass installer: you cannot install `ripgrep` and use it on the next line.

A reliable marker for detecting the case: **the file `/run/ostree-booted`** exists.
It is more robust than looking for `rpm-ostree` in PATH (which also exists on mutable
systems with the package installed).

The good news: **the app needs root for nothing at all.** The `~/.local` destination is
already the script's default, and it works perfectly here.

---

## 3. 🟠 On a clean Bazzite BOTH engines are missing

| Component | Present? | Role | Without it |
|---|---|---|---|
| `ripgrep` (`rg`) | ❌ **missing** | content search | pure-Python fallback |
| `fd` | ❌ **missing** | name search | pure-Python fallback |
| `pdftotext` (poppler) | ✅ present | PDF text | — |
| `libxcb-cursor` | ✅ present | Qt xcb plugin | GUI would not open on X11 |
| `ensurepip` | ✅ present | venv creation | venv impossible |
| PySide6 | ❌ missing | GUI | solved by venv |

`rpm -q ripgrep` → *package ripgrep is not installed*. Bazzite is a gaming image;
neither `ripgrep` nor `fd` is part of it.

This is serious for this project in particular: Sombrero is sold as *"powered by
ripgrep/fd with a proven pure-Python fallback"*, and the declared target is **large
collections on SMR and USB disks**. Falling back is precisely the scenario where the
fallback hurts most.

### ⚠️ Detection pitfall: `command -v` sees shell functions

Worth recording because it cost time during diagnosis. A manual probe indicated
`ripgrep` was present:

```
$ command -v rg
rg
```

Note that the output **is not a path**. `rg` was a **shell function** injected into the
user's profile by Claude Code, redirecting to the ripgrep embedded in the `claude` binary
itself. There was no binary at all.

The installer's `has()` uses `command -v`, which **matches functions and aliases**. The
script was not fooled in this run (it runs in its own shell, without the interactive
profile), but the same probe done by hand, or an installer run with `source`, would be.

**Defensive fix:** use `type -P` instead of `command -v` — `type -P` looks **only for
executables in PATH**, ignoring functions, aliases and builtins.

```bash
has(){ type -P "$1" >/dev/null 2>&1; }
```

---

## 4. ✅ What works — solution validated on this machine

All the rest of the installer is correct and runs fine here. And the way out for the
engines **already exists in the script itself**: it is the static-binary pattern used in
`install_rga()` and `install_pandoc()`. It just needs to be extended to `ripgrep` and
`fd`, which publish official `x86_64-unknown-linux-musl` tarballs on GitHub.

Tested and working, without root and without a reboot:

```bash
# ripgrep estático
curl -fsSL https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/\
ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz | tar xz
install -m755 ripgrep-*/rg ~/.local/bin/rg

# fd estático
curl -fsSL https://github.com/sharkdp/fd/releases/download/v10.4.2/\
fd-v10.4.2-x86_64-unknown-linux-musl.tar.gz | tar xz
install -m755 fd-*/fd ~/.local/bin/fd
```

Result:

```
$ ~/.local/bin/rg --version
ripgrep 15.2.0 (rev e89fff89ac)
$ ~/.local/bin/fd --version
fd 10.4.2
```

`~/.local/bin` is already in the user's PATH, so the binaries become visible to the
installer's `has()` — which then skips `dnf` and never hangs.

---

## 5. Proposed fixes to `install.sh`

### 5.1 🔴 Top priority — never let `$INSTALL` hang

Two lines of defense, both cheap:

**(a) Detect an immutable system BEFORE choosing the package manager.** On ostree there
is no usable package manager for our case: better to declare `PM=""` and go straight to
the user-space path, which is what works.

```bash
detect_pm() {
  if [ -e /run/ostree-booted ]; then
    PM=""; OSTREE=1
    wn "sistema imutável (ostree) — pacotes de sistema exigiriam rpm-ostree + reboot;"
    wn "usando binários estáticos e venv em ~/.local (nenhum root necessário)."
    return
  fi
  if   has apt-get; then PM=apt;    INSTALL="sudo apt-get install -y"
  ...
}
```

**(b) Universal seat belt — put a `timeout` on every system installation.**
It applies to any distro, not just ostree: no installer should be able to hang forever
because a package manager decided to open a browser.

```bash
INSTALL="timeout 300 sudo dnf install -y"
```

### 5.2 🟠 Extend the static-binary pattern to `ripgrep` and `fd`

Mirroring `install_rga()`, which already solves the same problem for `rga`:

```bash
install_static_engines() {
  mkdir -p "$PREFIX/bin"
  [ "$ARCH" = "x86_64" ] || { wn "binários estáticos só p/ x86_64"; return; }
  has rg || dl_tar "https://github.com/BurntSushi/ripgrep/releases/download/$RGV/ripgrep-$RGV-x86_64-unknown-linux-musl.tar.gz" rg
  has fd || dl_tar "https://github.com/sharkdp/fd/releases/download/$FDV/fd-$FDV-x86_64-unknown-linux-musl.tar.gz" fd
}
```

Gain: on **any** distro without those packages — immutable, locked-down corporate, or
without root privilege — the app starts running with the native engines instead of the
fallback. It stops being a Bazzite patch and becomes general robustness.

### 5.3 🟡 `has()` immune to functions and aliases

```bash
has(){ type -P "$1" >/dev/null 2>&1; }
```

### 5.4 🟡 Offer the `rpm-ostree` path as an explicit alternative

For those who prefer system packages, document it (without running it on our own, since
it requires a reboot):

```bash
rpm-ostree install ripgrep fd    # requer reiniciar para valer
```

### 5.5 🟢 `ask()` assumes "yes" outside a TTY — reconsider

```bash
ask(){ [ "$ASSUME_YES" = 1 ] && return 0; [ -t 0 ] || return 0; ... }
```

Outside a terminal, the script **consents on its own** to system installations via `sudo`.
That is how it reached `dnf` without anyone confirming. The safer default for automation
is the opposite: with no TTY and no explicit `-y`, **refuse** whatever requires privilege,
and follow the user-space path.

---

## 6. Final state of this machine — ✅ installed and working

| Item | State |
|---|---|
| Repository cloned | ✅ `~/projetos/sombrero-file-search` (`907085f`, 07-25) |
| `rg` 15.2.0 static | ✅ `~/.local/bin/rg` |
| `fd` 10.4.2 static | ✅ `~/.local/bin/fd` |
| `pdftotext` | ✅ from the system |
| `rga` / `pandoc` | ✅ static in `~/.local/share/sombrero-file-search/bin` |
| PySide6 6.11.1 (venv) | ✅ `~/.local/share/sombrero-file-search/venv` |
| App + menu shortcut | ✅ build `907085f+ (2026-07-25)` |

### How the installation was completed

**Without patching `install.sh`.** It was enough to pre-install the two engines as static
binaries (section 4) *before* running the script. With `rg` and `fd` visible in PATH,
`has()` returns early and step `[1/5]` never reaches `dnf`; and step `[4/5]` was spared by
the accidental `pkg_exists` safeguard described in section 1.

Result: the installer ran end to end **without a single call to `dnf`**, without root and
without a reboot.

### Verification

The app itself confirms it is using the native engines, not the fallback:

```
$ sfs ~/projetos/sombrero-file-search -n '*.md'
# engine: rg=/home/rtoledo/.local/bin/rg fd=/home/rtoledo/.local/bin/fd rga=…/bin/rga
```

- **CLI** — name search and content search, both returning correct results.
- **GUI** — `QApplication` created in *offscreen* mode, `lfs.app` imported,
  `MainWindow` present, exit 0. PySide6 6.11.1 on Wayland.

> Note: the `+` in `907085f+` indicates a dirty tree — it is this very report file,
> not yet committed.

---

## 7. Conclusion

None of the three problems is the fault of Sombrero's architecture — the app is
well-behaved, installs into `~/.local`, does not ask for root and already has the right
mechanism (static binary) implemented for other dependencies. What is missing is **not
trusting that a package manager exists** and extending to the two main engines the
strategy that already works for `rga` and `pandoc`.

Once that is done, Bazzite stops being a special case: it becomes just one more distro
where the installer runs to the end, without root and without a reboot.
