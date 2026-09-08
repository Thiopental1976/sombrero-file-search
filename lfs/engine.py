#!/usr/bin/env python3
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Sombrero File Search — motor de busca (nome + conteúdo).

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
import os, re, fnmatch, shutil, subprocess, json, stat, time, tempfile
from dataclasses import dataclass, field, replace
from typing import Callable, Optional


# ---------------------------------------------------------------- detecção
# binários que o próprio app pode empacotar (ver F6) — procurados além do PATH
_APP_BIN = os.path.expanduser("~/.local/share/sombrero-file-search/bin")

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


def user_mounts(lines=None):
    """Pontos de montagem 'de usuário' — discos externos/acervo: dispositivos
    reais (/dev/*) montados sob /media, /mnt, /run/media ou /var/mnt (ostree:
    Bazzite/Silverblue montam discos fixos ali, pois /mnt é da imagem ro). São os
    candidatos da busca MULTIDISCOS na GUI ("Discos ▾"). `lines` injetável p/ teste."""
    if lines is None:
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
    out = set()
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or not parts[0].startswith("/dev/"):
            continue
        mp = parts[1].replace("\\040", " ")     # espaço vem escapado no mounts
        if mp.startswith(("/media/", "/mnt/", "/run/media/", "/var/mnt/")):
            out.add(mp)
    return sorted(out)


# --------------------------------------------------- arvores de SNAPSHOT (F11)
# Descoberto medindo (08/09/2026): o 4TB-Portable levava ~1090 s numa busca que
# os outros discos fechavam em 1-17 s. Nao era o barramento USB (enlace em
# 5 Gbps; discos em USB 2.0 de 480 Mbps terminavam em segundos) — era CONTAGEM
# DE ARQUIVOS: o disco hospeda 5 snapshots diarios do Timeshift, cada um uma
# copia da raiz do sistema. 2.426.925 inodes contra 175.553 do DiscoQ.
# Varrer backup do sistema pra achar arquivo do usuario e ruido caro: devolve
# milhares de /usr/share/icons. Pulado por padrao, com como voltar atras.
# Os padroes sao GLOB DE COMPONENTE, nao substring de caminho (F11 bug4):
#  - "timeshift/snapshots*" cobre tambem snapshots-daily/, -boot/, -weekly/…,
#    que o Timeshift cria como fazenda de symlinks pra dentro de snapshots/.
#    Com --follow o fd entrava por ali e varria os cinco snapshots de novo.
#  - "@GMT-*": o diretorio do Samba nunca se chama "@GMT-" exato, tem a data.
#  - componente, e nao substring, pra "meus_timeshift_backups/" nao ser vitima.
EXCLUSOES_SNAPSHOT = (
    "timeshift/snapshots*",    # Timeshift (rsync): <destino>/timeshift/snapshots/<data>/
    "timeshift-btrfs",         # Timeshift em modo btrfs
    ".snapshots",              # snapper (openSUSE/btrfs)
    ".zfs/snapshot",           # ZFS
    "@GMT-*",                  # Samba/shadow copies (@GMT-2026.01.01-00.00.00)
    # ostree (Silverblue/Kinoite/Bazzite): /sysroot/ostree/repo/objects sao
    # centenas de milhares de blobs com nome de sha256, e cada deploy sob
    # ostree/deploy/<os>/deploy/<hash>/ e uma copia da raiz. Buscar em "/" desce
    # em /sysroot e vira o mesmo problema do Timeshift. O sistema VIVO nao se
    # esconde: ele e alcancado por /usr, /etc..., que nao passam por estes
    # componentes. (Fable 5, revisao de 08/09/2026.)
    "ostree/repo",
    "ostree/deploy",
)

# NAO entram aqui, e a distincao e a regra que impede a lista de virar lixeira:
# so e excluido por padrao o que e COPIA DO SISTEMA. "Ruido" (node_modules,
# .git, /nix/store) nunca entra — no NixOS o /nix/store E o sistema vivo, e
# quem busca la esta procurando de proposito.


def eh_snapshot(path: str) -> bool:
    """True se o caminho esta DENTRO de uma arvore de snapshot de sistema.
    Casa por COMPONENTE do caminho (um ou mais, em sequencia), com glob."""
    comps = path.strip("/").split("/")
    for m in EXCLUSOES_SNAPSHOT:
        mp = m.split("/")
        n = len(mp)
        for i in range(len(comps) - n + 1):
            if all(fnmatch.fnmatchcase(comps[i + j], mp[j]) for j in range(n)):
                return True
    return False


def tem_snapshot(root: str) -> bool:
    """Este root hospeda arvore de snapshot? Um punhado de glob, sem caminhada —
    serve pro motor AVISAR que escondeu algo (esconder em silencio e que nao).

    Deriva de EXCLUSOES_SNAPSHOT em vez de repetir a lista: a copia manual ja
    tinha divergido (faltavam '@GMT-*' e o '*' de 'snapshots*'), e uma lista que
    diverge da outra faz o aviso mentir. Olha tambem as MONTAGENS sob o root:
    buscar em "/" com o Timeshift em /media/x podava sem avisar."""
    import glob as _glob
    alvos = [root]
    try:
        base = os.path.abspath(root).rstrip("/") + "/"
        alvos += [m for m in user_mounts() if m.startswith(base)]
    except Exception:
        pass
    for a in alvos:
        for m in EXCLUSOES_SNAPSHOT:
            try:
                if _glob.glob(os.path.join(a, m)):
                    return True
            except OSError:
                pass
    return False


def _globs_snapshot():
    """Padroes p/ o --exclude do fd e o --glob '!' do rg. Precisa ser exclusao
    NO MOTOR, nao filtro na saida: filtrar depois nao economiza a caminhada,
    e a caminhada e justamente o custo (2,4 milhoes de entradas)."""
    fora = []
    for m in EXCLUSOES_SNAPSHOT:
        fora.append(f"**/{m}/**")
        fora.append(f"**/{m}")
    return fora


# ---------------------------------------------------------------- utilidades
def _reap(proc, errf=None, stats=None):
    """Encerra o subprocesso SEM deixar órfão (B1) e conta 'inacessíveis' do
    stderr capturado (B8). Idempotente e à prova de exceção."""
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(1)
            except Exception:
                proc.kill()
                try: proc.wait(1)
                except Exception: pass
    except Exception:
        pass
    if errf is not None:
        if stats is not None:
            try:
                errf.seek(0)
                linhas = errf.readlines()
                stats["denied"] = stats.get("denied", 0) + sum(
                    1 for L in linhas if "ermission denied" in L)
                # F11b (Fable 5): o rg sai com codigo 2 quando NAO ENTENDE uma
                # flag — p.ex. --glob-case-insensitive, que so existe do rg 12
                # pra cima e falta no Ubuntu 20.04. Antes disso o erro morria
                # aqui dentro e a busca devolvia ZERO RESULTADOS EM SILENCIO,
                # que e o pior modo de falha possivel numa ferramenta cujo lema
                # e "honestidade > completude": o usuario conclui que o arquivo
                # nao existe. Codigo 1 e legitimo (rg: "nada casou").
                rc = proc.returncode if proc is not None else None
                if rc is not None and rc not in (0, 1, -15, 143):
                    motivo = next((L.strip() for L in linhas
                                   if L.strip() and "ermission denied" not in L), "")
                    stats.setdefault("engine_errors", []).append(
                        {"rc": rc, "erro": (motivo or f"o motor saiu com codigo {rc}")[:200]})
            except Exception:
                pass
        try: errf.close()
        except Exception: pass


def parse_size(s):
    """'10M', '1.5G', '512K', '2TB'… -> bytes. None se vazio/ inválido.
    Canônico (antes duplicado em app.py e cli.py)."""
    if not s:
        return None
    s = str(s).strip().upper().replace(" ", "")
    if not s:
        return None
    mult = 1
    for suf, m in (("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10),
                   ("T", 1 << 40), ("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10), ("B", 1)):
        if s.endswith(suf):
            s = s[:-len(suf)]; mult = m; break
    try:
        n = int(float(s) * mult)
    except ValueError:
        return None
    return n if n >= 0 else None          # tamanho negativo não faz sentido -> ignora filtro


_GLOB_META = frozenset("*?[")

def as_name_glob(term: str) -> str:
    """Entrada crua do usuário no campo de NOME -> glob de basename, estilo
    Agent Ransack/Windows: texto puro significa 'contém' — "rotina" vira
    "*rotina*" e acha "exames de rotina.txt", qualquer extensão. Quem digita
    metacaracteres (* ? [) está pedindo glob literal e mantém o controle."""
    t = term.strip()
    if not t or _GLOB_META & set(t):
        return t
    return f"*{t}*"


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
    skip_snapshots: bool = True       # pula timeshift/snapper/zfs (ver EXCLUSOES_SNAPSHOT)
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
    # (lineno, texto lógico). CONTRATO (Fable, decisão CRLF 23/07): cada `texto`
    # é o texto LÓGICO da linha, SEM artefatos de terminador (`\n`, `\r\n`). NÃO
    # é fidelidade byte-a-byte do arquivo — é o que o usuário lê, copia e exporta
    # (export CSV/JSON consome isto; um `\r` perdido numa célula de CSV suja o
    # consumidor downstream). Os DOIS motores (rg e fallback Python) normalizam
    # via `_logical_line`; a suíte de paridade trava o invariante com sentinela.
    lines: list[tuple[int, str]] = field(default_factory=list)
    nmatch: int = 0


def _logical_line(text: str) -> str:
    r"""Texto lógico da linha p/ `Match.lines`: sem terminador de fim-de-linha.

    Tira o `\n` final e UM `\r` final (o par CRLF). Strip ÚNICO, não guloso: um
    CR fora do padrão CRLF (lone CR pré-OSX, ou `\r\r\n`) é divergência
    ESTRUTURAL de segmentação/numeração entre os motores — não de texto — e
    nenhum rstrip conserta numeração (ver DIVERGENCIAS_CONHECIDAS na suíte de
    paridade). Idempotente para linha já sem terminador.
    """
    text = text.rstrip("\n")
    return text[:-1] if text.endswith("\r") else text


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
def _walk_onerror(stats):
    """N2: os.walk engolia erros silenciosamente; agora conta os inacessíveis."""
    def cb(err):
        if stats is not None and isinstance(err, PermissionError):
            stats["denied"] = stats.get("denied", 0) + 1
    return cb


def _iter_names_python(q: Query, stats=None, cancel=None):
    """Fallback universal: os.walk com profundidade/hidden/symlink/meta/one-fs.
    N2: `stats` recebe 'denied' de diretórios sem permissão (onerror do os.walk)."""
    match_name = _name_matcher(q)
    # profundidade efetiva no MESMO sentido que o fd (--max-depth N conta filhos
    # diretos como 1). Uma entrada dentro de um dir de `depth` d tem fd-depth d+1,
    # então incluímos só quando depth < eff_max (senão o fallback casava um nível
    # a mais que o fd/rg — divergência de backend).
    if not q.recursive:
        eff_max = 1
    else:
        eff_max = q.max_depth
    seen_dirs = set() if q.follow_symlinks else None   # E4: corta laço de symlink
    for root in q.paths:
        root = os.path.abspath(os.path.expanduser(root))
        base_depth = root.rstrip("/").count("/")
        root_dev = None
        if q.one_file_system:                       # B9: não cruzar mounts no fallback
            try: root_dev = os.stat(root).st_dev
            except OSError: root_dev = None
        for dp, dns, fns in os.walk(root, followlinks=q.follow_symlinks,
                                    onerror=_walk_onerror(stats)):
            if cancel and cancel():                 # E10: honra cancelamento no fallback
                return
            depth = dp.rstrip("/").count("/") - base_depth
            if seen_dirs is not None:               # E4: não revisita dir já visto (ciclo)
                try:
                    st_dp = os.stat(dp)
                    key = (st_dp.st_dev, st_dp.st_ino)
                    if key in seen_dirs:
                        dns[:] = []
                        continue
                    seen_dirs.add(key)
                except OSError:
                    pass
            if not q.include_hidden:
                dns[:] = [d for d in dns if not d.startswith(".")]
            if q.skip_snapshots:                    # F11: poda a arvore de snapshot
                dns[:] = [d for d in dns           # ANTES de descer nela — filtrar
                          if not eh_snapshot(os.path.join(dp, d) + "/")]  # depois nao
                if eh_snapshot(dp + "/"):          # economiza a caminhada, que e o custo
                    dns[:] = []
                    continue
            if root_dev is not None:
                keep = []
                for d in dns:
                    try:
                        if os.stat(os.path.join(dp, d)).st_dev == root_dev:
                            keep.append(d)
                    except OSError:
                        pass
                dns[:] = keep
            emit_here = eff_max is None or depth < eff_max   # E3: gate por profundidade
            # pastas também casam por nome (busca só-por-nome; dir não tem conteúdo).
            # Feito com a lista JÁ podada (ocultos/one-fs), antes do corte de recursão.
            if emit_here:
                for d in dns:
                    if not match_name(d):
                        continue
                    dpp = os.path.join(dp, d)
                    try:
                        st = os.stat(dpp)
                    except OSError:
                        try:
                            st = os.lstat(dpp)      # E5: symlink de dir quebrado
                        except OSError:
                            continue
                    if not _passes_meta(q, st):
                        continue
                    yield Match(dpp, st.st_size, st.st_mtime, is_dir=True)
            if not q.recursive:
                dns[:] = []
            elif q.max_depth is not None and depth >= q.max_depth:
                dns[:] = []
            if emit_here:
                for f in fns:
                    if not q.include_hidden and f.startswith("."):
                        continue
                    if not match_name(f):
                        continue
                    fp = os.path.join(dp, f)
                    try:
                        st = os.stat(fp)
                    except OSError:
                        try:
                            st = os.lstat(fp)       # E5: symlink quebrado casa por nome
                        except OSError:
                            continue
                    if not _passes_meta(q, st):
                        continue
                    yield Match(fp, st.st_size, st.st_mtime)


_MERGE_GLOBS_MIN = 4                      # opt#3: >3 globs -> funde numa regex só

def _glob_to_regex(glob: str) -> str:
    """Converte um glob de basename numa regex ANCORADA (^...$), equivalente ao
    fnmatch. `*`->`.*`, `?`->`.`, `[...]` preservado (com `!`->`^`), resto literal."""
    out = ["^"]
    i, n = 0, len(glob)
    while i < n:
        c = glob[i]
        if c == "*":
            out.append(".*")
        elif c == "?":
            out.append(".")
        elif c == "[":
            j = i + 1
            if j < n and glob[j] in "!^":
                j += 1
            if j < n and glob[j] == "]":         # ']' logo no início é literal
                j += 1
            while j < n and glob[j] != "]":
                j += 1
            if j >= n:                           # '[' sem fechamento -> literal
                out.append(r"\[")
            else:
                inner = glob[i + 1:j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                out.append("[" + inner + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    out.append("$")
    return "".join(out)


def _merge_globs(pats) -> Optional[str]:
    """Opt#3: funde vários globs de basename numa única regex alternada, p/ rodar
    UM só fd em vez de um por padrão (menos varreduras = menos I/O, bom p/ SMR).
    Só funde globs simples (sem '/'); valida a regex antes. Devolve None p/ recusar."""
    if any("/" in p for p in pats):              # glob de caminho: fd casa a path toda
        return None
    merged = "(?:" + "|".join(_glob_to_regex(p) for p in pats) + ")"
    try:
        re.compile(merged)                       # sanidade (se falhar, cai no multi-fd)
    except re.error:
        return None
    return merged


def _iter_names_fd(q: Query, cancel, stats=None, jobs=None, procs=None):
    """fd/fdfind quando disponível (rápido). Multi-glob: >3 padrões viram UMA regex
    alternada (opt#3, 1 só fd); até 3, um fd por padrão."""
    pats = q.name_patterns or ["."]
    use_glob = bool(q.name_patterns) and not q.name_is_regex
    # opt#3: muitos globs -> funde numa regex única (uma varredura só)
    if use_glob and len(pats) >= _MERGE_GLOBS_MIN:
        merged = _merge_globs(pats)
        if merged is not None:
            pats = [merged]
            use_glob = False                      # agora é regex, não glob
    seen = set() if len(pats) > 1 else None   # dedup só faz sentido com múltiplos padrões
    for pat in pats:
        # arquivos E pastas (e symlinks): busca só-por-nome acha "Argentina/" como
        # pasta e "argentina.txt" como arquivo — dir não tem conteúdo p/ filtrar.
        cmd = [FD, "--absolute-path", "--type", "f", "--type", "d", "--type", "l"]
        if jobs:
            cmd += ["--threads", str(jobs)]   # F11: particionado por disco -> pool
                                              # enxuto por processo (ver _grupos_por_disco)
        if not q.respect_gitignore:
            cmd.append("--no-ignore")
        if q.include_hidden:
            cmd.append("--hidden")
        if q.follow_symlinks:
            cmd.append("--follow")
        if q.one_file_system:
            cmd.append("--one-file-system")
        if q.skip_snapshots:
            for g in _globs_snapshot():
                cmd += ["--exclude", g]
        if not q.recursive:
            cmd += ["--max-depth", "1"]
        elif q.max_depth is not None:
            cmd += ["--max-depth", str(q.max_depth)]
        if use_glob:
            cmd += ["--glob"]
        if q.name_patterns and not q.case_sensitive:
            cmd.append("--ignore-case")
        elif q.name_patterns and q.case_sensitive:
            cmd.append("--case-sensitive")        # N1: fd usa smart-case; força sensível
        pat_val = pat if q.name_patterns else "."
        cmd.append("--print0")                    # E1: saída NUL-delimitada — nome com
                                                  # '\n' não vira 2 registros (perda/fantasma)
        cmd += ["--", pat_val] + q.paths          # B10: '--' encerra as opções
        errf = tempfile.TemporaryFile(mode="w+")
        try:
            # binário (sem text=): lê bytes e decodifica com surrogateescape p/
            # sobreviver a nomes não-UTF-8 (E2) — o str resultante volta pro os.stat.
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf)
            if procs is not None:
                procs.append(proc)     # F11 bug1: quem cancela precisa alcancar
                                       # o processo; read1() so ve o `parar` se
                                       # vier chunk, e disco silencioso nao vem
        except OSError:
            errf.close()
            yield from _iter_names_python(q, stats, cancel); return
        try:
            buf = b""
            read1 = getattr(proc.stdout, "read1", proc.stdout.read)
            while True:
                if cancel():
                    return
                chunk = read1(65536)
                if chunk:
                    buf += chunk
                    parts = buf.split(b"\0")
                    buf = parts.pop()             # trecho incompleto fica p/ próxima
                else:
                    parts = [buf] if buf else []  # EOF: drena o resto (normalmente vazio)
                    buf = b""
                for raw in parts:
                    if not raw:
                        continue
                    fp = os.fsdecode(raw)         # E2: surrogateescape p/ nomes crus
                    if len(fp) > 1:
                        fp = fp.rstrip("/")   # fd emite "dir/" com barra final — ela
                                              # quebra os.path.basename() na GUI (nome
                                              # vazio). Guarda len>1 preserva a raiz "/".
                    if not fp or (seen is not None and fp in seen):
                        continue
                    if seen is not None:
                        seen.add(fp)
                    try:
                        st = os.stat(fp)
                        is_dir = stat.S_ISDIR(st.st_mode)
                    except OSError:
                        try:
                            st = os.lstat(fp)    # E5: symlink quebrado — mostra o link
                        except OSError:
                            continue
                        is_dir = False
                    if not _passes_meta(q, st):
                        continue
                    yield Match(fp, st.st_size, st.st_mtime, is_dir=is_dir)
                if not chunk:
                    break
        finally:
            _reap(proc, errf, stats)              # B1/B8: mata processo + conta inacessíveis


# ---------------------------------------------------------------- busca por CONTEÚDO
def rg_flags_comuns(q: Query, matching: bool = True):
    """Flags do rg compartilhadas pela busca de conteúdo e pelo motor BOOLEANO.

    Fonte única de propósito (F11b): o boolean.py montava o seu próprio rg e por
    isso ficou sem `skip_snapshots` — busca simples e booleana pelo mesmo termo
    devolviam conjuntos diferentes, e dentro do booleano o rg divergia do
    fallback Python. Toda regra que vale pro rg entra AQUI.

    `matching=False` (universo do NOT, no booleano) omite as flags de CASAMENTO
    de conteúdo: o universo lista todo arquivo de texto com padrão vazio, e
    --word-regexp quebraria isso.

    ORDEM IMPORTA: no rg o ÚLTIMO glob que casa vence, então os negativos de
    snapshot têm de vir DEPOIS dos globs de nome — senão um padrão como '*shot*'
    reabre a árvore que a gente acabou de excluir.
    """
    cmd = []
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
    if matching and q.whole_word:
        cmd.append("--word-regexp")
    if not q.recursive:
        cmd += ["--max-depth", "1"]
    elif q.max_depth is not None:
        cmd += ["--max-depth", str(q.max_depth)]
    if q.name_patterns and not q.name_is_regex:
        if not q.case_sensitive:
            cmd.append("--glob-case-insensitive")   # B2: glob insensível como o fd
        for p in q.name_patterns:
            cmd += ["--glob", p]
    if q.skip_snapshots:                            # depois dos globs de nome
        for g in _globs_snapshot():
            cmd += ["--glob", "!" + g]
    return cmd


def _iter_content_rg(q: Query, cancel, stats=None, jobs=None, procs=None):
    """ripgrep --json (ou rga p/ documentos): filtra por nome (glob) E casa conteúdo, streaming.

    Em modo documentos (q.documents + rga presente) o rga extrai texto de PDF/docx/epub/zip…
    e repassa ao rg no MESMO formato --json. Caminhos dentro de containers (ex zip) podem não
    ter stat no FS — nesse caso emitimos o Match sem metadados (size/mtime 0) p/ não perder o hit.
    """
    docs = bool(q.documents and RGA)
    binary = RGA if docs else RG
    cmd = [binary, "--json"]
    if jobs and not docs:
        cmd += ["--threads", str(jobs)]        # F11: idem ao fd, ver _grupos_por_disco
    if not docs:                               # --encoding é do rg; rga já extrai UTF-8
        cmd += ["--encoding", "auto"]
    if not q.content_is_regex:
        cmd.append("--fixed-strings")
    cmd += rg_flags_comuns(q)                  # fonte única — ver rg_flags_comuns
    cmd += ["-e", q.content, "--"]
    cmd += q.paths

    name_rx = None
    if q.name_patterns and q.name_is_regex:
        name_rx = re.compile(q.name_patterns[0], 0 if q.case_sensitive else re.IGNORECASE)

    errf = tempfile.TemporaryFile(mode="w+")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf,
                                text=True, errors="replace")
        if procs is not None:
            procs.append(proc)                 # F11 bug1: idem ao fd
    except OSError:
        errf.close()
        yield from _iter_content_python(q, cancel); return

    cur = None
    try:
        for line in proc.stdout:
            if cancel():
                break
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
                    cur.lines.append((ln or 0, _logical_line(txt)))
            elif t == "end" and cur is not None:
                yield cur
                cur = None
    finally:
        _reap(proc, errf, stats)                    # B1/B8


def _content_regex(content: str, q: Query) -> "re.Pattern":
    """Regex de conteúdo com as MESMAS flags que o fallback usa (case/regex/word).
    Fatorado p/ o fallback de linhas do booleano casar idêntico à busca do termo."""
    flags = 0 if q.case_sensitive else re.IGNORECASE
    if q.whole_word and not q.content_is_regex:
        return re.compile(r"\b" + re.escape(content) + r"\b", flags)
    return re.compile(content if q.content_is_regex else re.escape(content), flags)


def _iter_content_python(q: Query, cancel, stats=None):
    """Fallback: varre nomes e faz grep em Python (blocos, ignora binário).
    N2: conta 'denied' de diretórios (os.walk) e de arquivos sem permissão."""
    rx = _content_regex(q.content, q)
    for m in _iter_names_python(q, stats, cancel):
        if cancel():
            return
        try:
            # T1: FIFO/socket/device fazem open() bloquear pra sempre (pipe sem
            # escritor). O rg pula não-regulares sozinho; no fallback a guarda é nossa.
            if not stat.S_ISREG(os.stat(m.path, follow_symlinks=q.follow_symlinks).st_mode):
                continue
        except OSError:
            continue
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
                            m.lines.append((i, _logical_line(line)))
                if hit is not None:
                    yield m
        except PermissionError:
            if stats is not None:                     # N2: arquivo sem permissão de leitura
                stats["denied"] = stats.get("denied", 0) + 1
            continue
        except (OSError, UnicodeError):
            continue


# ---------------------------------------------------------------- API pública
def _live_roots(paths, stats, probe_timeout: float = 3.0,
                on_event=lambda ev, info: None, classes=None):
    """F9a §2.2 — GATE DE DESCIDA. Antes de o walker entrar num root, se ele for
    uma montagem de rede (NFS/CIFS/SSHFS/…), sonda `mount_status` numa PROCESSO
    descartável (F1). Montagem que não responde (D-state, `stat` travado) ou que
    responde QUEBRADA (ENOTCONN/ESTALE… — F2) é PULADA com aviso visível em
    `stats['skipped_mounts']`, com `reason` = 'no_response' | 'broken_mount' —
    nunca congela o programa, nunca silêncio.

    Roots locais (disco/SSD/SMR) passam direto, sem custo de sonda. Retorna a
    lista de roots vivos, na ordem original. Se `disks` não puder ser importado
    (uso do engine solto, sem o pacote), degrada para os paths originais.

    F11b: `classes` (dict opcional) recebe root -> klass. A classificação já era
    calculada aqui e jogada fora; agora ela escolhe o tamanho do pool de cada
    processo particionado (ver _jobs_para_classe)."""
    try:
        from . import disks
    except Exception:
        try:
            import disks  # type: ignore
        except Exception:
            return list(paths)
    live = []
    for root in paths:
        try:
            prof = disks.search_profile(root)
        except Exception:
            if classes is not None:
                classes[root] = "unknown"
            live.append(root)          # não sei classificar → não bloqueio
            on_event("root_scanning",   # F10a §2: badge de classe p/ o painel
                     {"path": root, "klass": "unknown", "mountpoint": None})
            continue
        if prof.is_network:
            mp = prof.mountpoint or root
            status = disks.mount_status(mp, timeout=probe_timeout)
            if status != "alive":
                if stats is not None:
                    stats.setdefault("skipped_mounts", []).append(
                        {"path": root, "mount": mp, "fstype": prof.fstype,
                         "reason": status})   # 'no_response' | 'broken_mount'
                # linha VERMELHA ao vivo (não popup no fim) — F10a §2
                on_event("root_skipped",
                         {"path": root, "mount": mp, "fstype": prof.fstype,
                          "klass": prof.klass, "reason": status})
                continue
        live.append(root)
        if classes is not None:
            classes[root] = prof.klass
        on_event("root_scanning",
                 {"path": root, "klass": prof.klass, "mountpoint": prof.mountpoint})
    return live


# ------------------------------------------- F11: paralelismo de I/O por disco
# Um `fd`/`rg` só, recebendo os 10 roots, tem pool de threads GLOBAL e CEGO à
# montagem: os resultados saem por um iterador serial e os discos rápidos ficam
# reféns do mais lento. Medido no acervo (padrão "Kevlyn", 10 montagens): nove
# discos entregavam tudo em menos de 1,4 s enquanto o 4TB-Portable (USB numa
# placa de expansão PCIe) levava 168 s sozinho — e a GUI só via o primeiro
# resultado quando o iterador serial chegasse nele.
# Aqui a busca é PARTICIONADA por dispositivo (st_dev): um processo por disco,
# rodando em paralelo, e um consumidor único que repassa cada achado assim que
# chega. Regra da casa: UMA thread por ponto de montagem, nunca mais que isso
# (cabeça de HDD não se divide; em SMR é pior) — por isso cada processo recebe
# um pool enxuto (_JOBS_POR_DISCO) em vez do padrão do fd, que é nº de CPUs.
_FILA_MAX = 4096             # contrapressão: o produtor espera se a GUI não drena

# F11b — quantas threads DENTRO de cada fd/rg, por classe de disco. Medido em
# 08/09/2026 (drop_caches antes de cada passada, máquina quiescida): no NVMe,
# `--threads 1` custa 12,5x contra o padrão do fd; num SMR de 1,15 milhão de
# inodes, `--threads 1` GANHA 21%. Os números estão no commit — aqui fica só a
# regra. Assimetria que manda no desenho: errar para menos (estrangular um SSD)
# é ordens de grandeza mais caro que errar para mais (soltar um disco mecânico).
# Por isso "não sei" NÃO estrangula: quem cai em 'unknown' é container, ZFS e
# não-Linux, hoje majoritariamente SSD. A regra da casa segue protegida porque
# `search_profile` já classifica rotacional-por-padrão sob /mnt|/media quando
# não consegue medir.
_JOBS_POR_CLASSE = {
    "ssd": None,             # None = padrão do fd (nº de CPUs): SSD quer fila funda
    "rotational": 1,         # um cabeçote, uma thread — a regra da casa, confirmada
    "unknown": None,         # não sei: solta. O conservadorismo mora no search_profile
}


def _pula_snapshot(paths, base):
    """Decide `skip_snapshots` PARA ESTE CONJUNTO de roots.

    F11 bug3: quem navega ate .../timeshift/snapshots/<data>/home/rodrigo esta
    procurando justamente ali, e os tres backends divergiam (o fd achava; o rg e
    o fallback devolviam vazio EM SILENCIO). A 1a correcao desligava a exclusao
    na CONSULTA INTEIRA — entao buscar em ["/.snapshots/5/snapshot/home", "/"]
    reabria os snapshots tambem no "/". Agora e por grupo: so o disco que contem
    o root-dentro-do-snapshot enxerga snapshots.
    """
    if not base:
        return False
    for r in paths:
        if eh_snapshot(os.path.abspath(os.path.expanduser(r)) + "/"):
            return False
    return True


def _jobs_de_rede():
    """Teto por montagem de rede — o `disks` é o dono desse número, não o motor."""
    try:
        from . import disks
    except Exception:
        try:
            import disks  # type: ignore
        except Exception:
            return 4
    return getattr(disks, "NET_WORKERS_PER_MOUNT", 4)


def _jobs_para_classe(classes_do_grupo):
    """Pool de um processo particionado. Grupo com classes mistas (roots do mesmo
    disco não deveriam divergir, mas acontece com bind mount) leva a política
    MAIS conservadora — errar para menos só custa tempo; errar para mais faz o
    cabeçote de um disco mecânico passear."""
    rede = _jobs_de_rede()
    valores = [rede if k in ("network", "gvfs", "autofs") else _JOBS_POR_CLASSE.get(k)
               for k in classes_do_grupo] or [None]
    concretos = [v for v in valores if v is not None]
    return min(concretos) if concretos else None


def _chave_de_disco(root):
    """Identidade do DISCO FÍSICO do root. st_dev sozinho não serve (Fable 5):
    btrfs com subvolumes @/@home — o padrão de Ubuntu e Fedora — e LVM com duas
    partições no mesmo prato dão st_dev diferentes para o MESMO cabeçote, e aí
    abriríamos dois fd concorrendo no mesmo disco, que é exatamente a regra da
    casa que este módulo existe para respeitar. Quando `disks` sabe dizer o
    disco-pai, ele manda; st_dev é o reserva."""
    try:
        from . import disks
    except Exception:
        try:
            import disks  # type: ignore
        except Exception:
            disks = None
    if disks is not None:
        try:
            dev, _mp, fstype = disks._mount_entry(os.path.abspath(root))
            # ZFS: o "dev" é pool/dataset, não um nó de bloco. Sem isto cada
            # dataset viraria um grupo e abriríamos N processos no MESMO pool.
            if (fstype or "").lower() == "zfs" and dev:
                return ("zpool", dev.split("/")[0])
            pai = disks._sys_disk(dev) if dev else None
            if pai:
                return ("disco", pai)
        except Exception:
            pass
    return ("dev", os.stat(root).st_dev)


def _grupos_por_disco(paths):
    """Agrupa roots por disco físico. Roots do mesmo disco vão juntos no mesmo
    processo — o ganho é entre discos, não dentro de um."""
    grupos, ordem = {}, []
    for r in paths:
        try:
            chave = _chave_de_disco(r)
        except OSError:
            chave = ("?", r)                  # não deu stat: fica sozinho
        if chave not in grupos:
            grupos[chave] = []
            ordem.append(chave)
        grupos[chave].append(r)
    return [grupos[k] for k in ordem]


def _funde_stats(dst, src):
    """Soma os contadores de um worker no dict compartilhado (só o consumidor
    chama isto — os workers escrevem em dicts próprios, sem lock)."""
    if dst is None or not src:
        return
    for k, v in src.items():
        if isinstance(v, list):
            dst.setdefault(k, []).extend(v)
        elif isinstance(v, (int, float)):
            dst[k] = dst.get(k, 0) + v
        else:
            dst.setdefault(k, v)


def _iter_particionado(q: Query, cancel, stats, grupos, fabrica, ao_fim=None):
    """Roda `fabrica(q_do_grupo, cancel, stats_do_grupo)` em uma thread por grupo
    e devolve os Matches EM STREAMING, na ordem em que chegarem.

    `ao_fim(paths)` é chamado quando o grupo termina — e só é chamado depois que
    todos os achados dele já foram entregues, porque cada worker enfileira seus
    Matches ANTES da própria sentinela e a fila preserva essa ordem por produtor.
    """
    import threading, queue
    fila = queue.Queue(maxsize=_FILA_MAX)
    parar = threading.Event()
    FIM = object()

    def _cancel():
        return parar.is_set() or cancel()

    procs = []          # list.append e atomico sob o GIL; so o finally le

    def trabalha(paths):
        meu = {}
        try:
            for m in fabrica(replace(q, paths=paths), _cancel, meu, procs):
                if _cancel():
                    break
                fila.put(m)
        except Exception as e:                # um disco quebrar não derruba a busca
            meu.setdefault("erros", []).append({"paths": paths, "erro": repr(e)})
        finally:
            fila.put((FIM, paths, meu))

    threads = [threading.Thread(target=trabalha, args=(g,), daemon=True,
                                name=f"sfs-disco-{i}") for i, g in enumerate(grupos)]
    for t in threads:
        t.start()
    vivos = len(threads)
    try:
        while vivos:
            try:
                item = fila.get(timeout=0.2)
            except queue.Empty:
                if cancel():
                    return
                continue
            if isinstance(item, tuple) and item and item[0] is FIM:
                _, paths, meu = item
                _funde_stats(stats, meu)
                if ao_fim is not None:
                    ao_fim(paths, meu)
                vivos -= 1
                continue
            yield item
    finally:
        # Saída antecipada (cancelamento ou max_results). O `parar` sozinho NÃO
        # basta: o worker está bloqueado em read1() de um fd que não tem mais
        # nada a dizer naquele disco, e só olharia o evento se chegasse chunk —
        # num disco silencioso ele esperaria a caminhada inteira terminar (no
        # 4TB-Portable, ~1000 s de Cancel que não solta e de disco martelado à
        # toa). Matar o processo faz o read1() devolver EOF e o worker sair;
        # _reap é idempotente, então o finally do próprio worker não se irrita.
        parar.set()
        mortos = set()

        def _mata():
            # dentro do laço, não uma vez só: um worker pode ainda estar ABRINDO
            # o processo quando o cancelamento chega, e um único tiro no início
            # erraria justamente quem ia varrer o disco lento.
            for pr in list(procs):
                if id(pr) in mortos:
                    continue
                mortos.add(id(pr))
                try:
                    pr.terminate()
                except Exception:
                    pass

        limite = time.time() + 5.0     # teto: são daemon threads, jamais seguram
        while time.time() < limite:    # a busca refém de um I/O que não volta
            _mata()
            if not any(t.is_alive() for t in threads):
                break
            try:
                item = fila.get(timeout=0.05)
            except queue.Empty:
                continue
            # não perde o 'denied' de quem foi interrompido no meio
            if isinstance(item, tuple) and item and item[0] is FIM:
                _funde_stats(stats, item[2])
        _mata()
        for t in threads:
            t.join(timeout=0.2)


def search(q: Query, on_result: Callable[[Match], None],
           cancel: Callable[[], bool] = lambda: False,
           on_progress: Callable[[int], None] = lambda n: None,
           stats: Optional[dict] = None,
           on_event: Callable[[str, dict], None] = lambda ev, info: None):
    """Executa a busca chamando on_result(Match) em streaming.
    Retorna (total_encontrado, segundos). Se `stats` (dict) for passado, recebe
    contadores como stats['denied'] (arquivos inacessíveis vistos no stderr) e
    stats['skipped_mounts'] (montagens de rede mortas puladas — F9a §2.2).

    `on_event(ev, info)` (F10a §2 — painel de narrativa, no ALTO da GUI) recebe,
    AO VIVO: 'root_scanning' {path, klass, mountpoint} quando um root passa o
    gate; 'root_skipped' {path, mount, fstype, klass, reason} quando uma montagem
    de rede morta é pulada (a GUI pinta linha vermelha na hora, sem popup); e
    'root_done' {path, found} por root ao fim, com os achados atribuídos a ele.
    Padrão no-op: chamadores e testes antigos seguem intactos."""
    t0 = time.time()
    n = 0
    classes = {}
    roots = _live_roots(q.paths, stats, on_event=on_event, classes=classes)
    if not roots:
        return 0, time.time() - t0
    if roots != list(q.paths):
        q = replace(q, paths=roots)
    # atribuição de achado -> root (prefixo mais longo) p/ o 'found' do root_done
    counts = {r: 0 for r in roots}
    ordered = sorted(roots, key=len, reverse=True)
    def _attribute(path):
        for r in ordered:
            base = r.rstrip("/")
            if path == base or path == r or path.startswith(base + os.sep):
                counts[r] += 1
                return
        counts[roots[0]] += 1          # sem prefixo casável (ex.: '.') → 1º root
    # F11: fábrica do iterador — a MESMA nos dois modos (serial e particionado).
    # `jobs` só é aplicado no modo particionado; no serial o fd/rg segue com o
    # pool padrão (nº de CPUs), que é o certo quando há um processo só.
    def _fabrica(qq, cc, ss, jobs=None, procs=None):
        if qq.content:
            if RG or (qq.documents and RGA):
                return _iter_content_rg(qq, cc, ss, jobs=jobs, procs=procs)
            return _iter_content_python(qq, cc, ss)
        if FD:
            return _iter_names_fd(qq, cc, ss, jobs=jobs, procs=procs)
        return _iter_names_python(qq, ss, cc)

    if q.skip_snapshots:
        for r in roots:
            if _pula_snapshot([r], True) and tem_snapshot(r):
                # o painel de narrativa avisa; nada de esconder calado
                on_event("snapshots_skipped", {"path": r})

    grupos = _grupos_por_disco(roots)
    # Root apontado PARA DENTRO de um snapshot ganha grupo PROPRIO, senao a
    # decisao dele contaminaria os vizinhos do mesmo disco: buscar em
    # ["/.snapshots/5/snapshot/home", "/"] reabriria os snapshots tambem no "/".
    # Custo aceito: dois processos no mesmo prato nesse caso raro — cada um com
    # o pool de 1 thread da classe, entao o disco ve 2, nao 24.
    if q.skip_snapshots:
        separados = []
        for g in grupos:
            dentro = [r for r in g
                      if eh_snapshot(os.path.abspath(os.path.expanduser(r)) + "/")]
            fora = [r for r in g if r not in dentro]
            separados += [x for x in (fora, dentro) if x]
        grupos = separados
    # F11b: a classe do disco escolhe o pool de cada processo (SSD solto, SMR
    # numa thread só). Vale TAMBÉM no caminho serial: um único SMR ganhava o
    # padrão do fd, nº de CPUs, que era a maior violação da regra da casa aqui.
    # 1 disco só (ou fallback Python, que já é os.walk por root) → nada a ganhar
    # abrindo threads: mantém o caminho serial de sempre.
    paralelo = len(grupos) > 1 and (FD or (q.content and (RG or (q.documents and RGA))))
    if paralelo:
        pendentes = set(roots)

        def _grupo_terminou(paths, meu=None):
            # o disco acabou: já dá pra fechar a narrativa dos roots dele, sem
            # esperar os discos lentos (era isso que o iterador serial impedia)
            erro = (meu or {}).get("erros")
            for r in paths:
                if r in pendentes:
                    pendentes.discard(r)
                    if erro:
                        # honestidade > completude: se o disco caiu no meio, a
                        # GUI pinta linha vermelha em vez de dizer "0 achados"
                        on_event("root_skipped",
                                 {"path": r, "mount": r, "fstype": None,
                                  "klass": None, "reason": "error",
                                  "erro": erro[0].get("erro", "")[:200]})
                    else:
                        on_event("root_done", {"path": r, "found": counts[r]})

        it = _iter_particionado(
            q, cancel, stats, grupos,
            lambda qq, cc, ss, procs: _fabrica(
                replace(qq, skip_snapshots=_pula_snapshot(qq.paths, q.skip_snapshots)),
                cc, ss, procs=procs,
                jobs=_jobs_para_classe([classes.get(r, "unknown") for r in qq.paths])),
            ao_fim=_grupo_terminou)
    else:
        pendentes = set(roots)
        it = _fabrica(replace(q, skip_snapshots=_pula_snapshot(roots, q.skip_snapshots)),
                      cancel, stats,
                      jobs=_jobs_para_classe([classes.get(r, "unknown") for r in roots]))
    for m in it:
        if cancel():
            break
        on_result(m)
        n += 1
        _attribute(m.path)
        if n % 25 == 0:
            on_progress(n)
        if n >= q.max_results:
            break
    for r in roots:                       # F11: no modo particionado a maioria já
        if r in pendentes:                # foi anunciada assim que o disco fechou;
            on_event("root_done", {"path": r, "found": counts[r]})   # aqui sobram
    return n, time.time() - t0            # os interrompidos por cancel/max_results


if __name__ == "__main__":
    # teste rápido de linha de comando
    import sys
    q = Query(paths=[sys.argv[1] if len(sys.argv) > 1 else "."],
              name_patterns=["*.py"], content=sys.argv[2] if len(sys.argv) > 2 else "")
    print("engine:", engine_info())
    tot, dt = search(q, lambda m: print(f"{m.size:>10} {m.path}"
                                        + (f"  [{m.nmatch} matches]" if m.nmatch else "")))
    print(f"\n{tot} resultados em {dt:.2f}s")
