#!/usr/bin/env python3
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Sombrero File Search — há versão nova? (e o upgrade, onde der).

Decisões do Rodrigo (22/10/2026), que este módulo implementa:
  1. "Atualização" = nova RELEASE no GitHub. Commit no main é trabalho em
     andamento (o Windows passa por ele) e NÃO aciona aviso. Pré-release e
     rascunho também não: usamos /releases/latest, que já os exclui.
  2. O botão atualiza onde dá: código-fonte (install.sh) e AppImage se trocam
     sozinhos; .deb (exige root) e Windows (exe aberto não se sobrescreve)
     baixam o pacote e abrem o instalador / a pasta.
  3. Consulta ao abrir, no máximo 1×/dia, desligável. Sem rede = silêncio.

Sem Qt: a GUI só chama `check()` e `apply()` numa thread e mostra o resultado,
e os testes rodam sem tela nem rede (`fetch` e o downloader são injetáveis).
"""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time
import urllib.request

try:
    from . import version, plat
    from .i18n import t
except ImportError:
    import version, plat                     # type: ignore
    from i18n import t                       # type: ignore

REPO = "Thiopental1976/sombrero-file-search"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CHECK_EVERY = 24 * 3600                      # 1×/dia
_UA = "sombrero-file-search-updater"         # a API do GitHub recusa pedido sem User-Agent

_ROOT = version._ROOT                        # …/<PREFIX> instalado, ou o worktree


class UpdateError(Exception):
    """Falha do upgrade com frase humana já traduzida. NÃO é OSError de propósito:
    o humane.human_error deixa exceção de domínio passar com o texto dela, e
    "download cortado" ou o fim do log do install.sh valem mais que uma frase genérica."""


# ----------------------------------------------------------------- versões
def parse(v: str) -> tuple | None:
    """'v1.2.0' / '1.2.0' -> (1, 2, 0). Sufixo ('-windows', '-rc1') = None: não
    é uma release estável comparável, e um aviso errado é pior que nenhum."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest: str, current: str = version.RELEASE) -> bool:
    a, b = parse(latest), parse(current)
    return bool(a and b and a > b)


# ----------------------------------------------------------------- de onde rodo?
def install_kind(root: str | None = None, env=None) -> str:
    """'windows' | 'appimage' | 'deb' | 'dev' | 'source'.

    A ordem importa: o AppImage monta em /tmp/.mount_* e o .deb vive em /usr —
    olhar o caminho antes do $APPIMAGE confundiria os dois. 'dev' é o worktree
    com .git: quem desenvolve atualiza com git, nunca por cima do próprio repo."""
    root = root or _ROOT
    env = os.environ if env is None else env
    if plat.IS_WIN and plat.frozen():
        return "windows"
    if env.get("APPIMAGE") and os.path.isfile(env["APPIMAGE"]):
        return "appimage"
    if os.path.abspath(root).startswith("/usr/"):
        return "deb"
    if os.path.exists(os.path.join(root, ".git")):
        return "dev"
    return "source"


# ----------------------------------------------------------------- consulta
def fetch_latest(timeout: float = 8.0) -> dict:
    """A última release estável, já no formato que o resto do módulo usa."""
    req = urllib.request.Request(API_LATEST, headers={
        "Accept": "application/vnd.github+json", "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return {
        "tag": d.get("tag_name", ""),
        "name": d.get("name") or d.get("tag_name", ""),
        "page": d.get("html_url") or RELEASES_PAGE,
        "notes": d.get("body") or "",
        "published": (d.get("published_at") or "")[:10],
        "tarball": d.get("tarball_url", ""),
        "assets": [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
                    "size": int(a.get("size") or 0), "digest": a.get("digest") or ""}
                   for a in d.get("assets", [])],
    }


def check(cfg: dict, force: bool = False, now: float | None = None,
          fetch=None) -> dict | None:
    """Consulta (ou reaproveita a consulta de hoje) e devolve a release se for
    MAIS NOVA que a instalada; None caso contrário. Grava em cfg["updates"] —
    quem chama salva o cfg. Erro de rede sobe para quem pediu na mão (`force`)
    e morre em silêncio na consulta automática."""
    st = cfg.setdefault("updates", {})
    now = time.time() if now is None else now
    if not force:
        if not st.get("auto", True):
            return None
        if "last_check" in st and now - float(st["last_check"]) < CHECK_EVERY:
            rel = st.get("latest")
            return rel if rel and is_newer(rel.get("tag", "")) else None
    try:
        rel = (fetch or fetch_latest)()
    except Exception:
        if force:
            raise
        return None
    st["last_check"] = now
    st["latest"] = rel
    return rel if is_newer(rel.get("tag", "")) else None


# ----------------------------------------------------------------- o pacote certo
def pick_asset(kind: str, rel: dict) -> dict | None:
    """O arquivo da release que serve para ESTA instalação (None = não há)."""
    for a in rel.get("assets", []):
        n = a["name"].lower()
        if kind == "appimage" and n.endswith("-x86_64.appimage"):
            return a
        if kind == "deb" and n.endswith("_all.deb"):
            return a
        if kind == "windows" and n.endswith(".zip") and "windows" in n:
            return a
    if kind == "source" and rel.get("tarball"):
        return {"name": f"sombrero-file-search-{rel['tag']}.tar.gz",
                "url": rel["tarball"], "size": 0, "digest": ""}
    return None


def can_apply(kind: str, rel: dict) -> bool:
    return kind != "dev" and pick_asset(kind, rel) is not None


# ----------------------------------------------------------------- download
def download(url: str, dest: str, size: int = 0, digest: str = "",
             progress=None, cancelled=lambda: False) -> str:
    """Baixa para `dest + '.part'` e só renomeia no fim: um download cortado
    nunca fica com cara de arquivo pronto. Confere tamanho e, quando o GitHub
    informa, o sha256 — um AppImage truncado que substitui o bom é o pior
    desfecho possível de um botão de atualizar."""
    part = dest + ".part"
    h = hashlib.sha256()
    got = 0
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as f:
            total = size or int(r.headers.get("Content-Length") or 0)
            while True:
                if cancelled():
                    raise InterruptedError("cancelled")
                buf = r.read(1 << 16)
                if not buf:
                    break
                f.write(buf); h.update(buf); got += len(buf)
                if progress:
                    progress(got, total)
        if size and got != size:
            raise UpdateError(t("The download was cut short ({got} of {size} bytes). Nothing was changed.",
                                got=got, size=size))
        if digest.startswith("sha256:") and h.hexdigest() != digest[7:].lower():
            raise UpdateError(t("The download does not match the release (sha256). Nothing was changed."))
        os.replace(part, dest)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return dest


def downloads_dir() -> str:
    d = ""
    if not plat.IS_WIN:
        try:
            d = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True,
                               text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            d = ""
    d = d if d and os.path.isdir(d) else os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(d, exist_ok=True)
    return d


# ----------------------------------------------------------------- aplicar
def _safe_extract(tar_path: str, into: str) -> str:
    """Extrai o tarball da release e devolve a pasta de topo. Recusa caminho
    absoluto / '..' (o filtro 'data' faz isso no Python ≥ 3.12; antes, à mão)."""
    with tarfile.open(tar_path) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(into, filter="data")
        else:
            base = os.path.realpath(into)
            for m in tf.getmembers():
                p = os.path.realpath(os.path.join(into, m.name))
                if not (p == base or p.startswith(base + os.sep)) or m.issym() or m.islnk():
                    raise UpdateError(t("Unsafe path in the release archive: {name}", name=m.name))
            tf.extractall(into)
    tops = [e for e in os.listdir(into) if os.path.isdir(os.path.join(into, e))]
    if len(tops) != 1:
        raise UpdateError(t("Unexpected layout in the release archive."))
    return os.path.join(into, tops[0])


def apply(kind: str, rel: dict, progress=None, cancelled=lambda: False,
          root: str | None = None, env=None, run=subprocess.run) -> dict:
    """Executa o upgrade. Devolve {"restart": [argv] | None, "opened": caminho | None}.

    'restart' = a instalação JÁ foi trocada; a GUI pergunta e relança.
    'opened'  = baixamos o pacote e o entregamos ao sistema (.deb / Windows);
                o usuário termina o processo fora do app."""
    root = root or _ROOT
    env = os.environ if env is None else env
    asset = pick_asset(kind, rel)
    if kind == "dev" or asset is None:
        raise UpdateError(t("This release has no package for this installation — see the release page."))

    if kind == "appimage":
        cur = env["APPIMAGE"]
        # Mesmo diretório = mesmo sistema de arquivos: o os.replace final é
        # atômico, e o atalho que o usuário criou para o arquivo continua valendo
        # (mantemos o NOME antigo de propósito). Linux deixa trocar o arquivo de
        # um AppImage em execução: o processo segura o inode velho até sair.
        tmp = os.path.join(os.path.dirname(cur), "." + os.path.basename(cur) + ".new")
        download(asset["url"], tmp, asset["size"], asset["digest"], progress, cancelled)
        os.chmod(tmp, 0o755)
        os.replace(tmp, cur)
        return {"restart": [cur], "opened": None}

    if kind == "source":
        with tempfile.TemporaryDirectory(prefix="sfs-update-") as td:
            tgz = download(asset["url"], os.path.join(td, "src.tar.gz"),
                           progress=progress, cancelled=cancelled)
            src = _safe_extract(tgz, os.path.join(td, "x"))
            # --app-only: só o app ([4/5]+[5/5]). As dependências já estão aí (o app
            # está rodando), e sem terminal um pedido de sudo travaria o upgrade.
            r = run(["bash", os.path.join(src, "install.sh"), "-y", "--app-only"],
                    env={**env, "PREFIX": root}, capture_output=True, text=True,
                    stdin=subprocess.DEVNULL, timeout=900)
            if r.returncode != 0:
                tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
                raise UpdateError(t("install.sh failed (exit {code}):", code=r.returncode) + "\n" + tail)
        # Relança pelo lançador que o install.sh acabou de gerar: ele escolhe o
        # Python certo (venv ou sistema) e põe os motores empacotados no PATH.
        launcher = os.path.join(os.path.expanduser("~"), ".local", "bin", "sombrero-file-search")
        if os.access(launcher, os.X_OK):
            return {"restart": [launcher], "opened": None}
        return {"restart": [sys.executable, os.path.join(root, "lfs", "app.py")],
                "opened": None}

    # deb / windows: baixa para Downloads e entrega ao sistema
    dest = os.path.join(downloads_dir(), asset["name"])
    download(asset["url"], dest, asset["size"], asset["digest"], progress, cancelled)
    return {"restart": None, "opened": dest}
