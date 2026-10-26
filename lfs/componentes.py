"""Programas externos de que a busca depende, e o que dizer quando um falta.

26/10/2026 (pedido do Rodrigo): sem o pdftotext cada PDF virava um "erro de
leitura"; sem fd/rg a busca caía no walker Python sem dizer nada na janela;
sem rga, "documentos não lidos" ficava escondido na barra. Quem usa conclui
que o Sombrero falhou. Aqui mora, para os três canais (funil, CLI, diálogo
da GUI), o que cada programa faz e como resolver: o que vem no pacote
completo manda baixar o pacote; o que vem do sistema dá o comando da distro.

Frases em EN-US, traduzidas na renderização (i18n.t) como o resto do funil.
"""
from __future__ import annotations
import os

try:                       # pacote (GUI) e flat (cli.py/testes)
    from . import plat
except ImportError:
    import plat                                  # type: ignore

SITE_INSTALL = "https://sombrerofilesearch.com/#install"

# programa -> o que deixou de funcionar sem ele
EFEITO = {
    "fd": "name search ran on the slower built-in walker",
    "rg": "content search ran on the slower built-in reader, which does not read UTF-16 files",
    "rga": "text inside PDF, docx, epub and the like was not read (they were searched as plain text)",
    "pdftotext": "the text of these PDFs was not read",
    "pandoc": "the text of these documents was not read",
}
EFEITO_OUTRO = "the documents that need it were not read"

COMO_PACOTE = "Download the complete Sombrero package, which includes it: {url}"
COMO_SISTEMA = "Install it from your system's packages: {cmd}"
COMO_SISTEMA_SEM_CMD = "Install the package {pkg} from your system's packages"

SOURCE_STRINGS = frozenset(EFEITO.values()) | {EFEITO_OUTRO, COMO_PACOTE, COMO_SISTEMA,
                                               COMO_SISTEMA_SEM_CMD}

# Vêm no pacote completo: rg, fd e rga no AppImage e no zip do Windows (o .deb
# traz o rga e recomenda rg/fd ao apt); o zip do Windows traz também o
# pdftotext. No Linux o pdftotext e o pandoc são do sistema.
_NO_PACOTE = frozenset({"fd", "rg", "rga"})
_NO_PACOTE_WIN = _NO_PACOTE | {"pdftotext"}

# programa -> {gestor: pacote da distro}
_PACOTE_SISTEMA = {
    "pdftotext": {"apt": "poppler-utils", "dnf": "poppler-utils", "rpm-ostree": "poppler-utils",
                  "pacman": "poppler", "zypper": "poppler-tools"},
    "pandoc": {"apt": "pandoc", "dnf": "pandoc", "rpm-ostree": "pandoc",
               "pacman": "pandoc", "zypper": "pandoc"},
}
_COMANDO = {
    "apt": "sudo apt install {pkg}",
    "dnf": "sudo dnf install {pkg}",
    "rpm-ostree": "rpm-ostree install {pkg}",     # Silverblue/Bazzite: sistema imutável
    "pacman": "sudo pacman -S {pkg}",
    "zypper": "sudo zypper install {pkg}",
}


def gestor(os_release: str = "/etc/os-release", ostree: str = "/run/ostree-booted"):
    """O gerenciador de pacotes da distro, pelo ID/ID_LIKE do os-release, ou None."""
    if plat.IS_WIN:
        return None
    if os.path.exists(ostree):
        return "rpm-ostree"
    ids = []
    try:
        with open(os_release, encoding="utf-8") as f:
            for linha in f:
                k, _, v = linha.strip().partition("=")
                if k in ("ID", "ID_LIKE"):
                    ids += v.strip('"').lower().split()
    except OSError:
        return None
    for i in ids:
        if i in ("debian", "ubuntu"):
            return "apt"
        if i in ("fedora", "rhel", "centos"):
            return "dnf"
        if i == "arch":
            return "pacman"
        if i.startswith("suse") or i.startswith("opensuse"):
            return "zypper"
    return None


def efeito(prog: str) -> str:
    return EFEITO.get(prog, EFEITO_OUTRO)


def orientacao(prog: str, g=None) -> dict:
    """Como resolver a falta de `prog`: {'como': frase EN com {campos},
    'args': campos, 'cmd': comando ou None, 'url': página ou None}."""
    if prog in (_NO_PACOTE_WIN if plat.IS_WIN else _NO_PACOTE):
        return {"como": COMO_PACOTE, "args": {"url": SITE_INSTALL},
                "cmd": None, "url": SITE_INSTALL}
    g = gestor() if g is None else g
    tabela = _PACOTE_SISTEMA.get(prog, {})
    pkg = tabela.get(g) or tabela.get("apt") or prog     # sem gestor: o nome do Debian
    if g in _COMANDO:
        cmd = _COMANDO[g].format(pkg=pkg)
        return {"como": COMO_SISTEMA, "args": {"cmd": cmd}, "cmd": cmd, "url": None}
    return {"como": COMO_SISTEMA_SEM_CMD, "args": {"pkg": pkg}, "cmd": None, "url": None}


def texto_orientacao(prog: str, tr=None) -> str:
    tr = tr or (lambda s: s)
    o = orientacao(prog)
    return tr(o["como"]).format(**o["args"])
