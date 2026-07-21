#!/usr/bin/env bash
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Constrói o AppImage: um arquivo único que roda em qualquer distro x86_64 sem
# instalar nada. É o complemento do .deb, não um substituto:
#
#   .deb      -> magro, integra com o apt, GUI depende do PySide6 do usuário
#   AppImage  -> gordo (~200 MB), traz Python e PySide6 dentro, não depende de nada
#
# Por que AppImage e não Flatpak: o Flatpak roda em sandbox e este programa
# existe para varrer o disco INTEIRO. Concedê-lo `--filesystem=host` é anular a
# sandbox e ainda assim brigar com portais para abrir arquivo no aplicativo do
# usuário. Um buscador de arquivos é exatamente o tipo de programa para o qual a
# sandbox é o modelo errado.
#
# O Python vem do python-build-standalone (astral-sh): build relocável, com o
# ensurepip e as libs (ssl, sqlite) já dentro. Compilar Python aqui só criaria
# dependência de toolchain na máquina que empacota.
set -euo pipefail
umask 022

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$SRC/dist}"
CACHE="${LFS_APPIMAGE_CACHE:-$HOME/.cache/lfs-appimage}"
APP="sombrero-file-search"
PYVER="3.12.13"
PYTAG="20260718"
PYURL="https://github.com/astral-sh/python-build-standalone/releases/download/$PYTAG/cpython-$PYVER%2B$PYTAG-x86_64-unknown-linux-gnu-install_only.tar.gz"
AIURL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"

say() { printf '\033[1;36m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
wn()  { printf '  \033[33m!\033[0m %s\n' "$*"; }

ver="$(cd "$SRC" && python3 -c 'import sys; sys.path.insert(0,"lfs"); import version; print(version.RELEASE)')"
build="$(cd "$SRC" && python3 -c 'import sys; sys.path.insert(0,"lfs"); import version; print(version.build_info())')"
say "== Empacotando $APP $ver (AppImage) =="

# ------------------------------------------------------------------ insumos
mkdir -p "$CACHE"
fetch() {   # url destino
  [ -s "$2" ] && { ok "cache: $(basename "$2")"; return; }
  echo "  baixando $(basename "$2")…"
  curl -fL --retry 3 -o "$2.parcial" "$1"
  mv "$2.parcial" "$2"                 # nunca deixa download interrompido no cache
}
fetch "$AIURL" "$CACHE/appimagetool.AppImage"; chmod +x "$CACHE/appimagetool.AppImage"
fetch "$PYURL" "$CACHE/python-standalone.tar.gz"

# --------------------------------------------------------------- AppDir
appdir="$(mktemp -d)/$APP.AppDir"
trap 'rm -rf "$(dirname "$appdir")"' EXIT
mkdir -p "$appdir/usr/bin" "$appdir/usr/lib" "$appdir/usr/share/applications" \
         "$appdir/usr/share/icons/hicolor/256x256/apps" "$appdir/usr/share/metainfo"

say "[1/4] Python embutido"
tar -xzf "$CACHE/python-standalone.tar.gz" -C "$appdir/usr/lib"   # cria python/
PY="$appdir/usr/lib/python/bin/python3"
"$PY" -V

say "[2/4] PySide6 (Essentials — sem QtWebEngine, que dobraria o tamanho)"
"$PY" -m pip install --no-cache-dir --upgrade pip >/dev/null
"$PY" -m pip install --no-cache-dir PySide6-Essentials >/dev/null
"$PY" -c 'import PySide6; from PySide6.QtWidgets import QApplication; print("  PySide6", PySide6.__version__)'

# Poda: o que não é usado só engorda o download de quem vai baixar.
pyside_dir="$(dirname "$("$PY" -c 'import PySide6, os; print(PySide6.__file__)')")"
for mod in Qt3D QtCharts QtDataVis QtQuick QtQml QtWebSockets QtWebChannel \
           QtSensors QtSerialPort QtSpatialAudio QtScxml QtStateMachine \
           QtRemoteObjects QtBluetooth QtNfc QtDesigner QtUiTools QtHelp \
           QtTest QtPositioning QtLocation QtTextToSpeech; do
  rm -rf "$pyside_dir"/${mod}* "$pyside_dir"/Qt/lib/libQt6${mod#Qt}* 2>/dev/null || true
done
find "$appdir/usr/lib/python" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$appdir/usr/lib/python" -name 'tests' -path '*/lib/python3*' -prune -exec rm -rf {} + 2>/dev/null || true

say "[3/4] Aplicativo"
mkdir -p "$appdir/usr/lib/$APP/lfs" "$appdir/usr/lib/$APP/assets"
install -m 644 "$SRC/lfs/"*.py "$appdir/usr/lib/$APP/lfs/"
install -m 644 "$SRC/assets/"* "$appdir/usr/lib/$APP/assets/"
printf '%s\n' "$build" > "$appdir/usr/lib/$APP/VERSION"
install -m 644 "$SRC/assets/icon_256.png" "$appdir/usr/share/icons/hicolor/256x256/apps/$APP.png"
install -m 644 "$SRC/assets/icon_256.png" "$appdir/$APP.png"          # ícone do topo (exigido)
install -m 644 "$SRC/LICENSE" "$appdir/usr/lib/$APP/LICENSE"

cat > "$appdir/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Sombrero File Search
GenericName=Busca de arquivos
Comment=Busca ampla de arquivos: nome, conteúdo, booleano e dentro de documentos
Exec=$APP %F
Icon=$APP
Terminal=false
Categories=Utility;System;FileTools;
Keywords=busca;search;grep;ripgrep;arquivos;conteudo;pdf;booleano;
StartupNotify=true
EOF
cp "$appdir/$APP.desktop" "$appdir/usr/share/applications/"

# AppRun: o ponto de entrada. Duas responsabilidades além de chamar o Python —
#   1) `--cli`, para que UM arquivo sirva a GUI e a linha de comando;
#   2) achar rg/fd: o AppImage NÃO os embute (são binários grandes e o motor tem
#      fallback), então usa os do sistema quando existem. É a mesma política do
#      resto do projeto: motor externo se houver, degradação limpa se não.
cat > "$appdir/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
APPDIR_LIB="$HERE/usr/lib/sombrero-file-search"
PY="$HERE/usr/lib/python/bin/python3"
# PATH do sistema PRIMEIRO: se o usuário tem rg/fd instalados, são os dele que
# valem; o AppImage não sequestra as ferramentas da máquina.
export PATH="$PATH:$HERE/usr/bin"
case "${1:-}" in
  --cli|cli) shift; exec "$PY" "$APPDIR_LIB/lfs/cli.py" "$@" ;;
esac
exec "$PY" "$APPDIR_LIB/lfs/app.py" "$@"
APPRUN
chmod 755 "$appdir/AppRun"

# AppStream: o que faz o app aparecer direito em loja/centro de software.
cat > "$appdir/usr/share/metainfo/$APP.appdata.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>$APP</id>
  <name>Sombrero File Search</name>
  <summary>Broad file search by name and content</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>GPL-3.0-or-later</project_license>
  <description>
    <p>Searches a whole filesystem by file name, by content, by boolean
    expression and inside documents (PDF, docx, epub), over ripgrep and fd.</p>
    <p>It reads and exports; it never moves, renames or deletes anything.</p>
  </description>
  <launchable type="desktop-id">$APP.desktop</launchable>
  <url type="homepage">https://github.com/Thiopental1976/sombrero-file-search</url>
  <provides><binary>$APP</binary></provides>
  <releases><release version="$ver"/></releases>
</component>
EOF

say "[4/4] Montando"
mkdir -p "$OUT"
img="$OUT/Sombrero_File_Search-$ver-x86_64.AppImage"
# ARCH: o appimagetool não adivinha em build sem desktop integration.
ARCH=x86_64 "$CACHE/appimagetool.AppImage" --no-appstream "$appdir" "$img" 2>&1 \
  | grep -vi 'warning: no appstream' || true
[ -f "$img" ] || { echo "appimagetool não gerou o arquivo" >&2; exit 1; }
chmod +x "$img"
ok "$img  ($(du -h "$img" | cut -f1))"

say "== Conferindo =="
"$img" --cli --version
echo
echo "  GUI :  $img"
echo "  CLI :  $img --cli ~/pasta -n '*.pdf'"
