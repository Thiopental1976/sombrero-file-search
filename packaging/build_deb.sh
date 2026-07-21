#!/usr/bin/env bash
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Constrói o pacote .deb. Sem dh_make, sem debhelper: a árvore é montada à mão e
# fechada com dpkg-deb. O projeto tem UM diretório de código Python e nada para
# compilar — o maquinário do debhelper só acrescentaria dependências de build
# (que teriam de ser instaladas em qualquer máquina que empacote) sem resolver
# problema nenhum aqui.
#
# DESENHO — por que o pacote é MAGRO:
#   No Ubuntu/Mint noble o apt NÃO tem PySide6 (só PySide2). Um .deb que
#   dependesse de python3-pyside6 seria ininstalável na distro do próprio autor.
#   As saídas:
#     a) embutir PySide6 no .deb  -> ~250 MB, biblioteca duplicada fora do apt,
#        e o dpkg passa a carregar algo que ele não sabe atualizar;
#     b) pip no postinst          -> rede durante a instalação, como root, sem
#        o usuário ver. Isso é malandragem, não empacotamento;
#     c) MAGRO (o que fazemos)    -> o motor e a CLI não precisam de Qt e ficam
#        100% funcionais só com python3. A GUI usa o PySide6 do sistema se
#        houver; se não houver, o lançador EXPLICA e oferece
#        `sombrero-file-search --setup-gui`, que cria um venv no HOME do usuário
#        que pediu. Quem quer tudo pronto e autocontido usa o AppImage.
#
# Depends é deliberadamente mínimo: python3. ripgrep e fd são Recommends porque
# o motor tem fallback em Python puro (mais lento, mas correto) — declará-los
# como Depends mentiria sobre o que o programa precisa para funcionar.
set -euo pipefail
# O umask do autor nesta máquina é 007 (grupo-privado): sem isto, os diretórios
# saem 770 e o próprio dpkg-deb recusa a árvore ("control directory has bad
# permissions"). Um pacote tem que sair com as permissões do PACOTE, nunca com
# as do umask de quem o construiu.
umask 022

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$SRC/dist}"
APP="sombrero-file-search"
ARCH="all"                      # Python puro: um pacote serve qualquer máquina

ver="$(cd "$SRC" && python3 -c 'import sys; sys.path.insert(0,"lfs"); import version; print(version.deb_version())')"
pkgdir="$(mktemp -d)"
trap 'rm -rf "$pkgdir"' EXIT

say() { printf '\033[1;36m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }

say "== Empacotando $APP $ver (.deb) =="

# ------------------------------------------------------------------ árvore
LIB="$pkgdir/usr/lib/$APP"
mkdir -p "$LIB/lfs" "$LIB/assets" "$pkgdir/usr/bin" \
         "$pkgdir/usr/share/applications" \
         "$pkgdir/usr/share/doc/$APP" \
         "$pkgdir/usr/share/man/man1" \
         "$pkgdir/DEBIAN"

install -m 644 "$SRC/lfs/"*.py "$LIB/lfs/"
install -m 644 "$SRC/assets/"* "$LIB/assets/"
printf '%s\n' "$(cd "$SRC" && python3 -c 'import sys; sys.path.insert(0,"lfs"); import version; print(version.build_info())')" \
    > "$LIB/VERSION"
chmod 644 "$LIB/VERSION"

for sz in 48 64 128 256; do
  d="$pkgdir/usr/share/icons/hicolor/${sz}x${sz}/apps"
  mkdir -p "$d"; install -m 644 "$SRC/assets/icon_$sz.png" "$d/$APP.png"
done
mkdir -p "$pkgdir/usr/share/icons/hicolor/scalable/apps"
install -m 644 "$SRC/assets/icon.svg" "$pkgdir/usr/share/icons/hicolor/scalable/apps/$APP.svg"

# ------------------------------------------------------------- lançadores
# O launcher da GUI é o único lugar com lógica: é ele que sabe achar um Python
# com PySide6 e que transforma "ImportError: No module named PySide6" — que o
# usuário veria no terminal, ou nem veria se clicou no menu — em instrução.
cat > "$pkgdir/usr/bin/$APP" <<'LAUNCHER'
#!/usr/bin/env bash
# Lançador da GUI do Sombrero File Search (pacote .deb).
set -euo pipefail
LIB=/usr/lib/sombrero-file-search
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/sombrero-file-search/venv"

# 1) PySide6 do sistema (distros que o empacotam: Arch, Fedora, openSUSE);
# 2) venv do usuário, criado por --setup-gui (Debian/Ubuntu/Mint, que não têm).
pybin=""
if python3 -c 'import PySide6' >/dev/null 2>&1; then pybin=python3
elif [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import PySide6' >/dev/null 2>&1; then
  pybin="$VENV/bin/python"
fi

setup_gui() {
  echo "Preparando a interface gráfica em $VENV"
  echo "(PySide6 não está empacotado no apt desta distro; vai para o SEU home,"
  echo " sem root e sem tocar no sistema. A CLI 'lfs' já funciona sem isso.)"
  python3 -m venv "$VENV" || { echo "falta o venv do python: sudo apt install python3-venv" >&2; exit 1; }
  "$VENV/bin/pip" install --upgrade pip >/dev/null
  "$VENV/bin/pip" install PySide6 || exit 1
  # Qt >= 6.5 do pip precisa da libxcb-cursor do SISTEMA para abrir em X11.
  if ! ldconfig -p | grep libxcb-cursor >/dev/null 2>&1; then
    echo
    echo "AVISO: falta libxcb-cursor0 (o Qt do pip não a traz)."
    echo "       sudo apt install libxcb-cursor0"
  fi
  echo "pronto — rode 'sombrero-file-search' de novo."
}

if [ "${1:-}" = "--setup-gui" ]; then setup_gui; exit 0; fi

if [ -z "$pybin" ]; then
  msg="A interface gráfica precisa do PySide6, que não está instalado.
Rode uma vez:    sombrero-file-search --setup-gui
(A busca em linha de comando — 'lfs' — funciona sem isso.)"
  echo "$msg" >&2
  # Clicou no menu: sem terminal para ler a mensagem. Avisa na tela se der.
  if [ ! -t 2 ]; then
    command -v zenity  >/dev/null && zenity --error --no-wrap --text="$msg" 2>/dev/null && exit 1
    command -v kdialog >/dev/null && kdialog --error "$msg" 2>/dev/null && exit 1
  fi
  exit 1
fi
exec "$pybin" "$LIB/lfs/app.py" "$@"
LAUNCHER

# CLI: comando novo 'sfs' (Sombrero File Search) e 'lfs' como alias de
# compatibilidade. Os dois são arquivos reais (não symlink) de propósito: um
# link '/usr/bin/lfs -> sfs' apareceria diferente no `dpkg-deb -c` e o alias é
# barato demais para valer a complicação.
for cmd in sfs lfs; do
  cat > "$pkgdir/usr/bin/$cmd" <<'CLI'
#!/usr/bin/env bash
# CLI do Sombrero File Search. Não usa Qt: roda em servidor sem tela.
exec python3 /usr/lib/sombrero-file-search/lfs/cli.py "$@"
CLI
done
chmod 755 "$pkgdir/usr/bin/$APP" "$pkgdir/usr/bin/sfs" "$pkgdir/usr/bin/lfs"

# --------------------------------------------------------------- .desktop
cat > "$pkgdir/usr/share/applications/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Sombrero File Search
GenericName=Busca de arquivos
Comment=Busca ampla de arquivos: nome, conteúdo, booleano e dentro de documentos
Exec=/usr/bin/$APP %F
Icon=$APP
Terminal=false
Categories=Utility;System;FileTools;
Keywords=busca;search;grep;ripgrep;arquivos;conteudo;pdf;booleano;
StartupNotify=true
EOF
chmod 644 "$pkgdir/usr/share/applications/$APP.desktop"

# ------------------------------------------------------------------- docs
# copyright no formato DEP-5: é o arquivo que a Debian Policy exige e o que
# qualquer um lê para saber sob que licença redistribuir.
cat > "$pkgdir/usr/share/doc/$APP/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: sombrero-file-search
Source: https://github.com/Thiopental1976/sombrero-file-search

Files: *
Copyright: 2026 Rodrigo Toledo
License: GPL-3+

License: GPL-3+
 This program is free software: you can redistribute it and/or modify it under
 the terms of the GNU General Public License as published by the Free Software
 Foundation, either version 3 of the License, or (at your option) any later
 version.
 .
 This program is distributed in the hope that it will be useful, but WITHOUT ANY
 WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
 PARTICULAR PURPOSE.  See the GNU General Public License for more details.
 .
 On Debian systems, the complete text of the GNU General Public License version 3
 can be found in "/usr/share/common-licenses/GPL-3".
EOF
chmod 644 "$pkgdir/usr/share/doc/$APP/copyright"

printf '%s (%s) unstable; urgency=low\n\n  * Pacote gerado por packaging/build_deb.sh a partir do commit %s.\n\n -- Rodrigo Toledo <rrdtoledo@gmail.com>  %s\n' \
  "$APP" "$ver" "$(cd "$SRC" && git rev-parse --short HEAD 2>/dev/null || echo desconhecido)" \
  "$(date -R)" | gzip -9n > "$pkgdir/usr/share/doc/$APP/changelog.Debian.gz"
chmod 644 "$pkgdir/usr/share/doc/$APP/changelog.Debian.gz"

# ------------------------------------------------------------------- man
cat > "$pkgdir/usr/share/man/man1/sfs.1" <<'MAN'
.TH SFS 1 "2026" "sombrero-file-search" "User Commands"
.SH NAME
sfs \- broad file search (name and content) over ripgrep/fd
.SH SYNOPSIS
.B sfs
.RI [ options ] " PATH" ...
.SH DESCRIPTION
Searches files by name and/or content. Name terms match as CONTAINS by default;
globs are used as typed. Content search runs through ripgrep when available and
falls back to pure Python otherwise.
.PP
Output goes to stdout as raw bytes, so file names that are not valid UTF-8
survive a pipe to xargs.
.SH OPTIONS
.TP
.BR \-n ", " \-\-name " PATTERN"
name contains PATTERN (comma-separates several)
.TP
.BR \-c ", " \-\-content " TEXT"
file must contain TEXT
.TP
.BR \-b ", " \-\-bool " EXPR"
boolean content search: '(A OR B) AND C NOT D'
.TP
.BR \-D ", " \-\-docs
search inside documents (PDF/docx/epub) via ripgrep-all
.TP
.BR \-l
print file names only
.TP
.BR \-0
separate results with NUL (for xargs -0)
.TP
.BR \-V ", " \-\-version
show version and license
.SH SEE ALSO
.BR rg (1),
.BR fd (1)
.SH AUTHOR
Rodrigo Toledo
MAN
gzip -9n "$pkgdir/usr/share/man/man1/sfs.1"
chmod 644 "$pkgdir/usr/share/man/man1/sfs.1.gz"
# 'lfs' é alias do 'sfs': a man page do alias é um include (.so) para a real —
# `man lfs` mostra a mesma página, sem duplicar o texto.
printf '.so man1/sfs.1\n' > "$pkgdir/usr/share/man/man1/lfs.1"
gzip -9n "$pkgdir/usr/share/man/man1/lfs.1"
chmod 644 "$pkgdir/usr/share/man/man1/lfs.1.gz"

# ---------------------------------------------------------------- control
# Installed-Size é em KiB e o dpkg não o calcula sozinho num build manual.
size_kb="$(du -sk --exclude=DEBIAN "$pkgdir" | cut -f1)"
cat > "$pkgdir/DEBIAN/control" <<EOF
Package: $APP
Version: $ver
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Rodrigo Toledo <rrdtoledo@gmail.com>
Installed-Size: $size_kb
Depends: python3 (>= 3.10)
Recommends: ripgrep, fd-find
Suggests: ripgrep-all, python3-venv, libxcb-cursor0
Homepage: https://github.com/Thiopental1976/sombrero-file-search
Description: broad file search by name and content
 Searches a whole filesystem by file name, by content, by boolean expression
 and inside documents (PDF, docx, epub) — the kind of search Agent Ransack and
 FileLocator do on Windows, done natively on Linux over ripgrep and fd.
 .
 The search engine and the command line tool need nothing but python3: ripgrep
 and fd make it fast, and a pure Python fallback keeps it correct without them.
 The graphical interface needs PySide6; on distributions that do not package it
 (Debian, Ubuntu, Mint), run "sombrero-file-search --setup-gui" once.
EOF

# postinst/postrm: apenas caches do desktop. Nada de rede, nada de pip, nada de
# escrever no HOME de ninguém — instalar um pacote não deve surpreender.
cat > "$pkgdir/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache   >/dev/null && gtk-update-icon-cache -qtf /usr/share/icons/hicolor || true
fi
exit 0
EOF
cat > "$pkgdir/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache   >/dev/null && gtk-update-icon-cache -qtf /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$pkgdir/DEBIAN/postinst" "$pkgdir/DEBIAN/postrm"

# --------------------------------------------------------------- fechar
mkdir -p "$OUT"
deb="$OUT/${APP}_${ver}_${ARCH}.deb"
# --root-owner-group: sem fakeroot e sem sudo, tudo sai como root:root — sem
# isso o pacote instalaria arquivos pertencentes ao uid de quem empacotou.
dpkg-deb --build --root-owner-group -Zxz "$pkgdir" "$deb" >/dev/null
ok "$deb  ($(du -h "$deb" | cut -f1))"

# ------------------------------------------------------------- conferência
say "== Conferindo =="
dpkg-deb -I "$deb" | sed -n '2,12p'
probs=0
# grep sem casar sai com 1 e, sob `set -e`, derrubaria o script justamente no
# caso BOM (nenhum arquivo fora de /usr). Daí o `|| true`.
fora="$(dpkg-deb -c "$deb" | awk '{print $6}' | grep -v '^\./usr/' | grep -v '^\./$' || true)"
if [ -n "$fora" ]; then
  echo "$fora" | sed 's/^/  !! arquivo fora de \/usr: /'; probs=1
fi
# Lista UMA vez para um arquivo: `dpkg-deb -c | grep -q` sai no primeiro match e
# o SIGPIPE mata o dpkg-deb no meio ("tar subprocess killed by signal"), fazendo
# o arquivo presente parecer ausente. Mesma armadilha que o install.sh já
# documenta no ldconfig — vale a pena não repetir o erro em outro arquivo.
lista="$(mktemp)"; dpkg-deb -c "$deb" | awk '{print $NF}' > "$lista"
for f in ./usr/bin/sfs ./usr/bin/lfs ./usr/bin/$APP ./usr/lib/$APP/lfs/engine.py ./usr/lib/$APP/VERSION \
         ./usr/share/applications/$APP.desktop ./usr/share/doc/$APP/copyright \
         ./usr/share/man/man1/sfs.1.gz ./usr/share/man/man1/lfs.1.gz; do
  grep -Fxq "$f" "$lista" || { echo "  !! FALTA $f"; probs=1; }
done
rm -f "$lista"
[ "$probs" = 0 ] && ok "conteúdo conferido: tudo em /usr, nada faltando"
echo
echo "  instalar:    sudo apt install $deb"
echo "  remover:     sudo apt remove $APP"
