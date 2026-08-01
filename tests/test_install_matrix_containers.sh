#!/bin/bash
# F8 — matriz de contêiners reais (debian/ubuntu/fedora/arch/opensuse).
#
# Complementa tests/test_install_matrix.sh (que usa unshare -Urm pra simular
# imutabilidade sem sair do host). Aqui o alvo é o caminho MUTÁVEL comum, mas
# em distros de verdade via podman rootless — cada família de gerenciador de
# pacotes (apt/dnf/pacman/zypper) com seu próprio bootstrap de imagem mínima.
#
# Não entra na suíte rápida: baixa imagens de container (centenas de MB no
# total) e leva minutos. Rodar manual: `bash tests/test_install_matrix_containers.sh`.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
WORK="$(mktemp -d /tmp/sfs-matrix-containers.XXXX)"
PASS=0 FAIL=0

ok()  { printf "  \033[32m✓\033[0m %s\n" "$*"; PASS=$((PASS+1)); }
bad() { printf "  \033[31m✗\033[0m %s\n" "$*"; FAIL=$((FAIL+1)); }
sec() { printf "\033[1;36m%s\033[0m\n" "$*"; }

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

if ! command -v podman >/dev/null 2>&1; then
  echo "podman não encontrado — instale com 'sudo apt-get install -y podman'"
  exit 1
fi

# <nome> <imagem> <comando de bootstrap: cria user 'sfs', sudo NOPASSWD, curl/ca-certificates>
run_case() {
  local name="$1" image="$2" bootstrap="$3"
  sec "[$name] $image"
  local log="$WORK/$name.log"
  timeout 1800 podman run --rm -v "$REPO:/src:ro" "$image" bash -c "
    set -e
    $bootstrap
    cp -a /src /home/sfs/repo
    chown -R sfs:sfs /home/sfs/repo
    su - sfs -c 'cd ~/repo && bash install.sh -y && ~/.local/bin/sfs --version && \
      for e in rg fd rga pandoc; do test -x ~/.local/bin/\$e || echo \"MOTOR_FALTANDO: \$e\"; done'
  " >"$log" 2>&1
  local rc=$?
  if [ "$rc" = 0 ] && grep -q '^Sombrero File Search 0\.' "$log" && ! grep -q "MOTOR_FALTANDO" "$log"; then
    ok "instalou, CLI respondeu e os 4 motores (rg/fd/rga/pandoc) estão presentes (rc=$rc)"
    rm -f "$log"
  else
    bad "falhou (rc=$rc) — ver $log"
  fi
}

APT_BOOTSTRAP='export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq sudo curl ca-certificates python3 python3-venv >/dev/null
useradd -m -s /bin/bash sfs
echo "sfs ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/sfs'

DNF_BOOTSTRAP='dnf install -y -q sudo curl ca-certificates python3 util-linux >/dev/null
useradd -m -s /bin/bash sfs
echo "sfs ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/sfs'

PACMAN_BOOTSTRAP='pacman -Sy --noconfirm --needed sudo curl ca-certificates python python-pip >/dev/null
useradd -m -s /bin/bash sfs
echo "sfs ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/sfs'

ZYPPER_BOOTSTRAP='zypper --non-interactive install -y sudo curl ca-certificates python3 findutils >/dev/null
useradd -m -s /bin/bash sfs
echo "sfs ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/sfs'

run_case "debian"   "docker.io/library/debian:12"        "$APT_BOOTSTRAP"
run_case "ubuntu"   "docker.io/library/ubuntu:24.04"     "$APT_BOOTSTRAP"
run_case "fedora"   "docker.io/library/fedora:latest"    "$DNF_BOOTSTRAP"
run_case "archlinux" "docker.io/library/archlinux:latest" "$PACMAN_BOOTSTRAP"
run_case "opensuse" "docker.io/opensuse/tumbleweed:latest" "$ZYPPER_BOOTSTRAP"

echo
sec "== Resultado: $PASS ok, $FAIL falhas =="
[ "$FAIL" = 0 ]
