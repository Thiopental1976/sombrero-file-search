# SPDX-License-Identifier: GPL-3.0-or-later
# Monta o pacote Windows do SFS (F3). Rodar na raiz do repo, com bin\ já preenchido
# (rg/fd/rga/pdftotext + bin\licenses — o passo "motores" do CI) e PySide6 + pyinstaller + pillow.
# Requer env vars RGV, FDV, RGAV e POPPLERV (fonte única em .github/workflows/windows.yml).
# Saída: dist\SombreroFileSearch\ e dist\SombreroFileSearch-<versão>-windows-x64.zip
$ErrorActionPreference = "Stop"

foreach ($v in "RGV", "FDV", "RGAV", "POPPLERV") {
  if (-not (Get-Item "Env:$v" -ErrorAction SilentlyContinue).Value) {
    throw "Variável de ambiente obrigatória ausente: $v"
  }
}

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
if (-not (Test-Path "bin\licenses")) {
  throw "bin\licenses ausente: os textos de licença dos motores são obrigatórios"
}
Copy-Item "bin\licenses\*" -Destination "$pkg\licenses" -Recurse -Force
Remove-Item "$pkg\bin\licenses" -Recurse -Force -ErrorAction SilentlyContinue
foreach ($reqLic in "ripgrep-all-LICENSE.md", "poppler-COPYING") {
  if (-not (Test-Path "$pkg\licenses\$reqLic")) {
    throw "Licença obrigatória ausente no pacote: $reqLic"
  }
}

$licReadme = @"
Third-party components bundled in this Windows package
======================================================

1. ripgrep-all (bin\rga.exe, bin\rga-preproc.exe)
   Version : $($env:RGAV) (unmodified upstream release binaries)
   License : AGPL-3.0-or-later (full text in ripgrep-all-LICENSE.md)
   Source  : https://github.com/phiresky/ripgrep-all/tree/$($env:RGAV)

2. Poppler (bin\pdftotext.exe and Poppler DLLs)
   Version : $($env:POPPLERV) (poppler-windows upstream release)
   License : GPL-2.0-or-later (full text in poppler-COPYING)
   Source  : https://github.com/oschwartz10612/poppler-windows/releases/tag/v$($env:POPPLERV)
             https://poppler.freedesktop.org/

3. ripgrep (bin\rg.exe)
   Version : $($env:RGV)
   License : MIT / Unlicense
   Source  : https://github.com/BurntSushi/ripgrep/tree/$($env:RGV)

4. fd (bin\fd.exe)
   Version : $($env:FDV)
   License : MIT / Apache-2.0
   Source  : https://github.com/sharkdp/fd/tree/$($env:FDV)

5. PySide6 / Qt6 (LGPL-3.0) and CPython (PSF-2.0)
   Sources : https://code.qt.io/cgit/pyside/pyside-setup.git/
             https://github.com/python/cpython
"@
Set-Content -Path "$pkg\licenses\README.txt" -Value $licReadme -Encoding utf8

$rel = python -c "import sys; sys.path.insert(0,'lfs'); import version; print(version.RELEASE)"
$commit = (git log -1 --format="%h (%cs)")
Set-Content -Path "$pkg\VERSION" -Value $commit -Encoding utf8

# Manifesto de integridade contra corrupcao (todos os arquivos menos ele mesmo;
# formato sha256sum: "<hash>  <caminho/com/barra>", UTF-8 sem BOM, LF).
$manifestPath = Join-Path $pkg "MANIFEST.sha256"
if (Test-Path $manifestPath) { Remove-Item $manifestPath }
$pkgFull = (Resolve-Path $pkg).Path.TrimEnd('\', '/')
$linhas = Get-ChildItem -Path $pkgFull -Recurse -File |
  ForEach-Object {
    $relPath = $_.FullName.Substring($pkgFull.Length + 1).Replace('\', '/')
    if ($relPath -ne "MANIFEST.sha256") {
      $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      [PSCustomObject]@{ Rel = $relPath; Line = "$hash  $relPath" }
    }
  } |
  Sort-Object -Property Rel |
  ForEach-Object { $_.Line }
$utf8SemBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($manifestPath, (($linhas -join "`n") + "`n"), $utf8SemBom)

$zip = "dist\SombreroFileSearch-$rel-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $pkg -DestinationPath $zip
"pacote: $zip  ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)"
exit 0
