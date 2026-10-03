#!/bin/bash
# Publica o pacote Windows como release do GitHub. SÓ rodar com o ok do Rodrigo.
# Uso: publicar_release.sh <run-id do CI com o artefato aprovado>
set -euo pipefail
RUN=${1:?run id do CI}
cd "$(dirname "$0")/../.."
REL=$(python3 -c "import sys; sys.path.insert(0,'lfs'); import version; print(version.RELEASE)")
TAG="v$REL-windows"
D=$(mktemp -d)
gh run download "$RUN" -n SombreroFileSearch-windows-x64 -D "$D"
ZIP=$(ls "$D"/*.zip)
cp packaging/windows/LEIA-ME.txt "$D/LEIA-ME.txt"
gh release create "$TAG" "$ZIP" "$D/LEIA-ME.txt" --target windows --prerelease \
  --title "Sombrero File Search $REL para Windows (prévia)" \
  --notes "Versão para Windows 10/11 (x64). Baixe o .zip, leia o LEIA-ME.txt (desbloquear antes de extrair) e abra SombreroFileSearch.exe. Sem instalador e sem administrador."
echo "publicado: $TAG"
