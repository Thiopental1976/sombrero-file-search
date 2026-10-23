#!/bin/bash
# Anexa o pacote Windows (beta) à release do Linux. SÓ rodar com o ok do Rodrigo.
# Uso: publicar_release.sh <run-id do CI com o artefato aprovado>
#
# Mesma release, e não uma prévia à parte: o atualizador (updates.py) e o site
# (release.js) leem /releases/latest, que ignora prerelease — uma "v1.3.0-windows"
# marcada como prévia nunca seria oferecida a ninguém. O "beta" vai no nome da
# seção das notas e no README-Windows.txt.
set -euo pipefail
RUN=${1:?run id do CI}
cd "$(dirname "$0")/../.."
REL=$(python3 -c "import sys; sys.path.insert(0,'lfs'); import version; print(version.RELEASE)")
TAG="v$REL"

# A release do Linux tem de existir antes; este script não cria release.
gh release view "$TAG" --json tagName >/dev/null || { echo "release $TAG não existe: publique o Linux antes" >&2; exit 1; }

# O artefato tem de ter sido construído do commit da tag.
SHA_TAG=$(git rev-list -n1 "$TAG")
SHA_RUN=$(gh run view "$RUN" --json headSha -q .headSha)
[ "$SHA_TAG" = "$SHA_RUN" ] || { echo "run $RUN é de ${SHA_RUN:0:7}, a tag $TAG é de ${SHA_TAG:0:7}" >&2; exit 1; }
[ "$(gh run view "$RUN" --json conclusion -q .conclusion)" = success ] || { echo "run $RUN não terminou verde" >&2; exit 1; }

D=$(mktemp -d)
gh run download "$RUN" -n SombreroFileSearch-windows-x64 -D "$D"
ZIP="$D/SombreroFileSearch-$REL-windows-x64.zip"
[ -f "$ZIP" ] || { echo "esperava $(basename "$ZIP"), veio: $(ls "$D")" >&2; exit 1; }
cp packaging/windows/README-Windows.txt "$D/README-Windows.txt"
gh release upload "$TAG" "$ZIP" "$D/README-Windows.txt"

# Seção do Windows nas notas, uma vez só (rodar de novo não duplica).
NOTAS=$(gh release view "$TAG" --json body -q .body)
if ! grep -q "^## Windows (beta)" <<<"$NOTAS"; then
  gh release edit "$TAG" --notes "$NOTAS

## Windows (beta)

Windows 10/11, 64-bit: download \`$(basename "$ZIP")\`, unblock it (Properties → Unblock), extract and run \`SombreroFileSearch.exe\`. No installer, no administrator rights. The Windows build is new and still being tested; Linux is the primary platform. Steps in \`README-Windows.txt\`."
fi
echo "anexado a $TAG: $(basename "$ZIP") + README-Windows.txt"
