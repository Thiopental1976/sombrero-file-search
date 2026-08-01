#!/bin/bash
# F8-lite — regressão do install.sh contra os travamentos de distro imutável.
#
# Não entra na suíte rápida (test_audit.py): baixa binários reais da internet
# e usa unshare/mount namespaces, então é mais lento e barulhento. Rodar manual
# ou em CI dedicado: `bash tests/test_install_matrix.sh`.
#
# Casos cobertos (o que quebrou no Bazzite e não pode voltar a quebrar):
#   1. Máquina virgem MUTÁVEL real (apt/dnf/pacman/zypper) — instala normal.
#   2. IMUTÁVEL via `transactional-update` no PATH (família MicroOS/Aeon),
#      numa gaiola de PATH sem rg/fd/rga/pandoc/sudo — prova que o caminho
#      100% binário-estático funciona e nenhum `sudo` é chamado.
#   3. IMUTÁVEL via marcador /run/ostree-booted (família Fedora Atomic/uBlue).
#   4. IMUTÁVEL via fallback genérico (/usr montado ro em /proc/mounts) —
#      pega qualquer imutável futura sem marcador conhecido.
#   5. Idempotência: rodar 2x no mesmo HOME não deve rebaixar nada.
set -uo pipefail
cd "$(dirname "$0")/.."
INSTALL="$PWD/install.sh"
WORK="$(mktemp -d /tmp/sfs-matrix.XXXX)"
PASS=0 FAIL=0

ok()  { printf "  \033[32m✓\033[0m %s\n" "$*"; PASS=$((PASS+1)); }
bad() { printf "  \033[31m✗\033[0m %s\n" "$*"; FAIL=$((FAIL+1)); }
sec() { printf "\033[1;36m%s\033[0m\n" "$*"; }

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# ---------------------------------------------------------------- caso 1
sec "[1/5] Máquina virgem MUTÁVEL (sistema real: $(command -v apt-get dnf pacman zypper 2>/dev/null | head -1))"
H1="$WORK/mut"
env -i HOME="$H1" PATH=/usr/bin:/bin bash "$INSTALL" </dev/null >"$WORK/mut.log" 2>&1
rc=$?
if [ "$rc" = 0 ] && [ -x "$H1/.local/bin/sfs" ]; then
  ok "instalou e o CLI existe (rc=$rc)"
else
  bad "falhou (rc=$rc) — ver $WORK/mut.log"
fi

# ---------------------------------------------------------------- caso 2
sec "[2/5] IMUTÁVEL via 'transactional-update' — gaiola de PATH sem rg/fd/rga/pandoc/sudo"
CAGE="$WORK/fakebin"; mkdir -p "$CAGE"
for b in bash cat chmod cp curl date dirname env find git grep gzip head id \
         install ln mkdir mktemp python3 readlink rm sed sh sleep tar touch uname; do
  p="$(command -v "$b")" && ln -sf "$p" "$CAGE/$b"
done
[ -x /sbin/ldconfig ] && ln -sf /sbin/ldconfig "$CAGE/ldconfig"
cat > "$CAGE/transactional-update" <<'EOF'
#!/bin/sh
echo "transactional-update stub: não deveria ser chamado além de detecção" >&2
exit 1
EOF
chmod +x "$CAGE/transactional-update"
H2="$WORK/imm-trans"
env -i HOME="$H2" PATH="$CAGE" bash "$INSTALL" </dev/null >"$WORK/imm-trans.log" 2>&1
rc=$?
sudo_calls=$(grep -c 'sudo' "$WORK/imm-trans.log" 2>/dev/null)
sudo_calls=${sudo_calls:-0}
if [ "$rc" = 0 ] && [ -x "$H2/.local/bin/sfs" ] && [ "$sudo_calls" = 0 ]; then
  ok "instalou 100% por binário estático, zero menção a sudo (rc=$rc)"
else
  bad "falhou ou chamou sudo (rc=$rc, sudo_refs=$sudo_calls) — ver $WORK/imm-trans.log"
fi

# ---------------------------------------------------------------- caso 3
sec "[3/5] IMUTÁVEL via /run/ostree-booted (unshare -Urm, sem tocar no sistema real)"
H3="$WORK/imm-ostree"; mkdir -p "$H3"
if command -v unshare >/dev/null 2>&1; then
  unshare -Urm bash -c "
    mkdir -p /tmp/run_orig.\$\$
    mount --rbind /run /tmp/run_orig.\$\$
    mount -t tmpfs tmpfs /run 2>/dev/null
    mkdir -p /run/systemd/resolve
    mount --bind /tmp/run_orig.\$\$/systemd/resolve /run/systemd/resolve
    touch /run/ostree-booted
    env -i HOME='$H3' PATH=/usr/bin:/bin bash '$INSTALL' </dev/null
  " >"$WORK/imm-ostree.log" 2>&1
  rc=$?
  if [ "$rc" = 0 ] && grep -q "sistema imutável" "$WORK/imm-ostree.log"; then
    ok "detectou ostree e instalou por binário estático (rc=$rc)"
  else
    bad "falhou ou não detectou (rc=$rc) — ver $WORK/imm-ostree.log"
  fi
else
  bad "unshare indisponível — pulei este caso"
fi

# ---------------------------------------------------------------- caso 4
sec "[4/5] IMUTÁVEL via fallback genérico (/usr remontado ro em namespace isolado)"
H4="$WORK/imm-generic"; mkdir -p "$H4"
if command -v unshare >/dev/null 2>&1; then
  unshare -Urm bash -c "
    mount --bind /usr /usr 2>/dev/null
    mount -o remount,bind,ro /usr 2>/dev/null
    env -i HOME='$H4' PATH=/usr/bin:/bin bash '$INSTALL' </dev/null
  " >"$WORK/imm-generic.log" 2>&1
  rc=$?
  if [ "$rc" = 0 ] && grep -q "sistema imutável" "$WORK/imm-generic.log"; then
    ok "detectou /usr ro e instalou por binário estático (rc=$rc)"
  else
    bad "falhou ou não detectou (rc=$rc) — ver $WORK/imm-generic.log"
  fi
else
  bad "unshare indisponível — pulei este caso"
fi

# ---------------------------------------------------------------- caso 5
sec "[5/5] Idempotência (2ª rodada no mesmo HOME não deve rebaixar nada)"
env -i HOME="$H1" PATH=/usr/bin:/bin bash "$INSTALL" </dev/null >"$WORK/mut-2.log" 2>&1
rc=$?
if [ "$rc" = 0 ] && ! grep -q "Baixando" "$WORK/mut-2.log"; then
  ok "2ª rodada não baixou nada de novo (rc=$rc)"
else
  bad "2ª rodada rebaixou algo ou falhou (rc=$rc) — ver $WORK/mut-2.log"
fi

echo
sec "== Resultado: $PASS ok, $FAIL falhas =="
[ "$FAIL" = 0 ]
