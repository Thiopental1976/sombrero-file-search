#!/usr/bin/env bash
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Compila um pdftotext ESTÁTICO (musl, Alpine em container) para o AppImage.
#
# 26/10/2026 (decisão do Rodrigo: "faremos o que é melhor para o usuário"): sem
# pdftotext no sistema, o modo documentos do AppImage não lia PDF nenhum. O
# pdftotext da distro não serve para embutir: puxa 52 bibliotecas (cripto, rede,
# Kerberos — assinatura digital, que extrair texto não usa) e exige a glibc da
# máquina que empacota (2.38 no Mint 22), acima do piso do AppImage. Estático
# com musl, como o rg/fd/rga, ele roda em qualquer distro x86_64.
#
# A poppler sai enxuta: só o que extrair texto precisa (FreeType; sem NSS,
# GPGME, curl, Qt, GLib, Cairo, OpenJPEG, LCMS, TIFF). Fontes e codificação vêm
# do próprio PDF; o que falta (imagem JPEG2000, cor gerenciada) não é texto.
#
# Uso: build_pdftotext_static.sh <saída>   (escreve <saída>/pdftotext)
# Precisa de podman (ou docker). O AppImage chama isto só quando o cache não
# tem o binário desta versão.
set -euo pipefail
umask 022

OUT="${1:?uso: build_pdftotext_static.sh <pasta de saída>}"
POPPLER_V="24.08.0"
POPPLER_SHA="97453fbddf0c9a9eafa0ea45ac710d3d49bcf23a62e864585385d3c0b4403174"
POPPLER_URL="https://poppler.freedesktop.org/poppler-$POPPLER_V.tar.xz"
ALPINE="docker.io/library/alpine:3.20"

CT="$(command -v podman || command -v docker || true)"
[ -n "$CT" ] || { echo "precisa de podman ou docker para compilar o pdftotext estático" >&2; exit 1; }

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

curl -fL --retry 3 -o "$work/poppler.tar.xz" "$POPPLER_URL"
echo "$POPPLER_SHA  $work/poppler.tar.xz" | sha256sum -c - >/dev/null \
  || { echo "sha256 da poppler $POPPLER_V não confere" >&2; exit 1; }

cat > "$work/dentro.sh" <<'DENTRO'
set -eu
apk add --no-cache build-base cmake samurai pkgconf \
  freetype-dev freetype-static zlib-dev zlib-static libpng-dev libpng-static \
  bzip2-dev bzip2-static brotli-dev brotli-static \
  fontconfig-dev fontconfig-static expat-dev expat-static >/dev/null
# o find_package do CMake escolhe o .so mesmo com -static: cada .a vai explícito
a() { find /lib /usr/lib -maxdepth 1 -name "$1" | head -1; }
# e, na ligação estática, as dependências de freetype/fontconfig vão no fim
EXTRA="$(pkg-config --static --libs fontconfig freetype2 libpng zlib)"
cd /w
tar -xf poppler.tar.xz
cd poppler-*/
cmake -S . -B b -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF -DENABLE_UTILS=ON -DENABLE_CPP=OFF -DENABLE_GLIB=OFF \
  -DENABLE_QT5=OFF -DENABLE_QT6=OFF -DENABLE_GOBJECT_INTROSPECTION=OFF \
  -DENABLE_LIBCURL=OFF -DENABLE_NSS3=OFF -DENABLE_GPGME=OFF -DENABLE_BOOST=OFF \
  -DENABLE_LIBOPENJPEG=none -DENABLE_DCTDECODER=none -DENABLE_LCMS=OFF \
  -DENABLE_LIBTIFF=OFF -DWITH_Cairo=OFF \
  -DBUILD_GTK_TESTS=OFF -DBUILD_QT5_TESTS=OFF -DBUILD_QT6_TESTS=OFF \
  -DBUILD_CPP_TESTS=OFF -DBUILD_MANUAL_TESTS=OFF -DENABLE_ZLIB_UNCOMPRESS=OFF \
  -DFREETYPE_LIBRARY="$(a libfreetype.a)" -DFontconfig_LIBRARY="$(a libfontconfig.a)" \
  -DPNG_LIBRARY="$(a libpng16.a)" -DZLIB_LIBRARY="$(a libz.a)" \
  -DCMAKE_EXE_LINKER_FLAGS="-static" \
  -DCMAKE_CXX_STANDARD_LIBRARIES="$EXTRA" >/dev/null
cmake --build b --target pdftotext >/dev/null
strip b/utils/pdftotext
cp b/utils/pdftotext /w/pdftotext
cp COPYING /w/COPYING
DENTRO

"$CT" run --rm -v "$work:/w:Z" "$ALPINE" sh /w/dentro.sh

if ldd "$work/pdftotext" 2>&1 | grep -q '=>'; then
  echo "pdftotext saiu dinâmico (ldd lista dependências)" >&2; exit 1
fi
install -m 755 "$work/pdftotext" "$OUT/pdftotext"
install -m 644 "$work/COPYING" "$OUT/poppler-COPYING"
echo "$POPPLER_V" > "$OUT/poppler-VERSION"
"$OUT/pdftotext" -v 2>&1 | head -1
