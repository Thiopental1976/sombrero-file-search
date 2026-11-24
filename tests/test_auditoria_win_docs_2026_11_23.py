#!/usr/bin/env python3
"""Testes das correções da auditoria de 23/11/2026 (frente Windows, docs_text, dupes e matriz):

1. boolean._fatiar_lotes respeita limite de linha de comando (Windows 32 KiB) e
   boolean.py usa errf UTF-8 com errors='replace'.
2. i18n._detect() detecta idioma no Windows (GetUserDefaultUILanguage / locale)
   mantendo precedência de SFS_LANG / LANG.
3. docs_text: EPUB com href URL-encoded (%20, acentos) não perde capítulos;
   ODT com <text:note> aninhado não dá RecursionError; main() não quebra com
   high-surrogate HTML (&#55296;).
4. dupes: st_ino == 0 (CIFS noserverino / FAT / FUSE) não colapsa todos os
   arquivos num único candidato; _walk(follow_symlinks=True) não entra em loop
   infinito em symlink cíclico.
5. Empacotamento Windows (build_windows.ps1 / windows.yml) inclui licenças
   AGPL-3/GPL-2 de terceiros; test_install_matrix_containers.sh aceita v1.x+.
"""
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lfs"))

import boolean  # noqa: E402
import docs_text  # noqa: E402
import dupes  # noqa: E402
import i18n  # noqa: E402

falhas = []


def ok(nome, cond, detalhe=""):
    if cond:
        print(f"ok  {nome}")
    else:
        print(f"FAIL {nome}: {detalhe}")
        falhas.append((nome, detalhe))


# ------------------------------------------------ 1. boolean: lotes Windows
def test_boolean_lotes_windows():
    ok("boolean: _fatiar_lotes existe", hasattr(boolean, "_fatiar_lotes"),
       "helper ausente")
    if not hasattr(boolean, "_fatiar_lotes"):
        return
    base = ["rg", "-l", "--null", "-i", "-e", "termo", "--"]
    caminhos = [f"C:\\Arquivos\\Projeto\\Subpasta_{i:04d}\\relatorio_muito_longo_{i:04d}_v2.txt"
                for i in range(400)]
    lotes = boolean._fatiar_lotes(caminhos, base, max_n=400, max_chars=24_000)
    ok("boolean: 400 caminhos longos fatiados em >1 lote sob 24 KiB",
       len(lotes) > 1 and sum(len(b) for b in lotes) == 400,
       f"len(lotes)={len(lotes)}, total={sum(len(b) for b in lotes)}")
    maior = max(len(subprocess.list2cmdline(base + b)) for b in lotes)
    ok("boolean: nenhum lote excede 32 KiB do CreateProcessW",
       maior < 30_000, f"maior cmd={maior} chars")

    # Caminho único maior que max_chars não entra em loop infinito
    gigante = ["C:\\" + ("a" * 30_000) + ".txt", "C:\\curto.txt"]
    lotes_g = boolean._fatiar_lotes(gigante, base, max_n=400, max_chars=24_000)
    ok("boolean: caminho gigante vai isolado sem travar",
       len(lotes_g) == 2 and lotes_g[0] == [gigante[0]] and lotes_g[1] == [gigante[1]],
       f"lotes_g={[len(x) for x in lotes_g]}")

    # Verifica que boolean.py não abre TemporaryFile(mode="w+") sem encoding/errors
    src = (ROOT / "lfs" / "boolean.py").read_text(encoding="utf-8")
    ok("boolean: errf usa encoding utf-8 + errors=replace",
       'TemporaryFile(mode="w+")' not in src,
       "TemporaryFile(mode='w+') estrito ainda presente em boolean.py")


# ------------------------------------------------ 2. i18n: detecção Windows
def test_i18n_windows():
    env_limpo = {}
    ok("i18n: _detect aceita hooks para Windows",
       hasattr(i18n, "_win_lang"), "_win_lang ausente")
    if not hasattr(i18n, "_win_lang"):
        return

    # 0x0416 = pt-BR, 0x0816 = pt-PT, 0x0409 = en-US
    ok("i18n: Windows pt-BR (0x0416) -> pt",
       i18n._detect(env=env_limpo, win_lcid=lambda: 0x0416, sys_locale=lambda: None) == "pt")
    ok("i18n: Windows pt-PT (0x0816) -> pt",
       i18n._detect(env=env_limpo, win_lcid=lambda: 0x0816, sys_locale=lambda: None) == "pt")
    ok("i18n: Windows en-US (0x0409) -> en",
       i18n._detect(env=env_limpo, win_lcid=lambda: 0x0409, sys_locale=lambda: None) == "en")
    ok("i18n: fallback locale 'Portuguese_Brazil' -> pt",
       i18n._detect(env=env_limpo, win_lcid=lambda: None, sys_locale=lambda: "Portuguese_Brazil") == "pt")
    ok("i18n: SFS_LANG=en prevalece sobre Windows pt-BR",
       i18n._detect(env={"SFS_LANG": "en"}, win_lcid=lambda: 0x0416, sys_locale=lambda: "pt_BR") == "en")


# ------------------------------------------------ 3. docs_text: EPUB / ODT / stdout
def _monta_epub_encoded() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf">'
                   '<manifest>'
                   '<item id="c0" href="cover.xhtml"/>'
                   '<item id="c1" href="Capitulo%201.xhtml"/>'
                   '<item id="c2" href="Se%C3%A7%C3%A3o%202.xhtml"/>'
                   '</manifest>'
                   '<spine><itemref idref="c0"/><itemref idref="c1"/><itemref idref="c2"/></spine>'
                   '</package>')
        z.writestr("OEBPS/cover.xhtml", "<html><body><p>Capa</p></body></html>")
        z.writestr("OEBPS/Capitulo 1.xhtml", "<html><body><p>achado_espaco_20</p></body></html>")
        z.writestr("OEBPS/Seção 2.xhtml", "<html><body><p>achado_acento_utf8 &#55296;</p></body></html>")
    return buf.getvalue()


def test_docs_text():
    dados = _monta_epub_encoded()
    txt = docs_text.extrai(dados, "epub")
    ok("docs_text: EPUB com %20 no href extrai capítulo 1",
       "achado_espaco_20" in txt, f"txt={txt!r}")
    ok("docs_text: EPUB com acento percent-encoded extrai capítulo 2",
       "achado_acento_utf8" in txt, f"txt={txt!r}")

    # ODT: árvore com 1200 <text:note><text:note-body> aninhados sem RecursionError
    ns = docs_text._TEXT_NS
    raiz = ET.Element(f"{{{ns}}}body")
    cur = raiz
    for _ in range(1200):
        nota = ET.SubElement(cur, f"{{{ns}}}note")
        cur = ET.SubElement(nota, f"{{{ns}}}note-body")
    p = ET.SubElement(cur, f"{{{ns}}}p")
    p.text = "fundo"
    try:
        docs_text._odt_parte(raiz)
        ok("docs_text: ODT notas aninhadas (1200 níveis) não dá RecursionError", True)
    except RecursionError as e:
        ok("docs_text: ODT notas aninhadas (1200 níveis) não dá RecursionError", False, str(e))

    # main() com high-surrogate &#55296; no HTML não estoura UnicodeEncodeError
    proc = subprocess.run([sys.executable, str(ROOT / "lfs" / "docs_text.py"), "epub"],
                          input=dados, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ok("docs_text: main() tolera high-surrogate HTML (exit 0)",
       proc.returncode == 0 and b"achado_acento_utf8" in proc.stdout,
       f"rc={proc.returncode} err={proc.stderr!r}")


# ------------------------------------------------ 4. dupes: st_ino==0 e ciclo symlink
def test_dupes_ino_zero_e_ciclo():
    with tempfile.TemporaryDirectory(prefix="sfs-dupes-test-") as td:
        a = os.path.join(td, "a.bin")
        b = os.path.join(td, "b.bin")
        payload = b"conteudo-identico-para-teste-de-duplicatas" * 20
        Path(a).write_bytes(payload)
        Path(b).write_bytes(payload)

        orig_lstat = os.lstat

        class FakeStat:
            def __init__(self, st):
                self.st_mode = st.st_mode
                self.st_dev = st.st_dev
                self.st_ino = 0
                self.st_size = st.st_size

        os.lstat = lambda p, *ar, **kw: FakeStat(orig_lstat(p, *ar, **kw))
        try:
            grupos = dupes.find_duplicates([td], min_size=1)
        finally:
            os.lstat = orig_lstat
        ok("dupes: st_ino == 0 encontra o par duplicado (não colapsa volume)",
           len(grupos) == 1 and len(grupos[0].members) == 2,
           f"grupos={len(grupos)}")

        # Symlink cíclico com follow_symlinks=True não entra em loop infinito
        sub = os.path.join(td, "sub")
        os.makedirs(sub)
        os.symlink(td, os.path.join(sub, "volta"))
        grupos2 = dupes.find_duplicates([td], min_size=1, follow_symlinks=True)
        ok("dupes: _walk(follow_symlinks=True) não trava em symlink cíclico",
           len(grupos2) == 1, f"grupos2={len(grupos2)}")


# ------------------------------------------------ 5. Windows licenças & matriz containers
def test_packaging_e_matriz():
    ps1 = (ROOT / "packaging" / "windows" / "build_windows.ps1").read_text(encoding="utf-8")
    ok("build_windows.ps1: inclui licenses/README.txt com AGPL (rga) e Poppler (GPL)",
       "licenses" in ps1 and "AGPL-3.0" in ps1 and "Poppler" in ps1,
       "falta bloco de licenças de terceiros em build_windows.ps1")
    ok("build_windows.ps1: copia README-Windows.txt no pacote",
       "README-Windows.txt" in ps1, "README-Windows.txt não copiado")

    mat = (ROOT / "tests" / "test_install_matrix_containers.sh").read_text(encoding="utf-8")
    ok("test_install_matrix_containers.sh: aceita versão 1.x+ (não travado em 0.)",
       "^Sombrero File Search 0\\." not in mat
       and bool(re.search(r"Sombrero File Search \[0-9\]", mat)),
       "ainda exige versão 0.x")
    ok("test_install_matrix_containers.sh: preserva $WORK quando FAIL > 0",
       'FAIL' in mat.split("cleanup()")[1].split("}")[0],
       "cleanup() apaga logs mesmo em falha")


if __name__ == "__main__":
    test_boolean_lotes_windows()
    test_i18n_windows()
    test_docs_text()
    test_dupes_ino_zero_e_ciclo()
    test_packaging_e_matriz()
    if falhas:
        print(f"\n{len(falhas)} falha(s)")
        sys.exit(1)
    print("\nTUDO OK")
