#!/usr/bin/env bash
# ==========================================================================
#  Linux File Search — instalador universal
#  Instala o app + TODAS as dependências, em qualquer distro:
#    - ripgrep, fd            (busca de conteúdo / nome)
#    - poppler-utils          (pdftotext, p/ PDF no modo documentos)
#    - PySide6                (GUI; via sistema ou venv próprio)
#    - ripgrep-all (rga)      (busca dentro de PDF/docx/epub/zip)  [binário estático]
#    - pandoc                 (docx/epub/odt/html no rga)          [binário estático]
#  Não requer root para o app: instala em ~/.local. Só usa sudo p/ pacotes
#  de sistema (ripgrep/fd/poppler), e apenas se você autorizar.
# ==========================================================================
set -euo pipefail

APP="linux-file-search"
PREFIX="${PREFIX:-$HOME/.local/share/$APP}"
BIN="$HOME/.local/bin"
APPDIR="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"
SRC="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ARCH="$(uname -m)"

c()  { printf "\033[1;36m%s\033[0m\n" "$*"; }
ok() { printf "  \033[32m✓\033[0m %s\n" "$*"; }
wn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
er() { printf "  \033[31m✗\033[0m %s\n" "$*"; }
has(){ command -v "$1" >/dev/null 2>&1; }

# -------------------------------------------------- gerenciador de pacotes
PM=""; INSTALL=""
detect_pm() {
  if   has apt-get; then PM=apt;    INSTALL="sudo apt-get install -y"
  elif has dnf;     then PM=dnf;    INSTALL="sudo dnf install -y"
  elif has pacman;  then PM=pacman; INSTALL="sudo pacman -S --noconfirm"
  elif has zypper;  then PM=zypper; INSTALL="sudo zypper install -y"
  else PM=""; fi
}
# nome do pacote por distro (var indireta)
pkg() {
  local key="$1"
  case "$key:$PM" in
    fd:apt) echo fd-find;;  fd:*) echo fd;;
    poppler:apt|poppler:dnf) echo poppler-utils;;
    poppler:pacman) echo poppler;;  poppler:zypper) echo poppler-tools;;
    ripgrep:*) echo ripgrep;;
    *) echo "$key";;
  esac
}

sys_install() {   # sys_install <chave-logica> <binario-p/-checar>
  local key="$1" probe="$2" p; p="$(pkg "$key")"
  if has "$probe"; then ok "$probe já instalado"; return; fi
  if [ -z "$PM" ]; then wn "sem gerenciador de pacotes conhecido — instale '$p' manualmente"; return; fi
  c "Instalando $p (via $PM)…"
  if $INSTALL "$p"; then ok "$p instalado"; else wn "falhou instalar $p — siga sem ele"; fi
}

# -------------------------------------------------- binário estático (rga/pandoc)
dl() { # dl <url> <destino>
  if has curl; then curl -fsSL --retry 3 "$1" -o "$2"
  elif has wget; then wget -qO "$2" "$1"
  else er "preciso de curl ou wget"; return 1; fi
}

install_rga() {
  mkdir -p "$PREFIX/bin"
  if has rga; then ok "rga já disponível ($(command -v rga))"; return; fi
  if [ "$ARCH" != "x86_64" ]; then
    wn "rga: binário pronto só p/ x86_64 (seu: $ARCH). Instale 'ripgrep-all' pelo gerenciador."
    sys_install ripgrep-all rga; return
  fi
  local v="v0.10.10"
  local url="https://github.com/phiresky/ripgrep-all/releases/download/$v/ripgrep_all-$v-x86_64-unknown-linux-musl.tar.gz"
  c "Baixando ripgrep-all $v (estático)…"
  local tmp; tmp="$(mktemp -d)"
  if dl "$url" "$tmp/rga.tgz"; then
    tar xzf "$tmp/rga.tgz" -C "$tmp"
    local d; d="$(find "$tmp" -maxdepth 1 -type d -name 'ripgrep_all-*')"
    install -m755 "$d/rga" "$d/rga-preproc" "$PREFIX/bin/"
    ln -sf "$PREFIX/bin/rga" "$BIN/rga"; ln -sf "$PREFIX/bin/rga-preproc" "$BIN/rga-preproc"
    ok "rga instalado em $PREFIX/bin (+ symlink em $BIN)"
  else wn "download do rga falhou — modo documentos ficará indisponível"; fi
  rm -rf "$tmp"
}

install_pandoc() {
  if has pandoc; then ok "pandoc já disponível"; return; fi
  local amd; case "$ARCH" in x86_64) amd=amd64;; aarch64|arm64) amd=arm64;; *) amd="";; esac
  if [ -z "$amd" ]; then wn "pandoc: arquitetura $ARCH sem binário pronto — docx/epub ficam de fora"; return; fi
  local v="3.10"
  local url="https://github.com/jgm/pandoc/releases/download/$v/pandoc-$v-linux-$amd.tar.gz"
  c "Baixando pandoc $v (estático, p/ docx/epub/odt)…"
  local tmp; tmp="$(mktemp -d)"
  if dl "$url" "$tmp/p.tgz"; then
    tar xzf "$tmp/p.tgz" -C "$tmp"
    install -m755 "$(find "$tmp" -type f -name pandoc)" "$PREFIX/bin/pandoc"
    ln -sf "$PREFIX/bin/pandoc" "$BIN/pandoc"
    ok "pandoc instalado (docx/epub/odt/html cobertos)"
  else wn "download do pandoc falhou — só PDF/zip no modo documentos"; fi
  rm -rf "$tmp"
}

# -------------------------------------------------- Python + PySide6
PYBIN=""
setup_python() {
  if python3 -c "import PySide6" >/dev/null 2>&1; then
    PYBIN="$(command -v python3)"; ok "PySide6 do sistema OK"; return
  fi
  c "PySide6 ausente no sistema — criando ambiente próprio (venv)…"
  if ! python3 -m venv --help >/dev/null 2>&1; then
    sys_install python3-venv python3    # Debian/Mint: pacote separado
  fi
  python3 -m venv "$PREFIX/venv"
  "$PREFIX/venv/bin/pip" install --upgrade pip >/dev/null
  c "Instalando PySide6 no venv (pode baixar ~100 MB)…"
  "$PREFIX/venv/bin/pip" install PySide6
  PYBIN="$PREFIX/venv/bin/python"; ok "PySide6 instalado no venv"
}

# -------------------------------------------------- copiar app + lançadores
install_app() {
  mkdir -p "$PREFIX/lfs" "$PREFIX/assets" "$BIN" "$APPDIR"
  cp -f "$SRC/lfs/"*.py "$PREFIX/lfs/"
  cp -f "$SRC/assets/"* "$PREFIX/assets/" 2>/dev/null || true

  cat > "$BIN/$APP" <<EOF
#!/usr/bin/env bash
# Lançador do Linux File Search (gerado pelo install.sh)
export PATH="$PREFIX/bin:\$PATH"    # acha rga/pandoc empacotados
exec "$PYBIN" "$PREFIX/lfs/app.py" "\$@"
EOF
  chmod +x "$BIN/$APP"
  ln -sf "$PREFIX/lfs/cli.py" "$BIN/$APP-cli" 2>/dev/null || true
  # CLI standalone (com o python certo)
  cat > "$BIN/lfs" <<EOF
#!/usr/bin/env bash
export PATH="$PREFIX/bin:\$PATH"
exec "$PYBIN" "$PREFIX/lfs/cli.py" "\$@"
EOF
  chmod +x "$BIN/lfs"
  ok "app em $PREFIX  ·  lançadores: $BIN/$APP  e  $BIN/lfs (CLI)"

  # ícones no tema hicolor
  for sz in 48 64 128 256; do
    if [ -f "$SRC/assets/icon_$sz.png" ]; then
      mkdir -p "$ICONS/${sz}x${sz}/apps"
      cp -f "$SRC/assets/icon_$sz.png" "$ICONS/${sz}x${sz}/apps/$APP.png"
    fi
  done
  [ -f "$SRC/assets/icon.svg" ] && { mkdir -p "$ICONS/scalable/apps"; cp -f "$SRC/assets/icon.svg" "$ICONS/scalable/apps/$APP.svg"; }

  cat > "$APPDIR/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Linux File Search
GenericName=Busca de arquivos
Comment=Busca ampla de arquivos: nome, conteúdo, booleano e dentro de documentos
Exec=$BIN/$APP %F
Icon=$APP
Terminal=false
Categories=Utility;System;FileTools;
Keywords=busca;search;grep;ripgrep;arquivos;conteudo;pdf;booleano;
StartupNotify=true
EOF
  has update-desktop-database && update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
  has gtk-update-icon-cache && gtk-update-icon-cache -f -t "$ICONS" >/dev/null 2>&1 || true
  ok "atalho de menu instalado (Linux File Search)"
}

# ============================================================ fluxo
c "== Linux File Search — instalador =="
echo "  destino: $PREFIX"
echo "  arch:    $ARCH"
detect_pm; [ -n "$PM" ] && echo "  pacotes: $PM" || wn "gerenciador de pacotes não detectado"
echo

c "[1/5] Dependências de busca (ripgrep, fd, poppler)"
sys_install ripgrep rg
sys_install fd "$(has fdfind && echo fdfind || echo fd)"
sys_install poppler pdftotext
echo
c "[2/5] ripgrep-all (busca dentro de documentos)"
install_rga
echo
c "[3/5] pandoc (docx/epub/odt)"
install_pandoc
echo
c "[4/5] Python + PySide6 (GUI)"
setup_python
echo
c "[5/5] Instalando o aplicativo"
install_app
echo
c "== Pronto! =="
echo "  GUI : abra 'Linux File Search' no menu, ou rode:  $APP"
echo "  CLI : lfs ~/pasta -c \"texto\"   |   lfs ~/docs -n '*.pdf' -c laudo --docs"
case ":$PATH:" in *":$BIN:"*) : ;; *) wn "adicione ao PATH:  export PATH=\"$BIN:\$PATH\"";; esac
