#!/usr/bin/env python3
"""Linux File Search — motor de busca (nome + conteúdo).

Filosofia de compatibilidade (roda em QUALQUER distro):
  - Busca de CONTEÚDO: usa `ripgrep` (rg) se existir -> rapidíssimo, --json.
    Fallback: Python puro (re + leitura em blocos), mais lento mas universal.
  - Busca por NOME: usa `fd`/`fdfind` se existir. Fallback: os.walk + fnmatch/regex.
  - Nomes de binário mudam entre distros (fd vs fdfind) -> autodetecção.
  - Sem dependência dura de nada além da stdlib.

O motor NÃO depende de Qt. A GUI o consome via callbacks/geradores, num thread,
pra interface nunca travar (foi o defeito do menu do Cinnamon: busca síncrona).
"""
from __future__ import annotations
import os, re, fnmatch, shutil, subprocess, json, stat, time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional


# ---------------------------------------------------------------- detecção
# binários que o próprio app pode empacotar (ver F6) — procurados além do PATH
_APP_BIN = os.path.expanduser("~/.local/share/linux-file-search/bin")

def _which(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
        cand = os.path.join(_APP_BIN, n)   # fallback: binário empacotado
        if os.access(cand, os.X_OK):
            return cand
    return None

RG = _which("rg")                    # ripgrep
FD = _which("fd", "fdfind")          # fd (Debian/Mint = fdfind)
RGA = _which("rga", "ripgrep-all")   # ripgrep-all: busca DENTRO de PDF/docx/epub/zip…

def engine_info():
    return {
        "ripgrep": RG or "(ausente — fallback Python)",
        "fd": FD or "(ausente — fallback Python)",
        "rga": RGA or "(ausente — sem modo documentos)",
    }


# ---------------------------------------------------------------- parâmetros
@dataclass
class Query:
    paths: list[str]                       # onde procurar
    name_patterns: list[str] = field(default_factory=list)  # globs OU 1 regex
    name_is_regex: bool = False
    content: str = ""                      # texto/regex a conter (vazio = só nome)
    content_is_regex: bool = False
    documents: bool = False                # busca DENTRO de PDF/docx/epub/zip via rga (F4)
    case_sensitive: bool = False
    whole_word: bool = False
    recursive: bool = True
    max_depth: Optional[int] = None
    include_hidden: bool = False
    follow_symlinks: bool = False
    respect_gitignore: bool = False   # False = busca TUDO (estilo Agent Ransack)
    one_file_system: bool = False     # não cruzar mounts (útil c/ USB do acervo)
    min_size: Optional[int] = None         # bytes
    max_size: Optional[int] = None
    modified_after: Optional[float] = None # epoch
    modified_before: Optional[float] = None
    max_results: int = 100000


@dataclass
class Match:
    path: str
    size: int
    mtime: float
    is_dir: bool = False
    lines: list[tuple[int, str]] = field(default_factory=list)  # (lineno, texto)
    nmatch: int = 0


# ---------------------------------------------------------------- filtros comuns
def _name_matcher(q: Query):
    """Retorna função(basename)->bool conforme padrões de nome."""
    if not q.name_patterns:
        return lambda b: True
    if q.name_is_regex:
        flags = 0 if q.case_sensitive else re.IGNORECASE
        rx = re.compile(q.name_patterns[0], flags)
        return lambda b: rx.search(b) is not None
    # globs (lista). case-insensitive por padrão como o Agent Ransack
    pats = q.name_patterns
    if q.case_sensitive:
        return lambda b: any(fnmatch.fnmatchcase(b, p) for p in pats)
    lp = [p.lower() for p in pats]
    return lambda b: any(fnmatch.fnmatchcase(b.lower(), p) for p in lp)


def _passes_meta(q: Query, st: os.stat_result) -> bool:
    if q.min_size is not None and st.st_size < q.min_size:
        return False
    if q.max_size is not None and st.st_size > q.max_size:
        return False
    if q.modified_after is not None and st.st_mtime < q.modified_after:
        return False
    if q.modified_before is not None and st.st_mtime > q.modified_before:
        return False
    return True


# ---------------------------------------------------------------- busca por NOME
def _iter_names_python(q: Query):
    """Fallback universal: os.walk com profundidade/hidden/symlink/meta."""
    match_name = _name_matcher(q)
    for root in q.paths:
        root = os.path.abspath(os.path.expanduser(root))
        base_depth = root.rstrip("/").count("/")
        for dp, dns, fns in os.walk(root, followlinks=q.follow_symlinks):
            depth = dp.rstrip("/").count("/") - base_depth
            if not q.include_hidden:
                dns[:] = [d for d in dns if not d.startswith(".")]
            if not q.recursive:
                dns[:] = []
            elif q.max_depth is not None and depth >= q.max_depth:
                dns[:] = []
            for f in fns:
                if not q.include_hidden and f.startswith("."):
                    continue
                if not match_name(f):
                    continue
                fp = os.path.join(dp, f)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                if not _passes_meta(q, st):
                    continue
                yield Match(fp, st.st_size, st.st_mtime)


def _iter_names_fd(q: Query, cancel):
    """fd/fdfind quando disponível (rápido). Multi-glob -> um fd por padrão."""
    seen = set()
    pats = q.name_patterns or ["."]
    for pat in pats:
        cmd = [FD, "--absolute-path", "--type", "f"]
        if not q.respect_gitignore:
            cmd.append("--no-ignore")
        if q.include_hidden:
            cmd.append("--hidden")
        if q.follow_symlinks:
            cmd.append("--follow")
        if q.one_file_system:
            cmd.append("--one-file-system")
        if not q.recursive:
            cmd += ["--max-depth", "1"]
        elif q.max_depth is not None:
            cmd += ["--max-depth", str(q.max_depth)]
        if q.name_patterns:
            if q.name_is_regex:
                if not q.case_sensitive:
                    cmd.append("--ignore-case")
                cmd += [pat]
            else:
                cmd += ["--glob"]
                if not q.case_sensitive:
                    cmd.append("--ignore-case")
                cmd += [pat]
        else:
            cmd += ["."]
        cmd += q.paths
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, errors="replace")
        except OSError:
            yield from _iter_names_python(q); return
        for line in proc.stdout:
            if cancel():
                proc.terminate(); return
            fp = line.rstrip("\n")
            if not fp or fp in seen:
                continue
            seen.add(fp)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            if not _passes_meta(q, st):
                continue
            yield Match(fp, st.st_size, st.st_mtime)
        proc.wait()


# ---------------------------------------------------------------- busca por CONTEÚDO
def _iter_content_rg(q: Query, cancel):
    """ripgrep --json (ou rga p/ documentos): filtra por nome (glob) E casa conteúdo, streaming.

    Em modo documentos (q.documents + rga presente) o rga extrai texto de PDF/docx/epub/zip…
    e repassa ao rg no MESMO formato --json. Caminhos dentro de containers (ex zip) podem não
    ter stat no FS — nesse caso emitimos o Match sem metadados (size/mtime 0) p/ não perder o hit.
    """
    docs = bool(q.documents and RGA)
    binary = RGA if docs else RG
    cmd = [binary, "--json"]
    if not docs:                                   # --encoding é do rg; rga extrai já em UTF-8
        cmd += ["--encoding", "auto"]
    if not q.respect_gitignore:
        cmd.append("--no-ignore")
    if q.include_hidden:
        cmd.append("--hidden")
    if q.follow_symlinks:
        cmd.append("--follow")
    if q.one_file_system:
        cmd.append("--one-file-system")
    if not q.case_sensitive:
        cmd.append("--ignore-case")
    if not q.content_is_regex:
        cmd.append("--fixed-strings")
    if q.whole_word:
        cmd.append("--word-regexp")
    if not q.recursive:
        cmd += ["--max-depth", "1"]
    elif q.max_depth is not None:
        cmd += ["--max-depth", str(q.max_depth)]
    # filtro de nome via glob (rg aplica no arquivo)
    if q.name_patterns and not q.name_is_regex:
        for p in q.name_patterns:
            cmd += ["--glob", p]
    cmd += ["-e", q.content, "--"]
    cmd += q.paths

    name_rx = None
    if q.name_patterns and q.name_is_regex:
        name_rx = re.compile(q.name_patterns[0], 0 if q.case_sensitive else re.IGNORECASE)

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, errors="replace")
    except OSError:
        yield from _iter_content_python(q, cancel); return

    cur = None
    for line in proc.stdout:
        if cancel():
            proc.terminate(); break
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "begin":
            path = ev["data"]["path"].get("text")
            if path is None or (name_rx and not name_rx.search(os.path.basename(path))):
                cur = None
                continue
            try:
                st = os.stat(path)
            except OSError:
                # arquivo dentro de container (ex algo.zip/interno.pdf): sem stat no FS
                cur = Match(path, 0, 0) if docs else None
                continue
            if not _passes_meta(q, st):
                cur = None; continue
            cur = Match(path, st.st_size, st.st_mtime)
        elif t == "match" and cur is not None:
            ln = ev["data"].get("line_number")
            txt = ev["data"]["lines"].get("text", "")
            cur.nmatch += len(ev["data"].get("submatches", []))
            if len(cur.lines) < 200:
                cur.lines.append((ln or 0, txt.rstrip("\n")))
        elif t == "end" and cur is not None:
            yield cur
            cur = None
    try:
        proc.wait(timeout=1)
    except Exception:
        pass


def _iter_content_python(q: Query, cancel):
    """Fallback: varre nomes e faz grep em Python (blocos, ignora binário)."""
    if q.case_sensitive:
        rx = re.compile(q.content if q.content_is_regex else re.escape(q.content))
    else:
        rx = re.compile(q.content if q.content_is_regex else re.escape(q.content), re.IGNORECASE)
    if q.whole_word and not q.content_is_regex:
        rx = re.compile(r"\b" + re.escape(q.content) + r"\b",
                        0 if q.case_sensitive else re.IGNORECASE)
    for m in _iter_names_python(q):
        if cancel():
            return
        try:
            with open(m.path, "r", errors="ignore") as fh:
                hit = None
                for i, line in enumerate(fh, 1):
                    if "\x00" in line:      # provável binário
                        hit = None; break
                    if rx.search(line):
                        if hit is None:
                            hit = m
                        m.nmatch += 1
                        if len(m.lines) < 200:
                            m.lines.append((i, line.rstrip("\n")))
                if hit is not None:
                    yield m
        except (OSError, UnicodeError):
            continue


# ---------------------------------------------------------------- API pública
def search(q: Query, on_result: Callable[[Match], None],
           cancel: Callable[[], bool] = lambda: False,
           on_progress: Callable[[int], None] = lambda n: None):
    """Executa a busca chamando on_result(Match) em streaming.
    Retorna (total_encontrado, segundos)."""
    t0 = time.time()
    n = 0
    if q.content:
        if RG or (q.documents and RGA):
            it = _iter_content_rg(q, cancel)
        else:
            it = _iter_content_python(q, cancel)
    else:
        it = _iter_names_fd(q, cancel) if FD else _iter_names_python(q)
    for m in it:
        if cancel():
            break
        on_result(m)
        n += 1
        if n % 25 == 0:
            on_progress(n)
        if n >= q.max_results:
            break
    return n, time.time() - t0


if __name__ == "__main__":
    # teste rápido de linha de comando
    import sys
    q = Query(paths=[sys.argv[1] if len(sys.argv) > 1 else "."],
              name_patterns=["*.py"], content=sys.argv[2] if len(sys.argv) > 2 else "")
    print("engine:", engine_info())
    tot, dt = search(q, lambda m: print(f"{m.size:>10} {m.path}"
                                        + (f"  [{m.nmatch} matches]" if m.nmatch else "")))
    print(f"\n{tot} resultados em {dt:.2f}s")
