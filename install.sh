#!/usr/bin/env bash
# ==========================================================================
#  Sombrero File Search — instalador universal
#  Instala o app + TODAS as dependências, em qualquer distro:
#    - ripgrep, fd            (busca de conteúdo / nome)          [binário estático]
#    - poppler-utils          (pdftotext, p/ PDF no modo documentos)
#    - PySide6                (GUI; via sistema ou venv próprio)
#    - ripgrep-all (rga)      (busca dentro de PDF/docx/epub/zip)  [binário estático]
#    - pandoc                 (docx/epub/odt/html no rga)          [binário estático]
#  Não requer root para o app: instala em ~/.local. Espaço de usuário primeiro,
#  gerenciador de pacotes como alternativa — importa em distros imutáveis
#  (ostree/Bazzite/Silverblue), onde /usr é somente-leitura e pacotes de sistema
#  exigem rpm-ostree + reboot. Só usa sudo se você autorizar, e nunca em ostree.
# ==========================================================================
set -Eeuo pipefail   # -E: o trap ERR abaixo também vale dentro de função (ver on_err)

APP="sombrero-file-search"
OLD_APP="linux-file-search"                 # nome anterior (rebranding jul/2026)
PREFIX="${PREFIX:-$HOME/.local/share/$APP}"
OLD_PREFIX="$HOME/.local/share/$OLD_APP"
BIN="$HOME/.local/bin"
APPDIR="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"
mkdir -p "$BIN"   # rga/pandoc/rg/fd (binário estático) symlinkam aqui já em [1/5]-[3/5],
                  # antes do install_app() em [5/5] — sem isto, ln -sf falha em HOME limpo

# Rebranding: reaproveita a instalação antiga (o venv de ~250 MB, sobretudo) em
# vez de recriá-la sob o nome novo. Só move se o destino NOVO ainda não existe.
if [ -d "$OLD_PREFIX" ] && [ ! -d "$PREFIX" ]; then
  mv "$OLD_PREFIX" "$PREFIX" 2>/dev/null || true
fi
SRC="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ARCH="$(uname -m)"
ASSUME_YES=0
for a in "$@"; do case "$a" in -y|--yes) ASSUME_YES=1;; -h|--help)
  echo "uso: ./install.sh [-y|--yes]   (-y = não perguntar, instala tudo)"; exit 0;; esac; done

STAGE="início"                       # última seção anunciada por c() — usado por on_err
c()  { STAGE="$*"; printf "\033[1;36m%s\033[0m\n" "$*"; }
ok() { printf "  \033[32m✓\033[0m %s\n" "$*"; }
wn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
er() { printf "  \033[31m✗\033[0m %s\n" "$*"; }
has(){ type -P "$1" >/dev/null 2>&1; }   # só binário no PATH — imune a função/alias de shell

# Rede de segurança geral: qualquer falha NÃO tratada explicitamente (os pontos
# já protegidos por if/else/wn continuam só avisando e seguindo) cai aqui em vez
# de abortar em silêncio. Aponta a seção em que quebrou (STAGE, do último c()) e
# o comando exato — sem isso, "o instalador travou" vira depuração às cegas.
on_err() {
  local line="$1" cmd="$2"
  echo
  er "instalação interrompida em: $STAGE"
  er "comando que falhou (install.sh linha $line): $cmd"
  echo "  Isso não deveria derrubar o app inteiro — rode 'bash -x install.sh' pra ver"
  echo "  o passo a passo, ou abra um issue citando a linha e a mensagem acima."
  exit 1
}
trap 'on_err "$LINENO" "$BASH_COMMAND"' ERR
# pergunta S/n (default Sim); respeita -y e ambiente não-interativo.
# ask "pergunta" [padrao_sem_tty: y|n] — padrao_sem_tty só importa quando NÃO há
# TTY e ASSUME_YES=0: usar "n" nos pontos que escalam para instalação de
# sistema via sudo (tem alternativa segura em espaço de usuário); o gate geral
# de "seguir com as dependências" continua "y" (automação não deve travar).
ask(){
  [ "$ASSUME_YES" = 1 ] && return 0
  if [ -t 0 ]; then
    local r; printf "  \033[1;36m?\033[0m %s [S/n] " "$1"; read -r r
    case "$r" in [nN]|[nN][aãoOÃ]*) return 1;; *) return 0;; esac
  fi
  [ "${2:-y}" = "n" ] && return 1
  return 0
}

# -------------------------------------------------- gerenciador de pacotes
PM=""; INSTALL=""; IMMUTABLE=0; IMMUTABLE_KIND=""

# Sistema de imagem imutável (/ e /usr somente-leitura; estado gravável só sob
# /var): cobre as três famílias que existem hoje, não só o Bazzite.
#   - Fedora Atomic/uBlue (Bazzite, Silverblue, Kinoite, …): marcador /run/ostree-booted
#   - openSUSE MicroOS/Aeon: comando transactional-update no PATH
#   - fallback genérico: /usr montado "ro" em /proc/mounts (pega qualquer
#     imutável futura que não use nenhum dos dois marcadores acima)
# Preenche IMMUTABLE_KIND (ostree|transactional|generic) — o comando de sistema
# pra escapar do modo imutável difere por família; "rpm-ostree" não existe no
# MicroOS, "transactional-update" não existe no ostree.
detect_immutable() {
  [ -e /run/ostree-booted ] && { IMMUTABLE_KIND=ostree; return 0; }
  has transactional-update && { IMMUTABLE_KIND=transactional; return 0; }
  grep -qE '^\S+[[:space:]]+/usr[[:space:]]+\S+[[:space:]]+ro[,[:space:]]' /proc/mounts 2>/dev/null \
    && { IMMUTABLE_KIND=generic; return 0; }
  return 1
}

# comando de sistema equivalente a "instalar pacote" nesta família de imutável
# (usado só em mensagens — nunca executado por nós)
immutable_pkg_cmd() { # immutable_pkg_cmd <pacote>
  case "$IMMUTABLE_KIND" in
    ostree)        echo "rpm-ostree install $1";;
    transactional) echo "transactional-update pkg install $1";;
    *)             echo "o mecanismo de atualização atômica da sua distro";;
  esac
}

detect_pm() {
  if detect_immutable; then
    PM=""; IMMUTABLE=1
    wn "sistema imutável (imagem atômica) — pacotes de sistema exigiriam"
    wn "$(immutable_pkg_cmd '<pacote>') + REBOOT; usando binários estáticos"
    wn "e venv em ~/.local (nenhum root necessário)."
    return
  fi
  # timeout: cinto de segurança universal — nenhum gerenciador de pacotes deve
  # poder pendurar o instalador para sempre (ex.: um wrapper que abre browser
  # e trava esperando algo que nunca chega). Vale p/ toda distro, não só ostree.
  local T="timeout ${SFS_PM_TIMEOUT:-300}"
  if   has apt-get; then PM=apt;    INSTALL="$T sudo apt-get install -y"
  elif has dnf;     then PM=dnf;    INSTALL="$T sudo dnf install -y"
  elif has pacman;  then PM=pacman; INSTALL="$T sudo pacman -S --noconfirm"
  elif has zypper;  then PM=zypper; INSTALL="$T sudo zypper install -y"
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
    pandoc:*) echo pandoc;;
    rga:pacman) echo ripgrep-all;;  rga:*) echo ripgrep-all;;
    pyside6:apt) echo python3-pyside6;;   pyside6:dnf) echo python3-pyside6;;
    pyside6:pacman) echo pyside6;;
    pyside6:zypper)
      # Tumbleweed nomeia com o prefixo de versão do python3 do sistema
      # (ex.: python313-pyside6) — "python3-PySide6" nunca existiu no repo.
      local pv; pv="$(python3 -c 'import sys; print("%d%d" % sys.version_info[:2])' 2>/dev/null)"
      if [ -n "$pv" ]; then echo "python${pv}-pyside6"; else echo "python3-pyside6"; fi
      ;;
    pyside6:*) echo python3-pyside6;;
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

# o repositório desta distro conhece o pacote? (evita tentar instalar em vão)
pkg_exists() {
  case "$PM" in
    apt)    apt-cache show "$1" >/dev/null 2>&1;;
    dnf)    dnf -q info "$1" >/dev/null 2>&1;;
    pacman) pacman -Si "$1" >/dev/null 2>&1;;
    zypper) zypper -q info "$1" >/dev/null 2>&1;;
    *)      return 1;;
  esac
}

# -------------------------------------------------- binário estático (rga/pandoc)
dl() { # dl <url> <destino>
  if has curl; then curl -fsSL --retry 3 "$1" -o "$2"
  elif has wget; then wget -qO "$2" "$1"
  else er "preciso de curl ou wget"; return 1; fi
}

# true se o binário já está no PATH OU já foi instalado por nós em $PREFIX/bin.
# Reexecutar o instalador não deve rebaixar ~150 MB de binários estáticos só
# porque $PREFIX/bin ainda não entrou no PATH desta sessão (aviso do próprio
# script, no fim da instalação).
engine_present() { has "$1" || [ -x "$PREFIX/bin/$1" ]; }

# baixa um .tar.gz e instala UM binário (nome = $2) em $PREFIX/bin + symlink em $BIN
dl_tar() { # dl_tar <url> <binario>
  local url="$1" bin="$2" tmp f
  tmp="$(mktemp -d)"
  if dl "$url" "$tmp/a.tgz" && tar xzf "$tmp/a.tgz" -C "$tmp" --no-same-owner; then
    f="$(find "$tmp" -type f -name "$bin" | head -1)"
    if [ -n "$f" ]; then
      install -m755 "$f" "$PREFIX/bin/$bin"
      ln -sf "$PREFIX/bin/$bin" "$BIN/$bin"
      rm -rf "$tmp"; return 0
    fi
  fi
  rm -rf "$tmp"; return 1
}

# rg/fd como binário estático — mesmo padrão de install_rga/install_pandoc.
# "espaço de usuário primeiro": roda em QUALQUER distro sem pedir root, e é o
# que evita cair no gerenciador de pacotes (o ponto que travava no Bazzite).
install_static_engines() {
  mkdir -p "$PREFIX/bin"
  local rgv="15.2.0" fdv="v10.4.2"
  if [ "$ARCH" != "x86_64" ]; then
    wn "rg/fd: binário pronto só p/ x86_64 (seu: $ARCH) — usando o gerenciador de pacotes."
    sys_install ripgrep rg
    sys_install fd "$(has fdfind && echo fdfind || echo fd)"
    return
  fi
  if engine_present rg; then ok "rg já presente"; else
    c "Baixando rg $rgv (binário estático, sem root)…"
    dl_tar "https://github.com/BurntSushi/ripgrep/releases/download/$rgv/ripgrep-$rgv-x86_64-unknown-linux-musl.tar.gz" rg \
      && ok "rg instalado" || wn "download do rg falhou — busca de conteúdo cai no fallback Python"
  fi
  if engine_present fd; then ok "fd já presente"; else
    c "Baixando fd $fdv (binário estático, sem root)…"
    dl_tar "https://github.com/sharkdp/fd/releases/download/$fdv/fd-$fdv-x86_64-unknown-linux-musl.tar.gz" fd \
      && ok "fd instalado" || wn "download do fd falhou — busca por nome cai no fallback Python"
  fi
  if [ "$IMMUTABLE" = 1 ]; then wn "alternativa via sistema (exige reboot): $(immutable_pkg_cmd 'ripgrep fd')"; fi
}

install_rga() {
  mkdir -p "$PREFIX/bin"
  if engine_present rga; then ok "rga já presente"; return; fi
  if [ "$ARCH" != "x86_64" ]; then
    wn "rga: binário pronto só p/ x86_64 (seu: $ARCH). Instale 'ripgrep-all' pelo gerenciador."
    sys_install ripgrep-all rga; return
  fi
  local v="v0.10.10"
  local url="https://github.com/phiresky/ripgrep-all/releases/download/$v/ripgrep_all-$v-x86_64-unknown-linux-musl.tar.gz"
  c "Baixando ripgrep-all $v (estático)…"
  local tmp d; tmp="$(mktemp -d)"
  # cadeia inteira na condição do if (como dl_tar): sob `set -e`, um tar/find/install
  # solto no corpo do then aborta o instalador inteiro num download truncado — aqui
  # uma falha em qualquer etapa só cai no wn de aviso, sem derrubar o script.
  if dl "$url" "$tmp/rga.tgz" \
    && tar xzf "$tmp/rga.tgz" -C "$tmp" --no-same-owner \
    && d="$(find "$tmp" -maxdepth 1 -type d -name 'ripgrep_all-*')" \
    && [ -n "$d" ] \
    && install -m755 "$d/rga" "$d/rga-preproc" "$PREFIX/bin/"; then
    ln -sf "$PREFIX/bin/rga" "$BIN/rga"; ln -sf "$PREFIX/bin/rga-preproc" "$BIN/rga-preproc"
    ok "rga instalado em $PREFIX/bin (+ symlink em $BIN)"
  else
    wn "download/extração do rga falhou — modo documentos ficará indisponível"
  fi
  rm -rf "$tmp"
}

install_pandoc() {
  if engine_present pandoc; then ok "pandoc já presente"; return; fi
  local amd; case "$ARCH" in x86_64) amd=amd64;; aarch64|arm64) amd=arm64;; *) amd="";; esac
  if [ -z "$amd" ]; then wn "pandoc: arquitetura $ARCH sem binário pronto — docx/epub ficam de fora"; return; fi
  local v="3.10"
  local url="https://github.com/jgm/pandoc/releases/download/$v/pandoc-$v-linux-$amd.tar.gz"
  c "Baixando pandoc $v (estático, p/ docx/epub/odt)…"
  local tmp f; tmp="$(mktemp -d)"
  if dl "$url" "$tmp/p.tgz" \
    && tar xzf "$tmp/p.tgz" -C "$tmp" --no-same-owner \
    && f="$(find "$tmp" -type f -name pandoc)" \
    && [ -n "$f" ] \
    && install -m755 "$f" "$PREFIX/bin/pandoc"; then
    ln -sf "$PREFIX/bin/pandoc" "$BIN/pandoc"
    ok "pandoc instalado (docx/epub/odt/html cobertos)"
  else
    wn "download/extração do pandoc falhou — só PDF/zip no modo documentos"
  fi
  rm -rf "$tmp"
}

# -------------------------------------------------- Python + PySide6
PYBIN=""

# Qt >= 6.5 (o PySide6 do pip) exige a libxcb-cursor do SISTEMA p/ abrir em X11 —
# o pip não empacota libs de sistema. Sem ela a GUI aborta no arranque com
# "Could not load the Qt platform plugin xcb". Pacotes da distro (python3-pyside6
# etc.) puxam-na por dependência; o caminho do venv precisa garantir na mão.
ensure_qt_xcb() {
  # grep SEM -q: com pipefail, o -q sai no 1º match e o SIGPIPE no ldconfig
  # derruba o pipeline — a lib presente pareceria ausente
  ldconfig -p 2>/dev/null | grep 'libxcb-cursor\.so\.0' >/dev/null && return 0
  if [ -z "$PM" ]; then
    if [ "$IMMUTABLE" = 1 ]; then
      wn "libxcb-cursor ausente — só falta se você abrir em X11 (Wayland não precisa dela)."
      wn "em sistema imutável só entra via '$(immutable_pkg_cmd xcb-util-cursor)' + REBOOT — não faço isso por você."
    else
      wn "libxcb-cursor ausente — sem ela a GUI não abre em X11; instale pela sua distro"
    fi
    return 1
  fi
  local p; case "$PM" in
    dnf|pacman) p=xcb-util-cursor;;
    *)          p=libxcb-cursor0;;      # apt/zypper
  esac
  c "Instalando $p (plugin xcb do Qt p/ a GUI)…"
  if $INSTALL "$p"; then ok "$p instalado"; else wn "falhou instalar $p — a GUI pode não abrir em X11"; fi
}

# venv de verdade exige o ensurepip, que em Debian/Mint vem em pacote SEPARADO
# (python3.X-venv). Atenção: `python3 -m venv --help` funciona mesmo SEM ele, e o
# binário `python3` sempre existe — nenhum dos dois serve de teste. Quem falta é o
# ensurepip, então é ele que checamos.
ensure_venv_pkg() {
  python3 -c "import ensurepip" >/dev/null 2>&1 && return 0
  if [ -z "$PM" ]; then
    wn "ensurepip ausente e sem gerenciador de pacotes — instale o venv da sua distro"; return 1
  fi
  local pv; pv="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  c "Instalando suporte a venv (ensurepip ausente)…"
  local p                                  # $pv já vem como "3.12" -> python3.12-venv
  for p in ${pv:+"python$pv-venv"} python3-venv; do
    pkg_exists "$p" || continue
    $INSTALL "$p" || continue
    if python3 -c "import ensurepip" >/dev/null 2>&1; then ok "$p instalado"; return 0; fi
  done
  wn "não consegui habilitar o venv — instale manualmente (ex.: python$pv-venv)"; return 1
}

setup_python() {
  if python3 -c "import PySide6" >/dev/null 2>&1; then
    PYBIN="$(command -v python3)"; ok "PySide6 do sistema OK"; return
  fi
  # tenta o pacote PySide6 da distro (traz QtMultimedia p/ o player).
  # Nem toda distro tem: Ubuntu noble/Mint 22.x só empacotam PySide2 (Qt5) — aí
  # nem tentamos, pra não poluir a saída com um erro esperado, e vamos de venv.
  # (recusa no prompt ≠ pacote inexistente: cada caso tem sua mensagem)
  if [ -n "$PM" ] && ! pkg_exists "$(pkg pyside6)"; then
    wn "$(pkg pyside6) não existe no repositório desta distro — usando venv."
  elif [ -n "$PM" ] && ask "Instalar PySide6 pelo gerenciador ($(pkg pyside6))?" n; then
    $INSTALL "$(pkg pyside6)" || true
    if python3 -c "import PySide6" >/dev/null 2>&1; then
      PYBIN="$(command -v python3)"; ok "PySide6 do sistema OK"; return
    fi
    wn "PySide6 do sistema não ficou disponível — caindo para venv."
  fi
  ensure_qt_xcb || true            # PySide6 do pip: garante o xcb do sistema (GUI)
  # venv anterior que já funciona: reaproveita (re-rodar o instalador não deve
  # rebaixar ~250 MB de PySide6 à toa)
  if [ -x "$PREFIX/venv/bin/python" ] && "$PREFIX/venv/bin/python" -c "import PySide6" >/dev/null 2>&1; then
    PYBIN="$PREFIX/venv/bin/python"; ok "venv com PySide6 já existe — reaproveitado"; return
  fi
  c "Criando ambiente próprio (venv) com PySide6…"
  ensure_venv_pkg || true          # se falhar, o venv abaixo dirá o porquê
  rm -rf "$PREFIX/venv"            # só aqui: venv ausente ou quebrado (ex.: sem ensurepip)
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
  rm -rf "$PREFIX/lfs/__pycache__"     # .pyc velho de um módulo removido confunde

  # Carimbo da build. O app instalado é uma CÓPIA: sem isto, nada na tela
  # distingue a versão de hoje da de semana passada, e "isso não existe no
  # programa" vira uma sessão inteira de depuração de um recurso que já estava
  # pronto. O título da janela mostra o que este arquivo diz.
  ver=""
  if git -C "$SRC" rev-parse --short HEAD >/dev/null 2>&1; then
    ver="$(git -C "$SRC" rev-parse --short HEAD)"
    [ -n "$(git -C "$SRC" status --porcelain 2>/dev/null)" ] && ver="$ver+"
    ver="$ver ($(git -C "$SRC" log -1 --format=%cs 2>/dev/null))"
  else
    ver="$(date +%Y-%m-%d)"            # tarball sem git: ao menos a data
  fi
  printf '%s\n' "$ver" > "$PREFIX/VERSION"
  ok "build instalada: $ver"

  cat > "$BIN/$APP" <<EOF
#!/usr/bin/env bash
# Lançador do Sombrero File Search (gerado pelo install.sh)
export PATH="$PREFIX/bin:\$PATH"    # acha rga/pandoc empacotados
exec "$PYBIN" "$PREFIX/lfs/app.py" "\$@"
EOF
  chmod +x "$BIN/$APP"
  ln -sf "$PREFIX/lfs/cli.py" "$BIN/$APP-cli" 2>/dev/null || true

  # CLI standalone (com o python certo). Comando novo: 'sfs' (Sombrero File
  # Search). Mantemos 'lfs' como ALIAS — muda o nome, não a memória muscular de
  # quem já usa o comando em scripts e no dia a dia.
  cat > "$BIN/sfs" <<EOF
#!/usr/bin/env bash
export PATH="$PREFIX/bin:\$PATH"
exec "$PYBIN" "$PREFIX/lfs/cli.py" "\$@"
EOF
  chmod +x "$BIN/sfs"
  ln -sf "$BIN/sfs" "$BIN/lfs"          # alias de compatibilidade

  # limpa lançadores/atalho do nome antigo, pra não ficar entrada duplicada no
  # menu nem um binário obsoleto no PATH apontando para o PREFIX que já movemos.
  rm -f "$BIN/$OLD_APP" "$BIN/$OLD_APP-cli" "$APPDIR/$OLD_APP.desktop" 2>/dev/null || true
  for sz in 48 64 128 256; do rm -f "$ICONS/${sz}x${sz}/apps/$OLD_APP.png" 2>/dev/null || true; done
  rm -f "$ICONS/scalable/apps/$OLD_APP.svg" 2>/dev/null || true

  ok "app em $PREFIX  ·  lançadores: $BIN/$APP  ·  CLI: $BIN/sfs (alias: lfs)"

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
Name=Sombrero File Search
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
  ok "atalho de menu instalado (Sombrero File Search)"
}

# mostra o plano de dependências (nome de pacote resolvido p/ ESTA distro) e pede OK
plan_and_confirm() {
  c "Dependências do projeto (para $PM):"
  printf "  %-16s %-22s %s\n" "COMPONENTE" "PACOTE ($PM)" "PAPEL"
  printf "  %-16s %-22s %s\n" "ripgrep"     "$(pkg ripgrep)" "busca de conteúdo"
  printf "  %-16s %-22s %s\n" "fd"          "$(pkg fd)"      "busca por nome"
  printf "  %-16s %-22s %s\n" "poppler"     "$(pkg poppler)" "texto de PDF (opcional)"
  printf "  %-16s %-22s %s\n" "pandoc"      "$(pkg pandoc)"  "docx/epub/odt (opcional)"
  printf "  %-16s %-22s %s\n" "ripgrep-all" "$(pkg rga)"     "buscar dentro de documentos"
  printf "  %-16s %-22s %s\n" "PySide6"     "$(pkg pyside6)" "interface gráfica (ou venv)"
  echo "  (rga/pandoc: se o repositório não tiver, baixo o binário estático. App vai em ~/.local, sem root.)"
  echo
  if ! ask "Instalar/verificar essas dependências agora?"; then
    wn "Instalação de dependências pulada a pedido. O app será copiado, mas pode faltar motor."
    return 1
  fi
  return 0
}

# ============================================================ fluxo
c "== Sombrero File Search — instalador =="
echo "  destino: $PREFIX"
echo "  arch:    $ARCH"
detect_pm; [ -n "$PM" ] && echo "  pacotes: $PM" || wn "gerenciador de pacotes não detectado"
echo

DEPS_OK=1; plan_and_confirm || DEPS_OK=0
echo

if [ "$DEPS_OK" = 1 ]; then
c "[1/5] Motores de busca (ripgrep, fd) + poppler"
install_static_engines
sys_install poppler pdftotext
echo
c "[2/5] ripgrep-all (busca dentro de documentos)"
install_rga
echo
c "[3/5] pandoc (docx/epub/odt)"
install_pandoc
echo
fi   # fim do bloco de dependências (DEPS_OK)

c "[4/5] Python + PySide6 (GUI)"
setup_python
echo
c "[5/5] Instalando o aplicativo"
install_app
echo
c "== Pronto! =="
echo "  GUI : abra 'Sombrero File Search' no menu, ou rode:  $APP"
echo "  CLI : sfs ~/pasta -c \"texto\"   |   sfs ~/docs -n '*.pdf' -c laudo --docs   (alias: lfs)"
case ":$PATH:" in *":$BIN:"*) : ;; *) wn "adicione ao PATH:  export PATH=\"$BIN:\$PATH\"";; esac
