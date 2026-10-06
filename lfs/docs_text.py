#!/usr/bin/env python3
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Texto de docx/odt/epub sem pandoc — adaptador do rga, só com a stdlib.

Por que existe (28/09/2026, decisão do Rodrigo): o rga lê docx/odt/epub pelo
pandoc, e o pandoc são ~160–200 MB. Embuti-lo multiplicava o .deb por 20; não
embuti-lo deixava a busca em documentos pela metade em toda distro sem pandoc
(foi o que se viu no ServidorCedro). Os três formatos são zip com XML dentro:
extrair o texto é trabalho de stdlib. O pandoc segue valendo para os formatos
raros que só ele lê (fb2, ipynb, html).

Contrato com o rga (custom adapter, ver engine.rga_args): o arquivo chega pelo
stdin, a extensão vem no argv, o texto sai no stdout em UTF-8, um parágrafo por
linha — é a linha que o SFS mostra como trecho do achado. Falha = código != 0
com a causa no stderr; o rga a repassa e o motor a conta como incompleto.
Nunca "sucesso" com texto parcial: um membro grande demais é erro, não corte.

Segurança: o XML vem de arquivo qualquer do disco. O ElementTree não resolve
entidade externa, e o expat (>= 2.4.1, o do Python 3.10+) barra a expansão em
cascata ("billion laughs"). Os membros do zip são lidos com teto de tamanho
DESCOMPACTADO, que é o que um zip-bomba estoura.
"""
from __future__ import annotations
import io, posixpath, re, sys, zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

# Entra na chave do cache do rga (campo "version" do adaptador): mudou a
# extração, sobe o número — senão o rga devolve o texto antigo do cache.
VERSAO = 1

EXTENSOES = ("docx", "odt", "epub")
MIMETYPES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/epub+zip",
)

# Teto por membro, descompactado. Texto de verdade não chega perto: um romance
# inteiro em XML do Word tem poucos MB.
MAX_MEMBRO = 256 * 1024 * 1024


class ErroDocumento(Exception):
    """Documento ilegível, com a causa em inglês (vai para o stderr do rga)."""


def _le_membro(z: zipfile.ZipFile, nome: str) -> bytes:
    with z.open(nome) as f:
        dados = f.read(MAX_MEMBRO + 1)
    if len(dados) > MAX_MEMBRO:
        raise ErroDocumento(f"{nome}: more than {MAX_MEMBRO >> 20} MiB uncompressed")
    return dados


def _xml(dados: bytes, nome: str):
    try:
        return ET.fromstring(dados)
    except ET.ParseError as e:
        raise ErroDocumento(f"{nome}: invalid XML ({e})") from None


def _local(tag) -> str:
    """'{namespace}p' -> 'p'. Comentário/instrução de processamento não têm tag str."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _percorre(raiz, abre, fecha, cauda=lambda s: s):
    """Caminha a árvore SEM recursão (XML fundo não derruba o processo):
    abre(elem) devolve o texto a emitir na entrada e True para pular os filhos;
    fecha(elem) o texto na saída. O .tail de cada elemento vem depois dele,
    passado por cauda()."""
    out = []
    pilha = [(raiz, False)]
    while pilha:
        el, saindo = pilha.pop()
        if saindo:
            out.append(fecha(el))
            if el is not raiz and el.tail:
                out.append(cauda(el.tail))
            continue
        texto, pula = abre(el)
        out.append(texto)
        pilha.append((el, True))
        if not pula:
            pilha.extend((f, False) for f in reversed(el))
    return "".join(out)


def _limpa(texto: str) -> str:
    """Um parágrafo por linha, sem linha vazia nem espaço nas pontas: a linha é
    o trecho que o SFS mostra no achado, e linha em branco não casa nada."""
    linhas = (l.strip() for l in texto.split("\n"))
    return "".join(l + "\n" for l in linhas if l)


# ------------------------------------------------------------------ docx
def _docx_parte(raiz) -> str:
    # No XML do Word o texto visível mora só em w:t; o .tail dos elementos é
    # indentação do arquivo, não conteúdo — por isso é apagado antes.
    for el in raiz.iter():
        el.tail = None

    def abre(el):
        n = _local(el.tag)
        if n == "t":
            return el.text or "", True
        if n == "tab":
            return "\t", True
        if n in ("br", "cr"):
            return "\n", True
        if n == "noBreakHyphen":
            return "-", True
        # texto apagado no controle de alterações e código de campo não são o
        # que o leitor vê na página; mc:Fallback repete a caixa de texto que o
        # mc:Choice já trouxe (sairia duplicada)
        if n in ("del", "delText", "instrText", "Fallback"):
            return "", True
        return "", False

    def fecha(el):
        return "\n" if _local(el.tag) == "p" else ""

    return _percorre(raiz, abre, fecha)


def docx(z: zipfile.ZipFile) -> str:
    nomes = set(z.namelist())
    if "word/document.xml" not in nomes:
        raise ErroDocumento("word/document.xml missing: not a Word document")
    extras = sorted(n for n in nomes if re.fullmatch(
        r"word/(header\d*|footer\d*|footnotes|endnotes|comments)\.xml", n))
    return "".join(_docx_parte(_xml(_le_membro(z, n), n))
                   for n in ["word/document.xml"] + extras)


# ------------------------------------------------------------------- odt
_BLOCO_ODT = {"p", "h"}
_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def _odt_parte(raiz) -> str:
    # No ODF o texto vale só dentro de parágrafo/título (text:p, text:h); fora
    # deles o que há é indentação entre elementos de estrutura. Passo 1: quem
    # está dentro de um bloco, e apagar o .tail de quem está fora.
    dentro = set()
    pilha = [(raiz, False)]
    while pilha:
        el, pai_dentro = pilha.pop()
        if pai_dentro:
            dentro.add(id(el))
        else:
            el.tail = None
        eh_bloco = pai_dentro or _local(el.tag) in _BLOCO_ODT
        pilha.extend((f, eh_bloco) for f in el)

    notas = []

    def abre(el):
        n = _local(el.tag)
        if n == "note":
            # nota de rodapé: o corpo vai para o fim (como o pandoc faz); no meio
            # da frase ele partiria a busca por uma frase que atravessa a nota
            notas.append(el)
            return "", True
        if n == "s":                       # N espaços seguidos: <text:s text:c="N"/>
            try:
                c = int(el.get(f"{{{_TEXT_NS}}}c", "1"))
            except ValueError:
                c = 1
            return " " * max(1, min(c, 1000)), True
        if n == "tab":
            return "\t", True
        if n == "line-break":
            return "\n", True
        if n in _BLOCO_ODT or id(el) in dentro:
            return _espaco_odf(el.text or ""), False
        return "", False

    def fecha(el):
        return "\n" if _local(el.tag) in _BLOCO_ODT else ""

    texto = _percorre(raiz, abre, fecha, cauda=_espaco_odf)
    for nota in notas:
        for corpo in nota:
            if _local(corpo.tag) == "note-body":
                texto += _odt_parte(corpo)
    return texto


def _espaco_odf(s: str) -> str:
    """Regra do ODF (§6.1.2): quebra de linha e tab LITERAIS no texto valem como
    espaço, e espaços seguidos viram um — os espaços reais vêm de <text:s>,
    <text:tab> e <text:line-break>, tratados à parte."""
    return re.sub(r"[ \t\r\n]+", " ", s)


def odt(z: zipfile.ZipFile) -> str:
    nomes = set(z.namelist())
    if "content.xml" not in nomes:
        raise ErroDocumento("content.xml missing: not an OpenDocument file")
    # styles.xml guarda cabeçalho e rodapé das páginas-mestras
    return "".join(_odt_parte(_xml(_le_membro(z, n), n))
                   for n in ("content.xml", "styles.xml") if n in nomes)


# ------------------------------------------------------------------ epub
class _Html(HTMLParser):
    BLOCO = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
             "section", "article", "blockquote", "pre", "dt", "dd", "hr", "td", "th"}
    PULA = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.pulando = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.PULA:
            self.pulando += 1
        elif tag in self.BLOCO:
            self.out.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in self.BLOCO:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.PULA:
            self.pulando = max(0, self.pulando - 1)
        elif tag in self.BLOCO:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.pulando:
            self.out.append(data)


def _html_texto(dados: bytes) -> str:
    m = re.search(rb"""<\?xml[^>]*encoding=["']([A-Za-z0-9._-]+)""", dados[:200])
    try:
        s = dados.decode(m.group(1).decode() if m else "utf-8")
    except (LookupError, UnicodeDecodeError):
        s = dados.decode("utf-8", errors="replace")
    p = _Html()
    p.feed(s)
    p.close()
    # espaço em branco do HTML não é conteúdo: colapsa dentro da linha e tira
    # as linhas vazias que os blocos aninhados deixam
    linhas = (re.sub(r"[ \t\r\f\v]+", " ", l).strip() for l in "".join(p.out).split("\n"))
    return "".join(l + "\n" for l in linhas if l)


def _epub_ordem(z: zipfile.ZipFile, nomes: set) -> list:
    """Capítulos na ordem de leitura (spine do OPF). Se o empacotamento estiver
    torto, todo (x)html do zip em ordem alfabética — melhor ler tudo fora de
    ordem do que nada."""
    try:
        cont = _xml(_le_membro(z, "META-INF/container.xml"), "container.xml")
        opf_nome = next(e.get("full-path") for e in cont.iter() if _local(e.tag) == "rootfile")
        opf = _xml(_le_membro(z, opf_nome), opf_nome)
        base = posixpath.dirname(opf_nome)
        itens = {e.get("id"): e.get("href") for e in opf.iter() if _local(e.tag) == "item"}
        ordem = []
        for e in opf.iter():
            if _local(e.tag) == "itemref":
                href = itens.get(e.get("idref"))
                if href:
                    n = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
                    if n in nomes and n not in ordem:
                        ordem.append(n)
        if ordem:
            return ordem
    except (ErroDocumento, KeyError, StopIteration, TypeError):
        pass
    return sorted(n for n in nomes if n.lower().endswith((".xhtml", ".html", ".htm")))


def epub(z: zipfile.ZipFile) -> str:
    nomes = set(z.namelist())
    capitulos = _epub_ordem(z, nomes)
    if not capitulos:
        raise ErroDocumento("no (x)html chapters: not an EPUB book")
    return "".join(_html_texto(_le_membro(z, n)) for n in capitulos)


# ------------------------------------------------------------- entrada
LEITORES = {"docx": docx, "odt": odt, "epub": epub}


def extrai(dados: bytes, ext: str) -> str:
    ext = ext.lower().lstrip(".")
    leitor = LEITORES.get(ext)
    if leitor is None:
        raise ErroDocumento(f"unsupported extension: {ext!r}")
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as e:
        raise ErroDocumento(f"not a valid zip container ({e})") from None
    with z:
        try:
            return _limpa(leitor(z))
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError) as e:
            # membro corrompido, cifrado (RuntimeError) ou com compressão exótica
            raise ErroDocumento(f"damaged or encrypted member ({e})") from None


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: docs_text.py EXTENSION < file > text", file=sys.stderr)
        return 2
    try:
        texto = extrai(sys.stdin.buffer.read(), argv[0])
    except ErroDocumento as e:
        print(f"sombrero docs_text: {e}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(texto.encode("utf-8", errors="surrogateescape"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
