# SPDX-License-Identifier: GPL-3.0-or-later
# Monta o pacote Windows do SFS (F3). Rodar na raiz do repo, com bin\ já preenchido
# (rg/fd/rga/pdftotext — o passo "motores" do CI) e PySide6 + pyinstaller + pillow.
# Saída: dist\SombreroFileSearch\ e dist\SombreroFileSearch-<versão>-windows-x64.zip
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force dist | Out-Null

# ícone .ico a partir do PNG (vários tamanhos num arquivo só)
python -c "from PIL import Image; Image.open('assets/icon_256.png').save('dist/sfs.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE) { throw "ico" }

python -m PyInstaller --noconfirm --clean --distpath dist --workpath dist\build packaging\windows\sfs.spec
if ($LASTEXITCODE) { throw "pyinstaller" }

$pkg = "dist\SombreroFileSearch"
Copy-Item bin -Destination "$pkg\bin" -Recurse -Force
New-Item -ItemType Directory -Force "$pkg\assets" | Out-Null
Copy-Item assets\icon*.png -Destination "$pkg\assets"
Copy-Item LICENSE, README.md -Destination $pkg
$rel = python -c "import sys; sys.path.insert(0,'lfs'); import version; print(version.RELEASE)"
$commit = (git log -1 --format="%h (%cs)")
Set-Content -Path "$pkg\VERSION" -Value $commit -Encoding utf8

$zip = "dist\SombreroFileSearch-$rel-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $pkg -DestinationPath $zip
"pacote: $zip  ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
exit 0
