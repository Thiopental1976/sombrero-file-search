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
Copy-Item LICENSE, README.md, packaging\windows\README-Windows.txt -Destination $pkg

# Compliance de licenças de terceiros (AGPL-3 para ripgrep-all, GPL-2 para Poppler, etc.)
New-Item -ItemType Directory -Force "$pkg\licenses" | Out-Null
if (Test-Path "bin\licenses") {
  Copy-Item "bin\licenses\*" -Destination "$pkg\licenses" -Recurse -Force
  Remove-Item "$pkg\bin\licenses" -Recurse -Force -ErrorAction SilentlyContinue
}
$rgv = if ($env:RGV) { $env:RGV } else { "15.2.0" }
$fdv = if ($env:FDV) { $env:FDV } else { "v10.4.2" }
$rgav = if ($env:RGAV) { $env:RGAV } else { "v0.10.9" }
$popv = if ($env:POPPLERV) { $env:POPPLERV } else { "26.09.0-0" }
$licReadme = @"
Third-party components bundled in this Windows package
======================================================

1. ripgrep-all (bin\rga.exe, bin\rga-preproc.exe)
   Version : $rgav (unmodified upstream release binaries)
   License : AGPL-3.0-or-later (see ripgrep-all-LICENSE.md alongside, if present)
   Source  : https://github.com/phiresky/ripgrep-all/tree/$rgav

2. Poppler (bin\pdftotext.exe and Poppler DLLs)
   Version : $popv (poppler-windows upstream release)
   License : GPL-2.0-or-later (see poppler-COPYING alongside, if present)
   Source  : https://github.com/oschwartz10612/poppler-windows/releases/tag/v$popv
             https://poppler.freedesktop.org/

3. ripgrep (bin\rg.exe)
   Version : $rgv
   License : MIT / Unlicense
   Source  : https://github.com/BurntSushi/ripgrep/tree/$rgv

4. fd (bin\fd.exe)
   Version : $fdv
   License : MIT / Apache-2.0
   Source  : https://github.com/sharkdp/fd/tree/$fdv

5. PySide6 / Qt6 (LGPL-3.0) and CPython (PSF-2.0)
   Sources : https://code.qt.io/cgit/pyside/pyside-setup.git/
             https://github.com/python/cpython
"@
Set-Content -Path "$pkg\licenses\README.txt" -Value $licReadme -Encoding utf8

$rel = python -c "import sys; sys.path.insert(0,'lfs'); import version; print(version.RELEASE)"
$commit = (git log -1 --format="%h (%cs)")
Set-Content -Path "$pkg\VERSION" -Value $commit -Encoding utf8

$zip = "dist\SombreroFileSearch-$rel-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $pkg -DestinationPath $zip
"pacote: $zip  ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
exit 0
