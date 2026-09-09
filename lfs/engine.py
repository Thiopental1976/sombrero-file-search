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

# H1 (Fable 5.1, 08/09/2026): o fd ENGOLE "Permission denied" a menos que receba
# --show-errors — medido: pasta chmod 000, rc=0, stderr vazio. Como a busca por
# NOME é o modo padrão da GUI, o modo padrão do programa mentia por omissão.
# A flag não existe em fd antigos (o fdfind do Ubuntu 20.04 é 7.4), e a
# pergunta é feita AO BINÁRIO: `fd --help` lista as flags que ele aceita.
# Comparar número de versão seria palpite. Cache por caminho do binário, e só
# guarda resposta de um --help que saiu 0 — um exec que falhou não vira "não".
_FD_SHOW_ERRORS: dict = {}

def _fd_mostra_erros(fd=None) -> bool:
    fd = fd or FD
    if not fd:
        return False
    if fd not in _FD_SHOW_ERRORS:
        try:
            r = subprocess.run([fd, "--help"], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=5)
            if r.returncode == 0:
                _FD_SHOW_ERRORS[fd] = b"--show-errors" in r.stdout
        except Exception:
            pass
    return _FD_SHOW_ERRORS.get(fd, False)

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


# Bazzite/ostree (09/09/2026, decisao do Rodrigo): ostree/repo e ostree/deploy
# NAO ganham mecanica propria. Sao "arvore podada" como o Timeshift — a mesma
# poda, o MESMO fallback (vivo primeiro, podadas so se faltar) e o mesmo dedup.
# O que muda e so o TEXTO da nota: a nota nao chama de snapshot o que e o
# acervo do proprio sistema. Decidido pelo PADRAO que casou, nao por nome de
# distro nem por /run/ostree-booted: um ostree/deploy e um ostree/deploy onde
# quer que esteja.
_PADROES_OSTREE = frozenset({"ostree/repo", "ostree/deploy"})

# Podadas que o fallback NAO estende: o repositorio de objetos do ostree e
# content-addressed — ostree/repo/objects/ab/cdef...file, centenas de milhares
# de blobs cujo nome e um sha256. Busca por NOME nunca casaria o que o usuario
# digitou; por CONTEUDO acharia bytes com um caminho que nao diz nada, e os
# mesmos bytes estao na implantacao (ostree/deploy), que E estendida. A nota
# diz que o repo nunca e varrido.
EXCLUSOES_SEM_FALLBACK = frozenset({"ostree/repo"})


def _achados_snapshot(root: str):
    """(padrao, caminho) de cada arvore de snapshot que `root` hospeda — a base
    de tem_snapshot, separada porque em ostree a nota precisa saber QUAL padrao
    casou. Um punhado de glob, sem caminhada.

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
    out = []
    for a in alvos:
        for m in EXCLUSOES_SNAPSHOT:
            try:
                out += [(m, p) for p in _glob.glob(os.path.join(a, m))]
            except OSError:
                pass
    return out


def tem_snapshot(root: str) -> bool:
    """Este root hospeda arvore de snapshot? Serve pro motor AVISAR que escondeu
    algo (esconder em silencio e que nao). Ver _achados_snapshot."""
    return bool(_achados_snapshot(root))


def _globs_snapshot():
    """Padroes p/ o --exclude do fd e o --glob '!' do rg. Precisa ser exclusao
    NO MOTOR, nao filtro na saida: filtrar depois nao economiza a caminhada,
    e a caminhada e justamente o custo (2,4 milhoes de entradas)."""
    fora = []
    for m in EXCLUSOES_SNAPSHOT:
        fora.append(f"**/{m}/**")
        fora.append(f"**/{m}")
    return fora


# ------------------------------------------------- FUNIL ÚNICO DE INCOMPLETUDE
# O lema do projeto é "honestidade > completude", mas até 08/09/2026 ele valia
# onde alguém tinha olhado: havia QUATRO canais paralelos de "algo se perdeu"
# (`denied`, `skipped_mounts`, `engine_errors`, `erros`) e várias perdas não iam
# para nenhum — Popen falhando e caindo no walker Python sem avisar (e o walker
# NÃO acha UTF-16 com BOM que o rg acha), lote de 400 arquivos falhando no
# booleano com um `continue`, match descartado porque o `stat` falhou.
#
# `stats['incompleto']` é o canal único: toda perda passa por aqui, e a barra da
# GUI e o código de saída da CLI DERIVAM dele. Assim "honestidade" deixa de ser
# frase em docstring e vira invariante que dá para testar.
#
# Os canais antigos continuam sendo preenchidos (a GUI e os testes os leem), mas
# são vista, não fonte.
_INCOMPLETO_MAX = 200        # teto: um disco negando 50 mil pastas não vira 50 mil linhas
_DETALHE_MAX = 300           # teto do detalhe (repr de exceção); os textos de _TEXTO_PODA
                             # cabem inteiros — cortar uma chave de i18n a faria não casar

# Motivos que significam "o resultado pode estar ERRADO", não só "faltou um
# pedaço" — só estes mudam o código de saída da CLI, porque um script que checa
# `sfs ... || echo "não achei"` não pode passar a falhar porque uma pasta do
# sistema negou leitura.
# `raiz_invalida` entra (H3): raiz que não existe — disco desmontado, nome
# digitado errado — não é "faltou um pedaço", é ZERO daquele lugar apresentado
# como resposta. grep e rg saem 2 num caminho inexistente; um script que decide
# "não está no disco X" tem de saber que o disco X não estava lá.
MOTIVOS_GRAVES = frozenset({"engine_failed", "engine_missing", "disk_failed",
                            "invalid_root", "not_mounted"})

# H11: o que o funil DESCREVE nasce em EN-US, como o resto da fonte do
# programa — o motivo é identificador estável (é o `reason` do --json, contrato
# de automação) e a frase humana mora aqui, traduzida na RENDERIZAÇÃO pelo
# `tr` que a GUI injeta (i18n.t). A CLI fica em inglês, como todo o resto dela.
MOTIVO_TEXTO = {
    "permission_denied": "permission denied",
    "engine_failed":     "search engine failed",
    "engine_missing":    "search engine missing",
    "disk_failed":       "disk failed",
    "invalid_root":      "invalid location",
    "not_mounted":       "disk not mounted",
    "empty_mountpoint":  "empty mount point",
    "dead_mount":        "mount not responding",
    "stat_failed":       "file vanished",
    "batch_failed":      "batch failed",
    "truncated":         "truncated",
    "snapshots_skipped": "snapshots skipped",
    "snapshots_searched": "snapshots searched",
    "read_error":        "read error",
    "interrupted":       "interrupted",
    "mount_not_entered": "mount not entered",
}

# `reason` do evento root_skipped -> frase (o painel da GUI traduz por t())
REASON_TEXTO = {
    "no_response":  "not responding",
    "broken_mount": "broken mount",
    "invalid_root": "folder not found",
    "not_mounted":  "disk not mounted",
    "not_entered":  "not entered by default",
    "error":        "disk error",
}

# Detalhe da nota de poda (09/09/2026, decisão do Rodrigo: "vivo primeiro,
# snapshots só se faltar"). Chave = (tipo da árvore, o que aconteceu):
#   skipped   — a raiz teve resultado vivo, a podada ficou de fora
#   searched  — zero no vivo, a busca foi ESTENDIDA à podada (fallback)
#   requested — --snapshots / caixa da GUI: estendida sem esperar zero
# O tipo "ostree" só muda o texto; a mecânica é a mesma do "snapshot".
_TEXTO_PODA = {
    ("snapshot", "skipped"):
        "snapshot tree not searched: this location had live results (--snapshots / 'include snapshots' to always search it)",
    ("snapshot", "searched"):
        "nothing in the live tree, so the snapshot tree was searched too; results from it are marked",
    ("snapshot", "requested"):
        "snapshot tree searched as requested; results from it are marked",
    ("ostree", "skipped"):
        "ostree deployments (the system's own image store, not a snapshot) not searched: this location had live results (--snapshots / 'include snapshots' to always search them); the object store ostree/repo is never searched, its files are named by hash",
    ("ostree", "searched"):
        "nothing in the live tree, so the ostree deployments were searched too; results from them are marked (the object store ostree/repo is never searched, its files are named by hash)",
    ("ostree", "requested"):
        "ostree deployments searched as requested; results from them are marked (the object store ostree/repo is never searched, its files are named by hash)",
    # a rodada viva parou (teto/cancel) antes de decidir: não é "teve resultado"
    ("snapshot", "stopped"):
        "snapshot tree not searched: the search stopped (cap or cancel) before reaching it",
    ("ostree", "stopped"):
        "ostree deployments not searched: the search stopped (cap or cancel) before reaching them",
}

# Strings-fonte (EN-US) que este módulo entrega a t() por VARIÁVEL — a guarda
# de i18n (test_i18n_no_stale_keys) consome isto, como faz com humane. Os
# `detalhe="..."` das chamadas de anota_incompleto ficam em UMA linha, literal:
# a guarda os varre no fonte, e concatenação implícita a cegaria.
SOURCE_STRINGS = (frozenset(MOTIVO_TEXTO.values()) | frozenset(REASON_TEXTO.values())
                  | frozenset(_TEXTO_PODA.values())
                  | {" in {where}", "and {n} more occurrence(s) not listed"})


def anota_incompleto(stats, motivo, onde="", detalhe="", n=1, args=None):
    """Registra uma perda de completude. Agrega por (motivo, onde) para não
    estourar, e conta o que passar do teto em vez de descartar em silêncio —
    seria a própria doença que este funil trata.

    `detalhe` é a frase EN-US como está no código (chave do i18n); o que varia
    (código de saída, teto) vai em `args` e é formatado só na renderização —
    senão a chave nunca casaria com a tabela de tradução."""
    if stats is None:
        return
    fila = stats.setdefault("incompleto", [])
    for e in fila:
        if e["motivo"] == motivo and e["onde"] == onde:
            e["n"] += n
            if detalhe and not e.get("detalhe"):
                e["detalhe"] = detalhe[:_DETALHE_MAX]
                if args:
                    e["args"] = dict(args)
            return
    if len(fila) >= _INCOMPLETO_MAX:
        stats["incompleto_omitidos"] = stats.get("incompleto_omitidos", 0) + n
        return
    e = {"motivo": motivo, "onde": onde, "detalhe": (detalhe or "")[:_DETALHE_MAX], "n": n}
    if args:
        e["args"] = dict(args)
    fila.append(e)


def texto_detalhe(e, tr=None) -> str:
    """Detalhe de uma entrada do funil, traduzido e formatado (ver anota_incompleto)."""
    tr = tr or (lambda s: s)
    det = e.get("detalhe") or ""
    if not det:
        return ""
    txt = tr(det)
    args = e.get("args")
    if args:
        try:
            txt = txt.format(**args)
        except (KeyError, IndexError, ValueError):
            pass
    return txt


def resumo_incompleto(stats, tr=None):
    """(grave, linhas) a partir do funil — fonte única da barra da GUI e do
    código de saída da CLI. `tr` (H11) traduz motivo e detalhe p/ o idioma do
    usuário; sem ele, EN-US."""
    tr = tr or (lambda s: s)
    fila = (stats or {}).get("incompleto") or []
    grave = any(e["motivo"] in MOTIVOS_GRAVES for e in fila)
    linhas = []
    for e in fila:
        # `onde` é caminho (passa intacto por tr) ou pseudo-local do booleano
        # ("(NOT universe)"), que se traduz
        alvo = tr(" in {where}").format(where=tr(e["onde"])) if e["onde"] else ""
        vezes = f" (×{e['n']})" if e["n"] > 1 else ""
        det = texto_detalhe(e, tr)
        det = f": {det}" if det else ""
        linhas.append(f"{tr(MOTIVO_TEXTO.get(e['motivo'], e['motivo']))}{alvo}{vezes}{det}")
    om = (stats or {}).get("incompleto_omitidos")
    if om:
        linhas.append(tr("and {n} more occurrence(s) not listed").format(n=om))
    return grave, linhas


# ---------------------------------------------------------------- utilidades
_ERRNO_MONTAGEM_MORTA = frozenset({107, 116, 112, 19})   # ENOTCONN ESTALE EHOSTDOWN ENODEV
_RX_ERRO_MOTOR = re.compile(r"^(?:\[fd error\]|rg|fd|fdfind)?:?\s*(/.*?): ([^:]*)\(os error (\d+)\)\s*$")


def _linha_de_montagem_morta(linha: str):
    """(caminho, mensagem) se a linha de stderr do fd/rg é um errno de montagem
    morta — "[fd error]: /x: Socket not connected (os error 107)",
    "rg: /x: Transport endpoint is not connected (os error 107)"; senão None."""
    m = _RX_ERRO_MOTOR.match(linha.strip())
    if m and int(m.group(3)) in _ERRNO_MONTAGEM_MORTA:
        return m.group(1), m.group(2).strip()
    return None


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
                d = sum(1 for L in linhas if "ermission denied" in L)
                if d:
                    stats["denied"] = stats.get("denied", 0) + d
                    anota_incompleto(stats, "permission_denied", n=d,
                                     detalhe="directories that denied reading")
                # F11b (Fable 5): o rg sai com codigo 2 quando NAO ENTENDE uma
                # flag — p.ex. --glob-case-insensitive, que so existe do rg 12
                # pra cima e falta no Ubuntu 20.04. Antes disso o erro morria
                # aqui dentro e a busca devolvia ZERO RESULTADOS EM SILENCIO,
                # que e o pior modo de falha possivel numa ferramenta cujo lema
                # e "honestidade > completude": o usuario conclui que o arquivo
                # nao existe.
                # CUIDADO ao "corrigir" a lista de codigos: 1 nao quer dizer a
                # mesma coisa nos dois binarios — no rg e "nada casou"
                # (legitimo), no fd e "houve erro na caminhada", tipicamente
                # permission denied. Tratar os dois como legitimos funciona
                # porque o denied ja tem canal proprio, logo acima.
                rc = proc.returncode if proc is not None else None
                # O rg sai com 2 tambem quando so encontrou pasta sem permissao —
                # comportamento NORMAL, e ja contado em 'denied' logo acima. Se a
                # unica queixa no stderr for negacao de permissao, isto nao e
                # falha de motor: chamar de falha faria a CLI sair 2 e um script
                # concluir que a busca quebrou. (Achado pelo proprio funil, no
                # primeiro teste real depois de liga-lo — 08/09/2026.)
                motivo = next((L.strip() for L in linhas
                               if L.strip() and "ermission denied" not in L), "")
                so_permissao = bool(d) and not motivo
                if (rc is not None and rc not in (0, 1, -15, 143)
                        and not so_permissao):
                    msg = (motivo or f"o motor saiu com codigo {rc}")[:200]
                    stats.setdefault("engine_errors", []).append({"rc": rc, "erro": msg})
                    anota_incompleto(stats, "engine_failed",
                                     detalhe="exited with code {rc}: {msg}",
                                     args={"rc": rc, "msg": msg})
                elif motivo:
                    # H1b: com --show-errors o fd passa a contar TUDO que não
                    # conseguiu ler (I/O error, "not a directory") com rc 0/1 —
                    # e este bloco só escutava "Permission denied". Ligar a
                    # flag sem escutar o resto abriria um vazamento novo entre
                    # o fd e este _reap. Medido: o rg --json não escreve nada
                    # no stderr em arquivo binário, então isto não inventa ruído.
                    # F12b: linha com errno de MONTAGEM MORTA (ENOTCONN/ESTALE…)
                    # é dead_mount naquele caminho — o rótulo certo, agregado
                    # com o do gate se ele já a conhecia — e não "read error".
                    outras = 0
                    for L in linhas:
                        if not L.strip() or "ermission denied" in L:
                            continue
                        morta = _linha_de_montagem_morta(L)
                        if morta:
                            anota_incompleto(stats, "dead_mount", onde=morta[0],
                                             detalhe=morta[1])
                        else:
                            outras += 1
                    if outras:
                        anota_incompleto(stats, "read_error", n=outras,
                                         detalhe=motivo[:200])
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
    excluded_paths: tuple = ()        # F12b: montagens MORTAS sob as raízes, condenadas
                                      # pelo gate — nenhum motor as toca (ver _excludes_fd)
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
    # Dedup de resultados (decisão do Rodrigo, 09/09/2026): o mesmo arquivo
    # aparece UMA vez. `ident` = (st_dev, st_ino) de quem fez o stat (hardlink,
    # bind, rsync entre snapshots do Timeshift); `copies` = os outros caminhos
    # que colapsaram neste ("+N cópias" na GUI, lista no --json); `snapshot` =
    # árvore podada de onde o achado veio quando a busca foi ESTENDIDA a ela
    # (None = árvore viva). O caminho vivo tem precedência sobre o do snapshot.
    snapshot: Optional[str] = None
    copies: list[str] = field(default_factory=list)
    ident: Optional[tuple] = None


def _ident_de(st) -> tuple:
    """Identidade do inode por trás de um stat — chave do dedup por identidade."""
    return (st.st_dev, st.st_ino)


def _stat_e_ident(fp):
    """(stat efetivo, identidade) de um caminho listado pelo motor. O stat
    SEGUE symlink (tamanho/mtime do alvo, como sempre foi); a identidade é a do
    PRÓPRIO nó (lstat). Medido na VM Bazzite (09/09/2026): /etc/os-release é
    symlink de /usr/lib/os-release e, com a identidade do alvo, o dedup
    colapsava um no outro — um link é outro objeto, não cópia do alvo. Symlink
    quebrado: o lstat vale pelos dois (E5: casa por nome, mostra o link)."""
    lst = os.lstat(fp)
    if stat.S_ISLNK(lst.st_mode):
        try:
            st = os.stat(fp)
        except OSError:
            st = lst
        return st, _ident_de(lst)
    return lst, _ident_de(lst)


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
            anota_incompleto(stats, "permission_denied",
                             detalhe="directories that denied reading")
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
            if q.excluded_paths:                    # F12b: montagem morta: nem stat
                dns[:] = [d for d in dns if os.path.join(dp, d) not in q.excluded_paths]
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
                        st, ident = _stat_e_ident(dpp)   # E5: symlink quebrado -> lstat
                    except OSError:
                        anota_incompleto(stats, "stat_failed", onde=dpp)   # H5
                        continue
                    if not _passes_meta(q, st):
                        continue
                    yield Match(dpp, st.st_size, st.st_mtime, is_dir=True, ident=ident)
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
                        st, ident = _stat_e_ident(fp)    # E5: symlink quebrado -> lstat
                    except OSError:
                        anota_incompleto(stats, "stat_failed", onde=fp)    # H5
                        continue
                    if not _passes_meta(q, st):
                        continue
                    yield Match(fp, st.st_size, st.st_mtime, ident=ident)


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
        if _fd_mostra_erros(FD):          # H1: sem isto o fd ENGOLE "Permission
            cmd.append("--show-errors")   # denied" e a busca por NOME mente por omissão
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
        cmd += _excludes_fd(q)                 # F12b: montagem morta, nem stat
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
            # NÃO é fallback silencioso: o walker Python não é equivalente ao fd
            anota_incompleto(stats, "engine_missing",
                             detalhe="fd could not be run; using the Python walker")
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
                        st, ident = _stat_e_ident(fp)   # E5: symlink quebrado — mostra o link
                        is_dir = stat.S_ISDIR(st.st_mode)
                    except OSError:
                        # H5: o fd listou e nós descartamos — mesma regra
                        # que o rg já seguia em _iter_content_rg
                        anota_incompleto(stats, "stat_failed", onde=fp,
                                         detalhe="the engine listed it, but the file vanished")
                        continue
                    if not _passes_meta(q, st):
                        continue
                    yield Match(fp, st.st_size, st.st_mtime, is_dir=is_dir, ident=ident)
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
    for e in q.excluded_paths:
        # F12b: no rg '!/abs' NÃO ancora (medido, rg 14.1); '!**/abs' casa o
        # caminho absoluto inteiro como sufixo — exato na prática, e um falso
        # positivo exigiria outro caminho que TERMINE com este inteiro.
        cmd += ["--glob", "!**" + e]
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
        # Aqui a diferença é REAL e não é de desempenho: o fallback Python não
        # decodifica UTF-16/UTF-32 com BOM, que o rg acha. Avisar é obrigatório.
        anota_incompleto(stats, "engine_missing",
                         detalhe="rg could not be run; the Python walker does not read UTF-16/UTF-32 with BOM")
        yield from _iter_content_python(q, cancel, stats); return

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
                    st, ident = _stat_e_ident(path)
                except OSError:
                    # arquivo dentro de container (ex algo.zip/interno.pdf): sem stat no FS
                    cur = Match(path, 0, 0) if docs else None
                    if not docs:
                        # o rg CASOU o conteudo e a gente esta jogando fora o
                        # achado — perda de completude, nao detalhe tecnico
                        anota_incompleto(stats, "stat_failed", onde=path,
                                         detalhe="the engine matched it, but the file vanished")
                    continue
                if not _passes_meta(q, st):
                    cur = None; continue
                cur = Match(path, st.st_size, st.st_mtime, ident=ident)
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
            anota_incompleto(stats, "stat_failed", onde=m.path)   # H5: o walker listou
            continue                                            # e o arquivo sumiu
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
                # H4: contava em 'denied' (vista) e não no funil (fonte) — o
                # arquivo que não abre sumia do relatório da CLI e da barra.
                anota_incompleto(stats, "permission_denied", onde=os.path.dirname(m.path),
                                 detalhe="files that denied reading")
            continue
        except OSError as e:
            # H4b: EIO num disco ruim, ELOOP, ENXIO… — o arquivo NÃO foi lido.
            # Um `continue` mudo aqui era o walker mentindo igual ao fd sem flag.
            anota_incompleto(stats, "read_error", onde=m.path,
                             detalhe=e.strerror or repr(e))
            continue
        except UnicodeError:
            continue


# ---------------------------------------------------------------- API pública
_existe = os.path.exists     # injetáveis: os testes do gate montam topologias
_eh_pasta = os.path.isdir    # fictícias (/mnt/nas2/y) sem NAS nenhum na máquina


def _vazia(p) -> bool:
    try:
        with os.scandir(p) as it:
            return next(it, None) is None
    except OSError:
        return False                 # sem permissão/erro não é "vazia": outro funil


def _eh_mountpoint(p) -> bool:
    try:
        import disks  # type: ignore
        return disks.is_mountpoint(p)
    except Exception:
        return True                  # sem `disks` não há como afirmar; não acusa


def _fstab_alvos() -> set:
    try:
        import disks  # type: ignore
        return disks.fstab_targets()
    except Exception:
        return set()


def _eh_vaga_de_montagem(p) -> bool:
    try:
        import disks  # type: ignore
        return disks.is_mount_slot(p)
    except Exception:
        return False

def _raiz_existe(root, stats, on_event=lambda ev, info: None) -> bool:
    """H3: raiz que não existe (disco desmontado, caminho digitado errado) era
    a mentira mais barata do programa — devolvia "0 resultados" com cara de
    resposta legítima nos cinco backends (o fd sai 1 e cala; o rg sai 2 e virava
    'engine_failed', rótulo errado; o os.walk chama onerror com
    FileNotFoundError, que o _walk_onerror ignora por não ser PermissionError).
    Um lugar só, no gate por onde TODA busca passa (engine.search e
    search_boolean chamam _live_roots)."""
    if not _existe(root):
        detalhe = "path does not exist (disk unmounted? typo?)"
    elif not _eh_pasta(root):
        # H3b: os backends DIVERGIAM — o rg aceita um arquivo como raiz, o fd
        # recusa ("Search path is not a directory", rc 1, mudo) e o os.walk
        # chama onerror com NotADirectoryError, ignorado. A CLI documenta
        # "folder(s) to search in"; recusar nos cinco é a única resposta igual.
        detalhe = "not a folder — searches take folders"
    else:
        return _raiz_montada(root, stats, on_event)
    anota_incompleto(stats, "invalid_root", onde=root, detalhe=detalhe)
    on_event("root_skipped", {"path": root, "mount": None, "fstype": None,
                              "klass": None, "reason": "invalid_root"})
    return False


def _raiz_montada(root, stats, on_event=lambda ev, info: None) -> bool:
    """H13 (09/09/2026): ponto de montagem VAZIO era a mentira que sobrou depois
    do H3 — /mnt/BACKUP sem o disco existe, é pasta, e "0 resultados" ali
    parecia resposta. Dois sinais, separados pelo que se pode AFIRMAR:
      - FATO (grave, raiz pulada): a pasta está no /etc/fstab como ponto de
        montagem e não está montada. O disco deveria estar ali e não está.
      - INDÍCIO (não-grave, a busca segue): pasta vazia numa vaga de montagem
        (/mnt/X, /media/<user>/X…) que não é ponto de montagem. Pode ser só
        uma pasta vazia; o programa não sabe — então diz o que viu e pergunta.
    Roda só DEPOIS de existir+ser pasta e depois da sonda de rede (scandir
    numa montagem morta travaria; aqui ela já respondeu)."""
    r = root.rstrip("/") or "/"
    if _eh_mountpoint(r):
        return True
    if r in _fstab_alvos():
        anota_incompleto(stats, "not_mounted", onde=root,
                         detalhe="listed in /etc/fstab but not mounted")
        on_event("root_skipped", {"path": root, "mount": None, "fstype": None,
                                  "klass": None, "reason": "not_mounted"})
        return False
    if _eh_vaga_de_montagem(r) and _vazia(r):
        anota_incompleto(stats, "empty_mountpoint", onde=root,
                         detalhe="empty folder where disks are mounted — is the disk mounted?")
    return True


# ------------------------------------------ vivo primeiro, podadas só se faltar
# Decisão do Rodrigo (09/09/2026): "não incluir snapshots é bom para a
# performance mas não é bom para o projeto — o SFS é um buscador de arquivos.
# Se o alvo do usuário estiver nas pastas de snapshot ele vai receber nada."
# A busca varre a árvore viva como sempre (poda em vigor); se a raiz DIGITADA
# devolver ZERO, a MESMA consulta é estendida às árvores podadas que ela
# hospeda, e a nota diz que foi. Com --snapshots / caixa da GUI a extensão é
# incondicional. Timeshift, snapper, ZFS, Samba e ostree/deploy passam pelo
# mesmo caminho; a única diferença é o texto da nota (ver _TEXTO_PODA).
#
# "Zero" é por raiz DIGITADA, não por raiz expandida: buscar em "/" no Bazzite
# vira [/, /boot, /etc, /sysroot, /var], e o /sysroot (só ostree) daria zero em
# toda consulta — estenderia às implantações mesmo com /etc/os-release achado.
# A unidade de decisão é o que o usuário pediu.

def _arvores_podadas(roots, q_paths, excluidos=()):
    """Árvores podadas hospedadas pelas raízes vivas, uma vez cada (por caminho
    real — "/ostree" é symlink de "/sysroot/ostree"), com o dono da nota.

    Devolve lista de dicts {arvore, padrao, dono, digitada, fallback}:
      arvore    — caminho REAL da árvore podada (raiz da extensão)
      padrao    — qual padrão de EXCLUSOES_SNAPSHOT casou (dita o texto e o
                  cálculo do caminho vivo, ver _caminho_vivo)
      dono      — raiz viva mais específica que a contém (onde da nota)
      digitada  — raiz que o usuário digitou e que contém o dono (unidade do
                  "zero")
      fallback  — False para EXCLUSOES_SEM_FALLBACK (ostree/repo): só nota
    Fora: árvore cuja montagem mais específica não é raiz viva nem a montagem
    de uma (disco que o gate não entrou, ou --one-fs do usuário — não cruza
    montagem para estender o que a busca viva não cruzou) e árvore sob uma
    montagem morta/condenada."""
    disks = _mod_disks()
    def montagem(p):
        if disks is None:
            return None
        try:
            return disks._mount_entry(p)[1]
        except Exception:
            return None
    vivas = [os.path.abspath(os.path.expanduser(r)) for r in roots]
    monts_vivas = {montagem(r) for r in vivas} | set(vivas)
    vistos, out = set(), []
    for r in roots:
        if not _pula_snapshot([r], True):        # raiz DENTRO de um snapshot: a
            continue                             # poda não está em vigor nela
        for padrao, p in _achados_snapshot(r):
            rp = os.path.realpath(p)
            if rp in vistos:
                continue
            vistos.add(rp)
            dono = _raiz_mais_especifica(rp, roots)
            if dono is None:
                continue
            if any(rp == e or _sob(rp, e) for e in excluidos):
                continue
            m = montagem(rp)
            if m is not None and m not in monts_vivas:
                continue
            digitada = _raiz_mais_especifica(os.path.abspath(os.path.expanduser(dono)),
                                             q_paths) or dono
            out.append({"arvore": rp, "padrao": padrao, "dono": dono,
                        "digitada": digitada,
                        "fallback": padrao not in EXCLUSOES_SEM_FALLBACK})
    return out


def _caminho_vivo(path, arvore, padrao):
    """Onde este arquivo do snapshot ESTARIA na árvore viva — a chave do dedup
    por cópia idêntica (caminho vivo + tamanho + mtime). None quando o layout
    não é o esperado: então o achado fica só com o dedup por inode.
    Layouts (09/09/2026), `arvore` = caminho real da árvore podada:
      timeshift/snapshots*  <arvore>/<data>/localhost/<rel>        -> /<rel>
      timeshift-btrfs       <arvore>/snapshots/<data>/@|@x/<rel>   -> /<rel> | /x/<rel>
      .snapshots (snapper)  <arvore>/<n>/snapshot/<rel>            -> <pai da arvore>/<rel>
      .zfs/snapshot         <arvore>/<nome>/<rel>                  -> <dataset>/<rel>
      @GMT-*  (Samba)       <arvore>/<rel>                         -> <pai da arvore>/<rel>
      ostree/deploy         <arvore>/<os>/deploy/<hash>.N/<rel>    -> /<rel>"""
    base = arvore.rstrip("/")
    if not path.startswith(base + "/"):
        return None
    comps = path[len(base) + 1:].split("/")
    if padrao == "timeshift/snapshots*":
        if len(comps) >= 3 and comps[1] == "localhost":
            return "/" + "/".join(comps[2:])
    elif padrao == "timeshift-btrfs":
        if len(comps) >= 4 and comps[0] == "snapshots":
            sub = comps[2]
            raiz = "/" if sub == "@" else "/" + sub.lstrip("@")
            return os.path.join(raiz, *comps[3:])
    elif padrao == ".snapshots":
        if len(comps) >= 3 and comps[1] == "snapshot":
            return os.path.join(os.path.dirname(base), *comps[2:])
    elif padrao == ".zfs/snapshot":
        if len(comps) >= 2:
            return os.path.join(os.path.dirname(os.path.dirname(base)), *comps[1:])
    elif padrao == "@GMT-*":
        if comps and comps[0]:
            return os.path.join(os.path.dirname(base), *comps)
    elif padrao == "ostree/deploy":
        if len(comps) >= 4 and comps[1] == "deploy":
            return "/" + "/".join(comps[3:])
    return None


class _Colapso:
    """Dedup de resultados (decisão do Rodrigo, 09/09/2026): o mesmo arquivo
    vira UM resultado. Mesmo arquivo =
      - mesma identidade (st_dev, st_ino): hardlink, bind, rsync do Timeshift
        entre snapshots; ou
      - cópia idêntica: mesmo caminho vivo (o próprio, ou o reconstruído por
        _caminho_vivo para achado de snapshot) + tamanho + mtime em segundos
        inteiros (btrfs/snapper e ostree têm inodes distintos; o mtime em
        segundos é o que sobrevive a rsync/protocolos antigos).
    Sem ler conteúdo. Quem chega primeiro fica; como a árvore viva é varrida
    ANTES das podadas, o caminho vivo tem precedência por construção. Só
    snapshot (arquivo já apagado do vivo) aparece com o caminho do snapshot.
    O lado ruim, declarado: dois arquivos DIFERENTES no mesmo caminho vivo com
    o mesmo tamanho e o mesmo segundo de mtime colapsariam — na prática é o
    mesmo arquivo."""

    def __init__(self):
        self.por_ident = {}
        self.por_copia = {}

    def absorve(self, m, vivo=None):
        """Registra `m`. Devolve o Match DONO se `m` é cópia de um já entregue
        (e anexa o caminho em dono.copies); None se `m` é novo."""
        k_id = m.ident
        k_cp = (vivo or m.path, m.size, int(m.mtime or 0))
        dono = self.por_ident.get(k_id) if k_id is not None else None
        if dono is None:
            dono = self.por_copia.get(k_cp)
        if dono is None:
            if k_id is not None:
                self.por_ident[k_id] = m
            self.por_copia[k_cp] = m
            return None
        if k_id is not None:
            self.por_ident.setdefault(k_id, dono)
        self.por_copia.setdefault(k_cp, dono)
        # mesma raiz digitada duas vezes ("/" e "/home") listava o arquivo 2x:
        # não é cópia, é o mesmo caminho — colapsa sem anotar
        if m.path != dono.path and m.path not in dono.copies:
            dono.copies.append(m.path)
        return dono


class _Entrega:
    """Funil de ENTREGA, compartilhado por search() e search_boolean(): dedup
    (_Colapso), teto de resultados (truncated no funil), contagem e progresso.
    É aqui — antes de CLI, --json, GUI e booleano — que o dedup mora, para que
    os quatro vejam o mesmo resultado. Cópia absorvida vira evento 'copy'
    {path, of, snapshot} (o --json a relata; a GUI ignora e relê o Match)."""

    def __init__(self, on_result, on_progress, stats, cap, on_event):
        self.on_result, self.on_progress = on_result, on_progress
        self.stats, self.cap, self.on_event = stats, cap, on_event
        self.colapso = _Colapso()
        self.n = 0
        self.parou = False          # teto atingido: nada mais entra (nem extensão)

    def entrega(self, m, origem=None) -> bool:
        """`origem` = (arvore, padrao) quando o achado veio da extensão às
        podadas. True se `m` foi entregue como resultado novo."""
        vivo = None
        if origem is not None:
            m.snapshot = origem[0]
            vivo = _caminho_vivo(m.path, origem[0], origem[1])
        dono = self.colapso.absorve(m, vivo)
        if dono is not None:
            if m.path != dono.path:      # o mesmo caminho 2x não é cópia de nada
                self.on_event("copy", {"path": m.path, "of": dono.path, "snapshot": m.snapshot})
            return False
        self.on_result(m)
        self.n += 1
        if self.n % 25 == 0:
            self.on_progress(self.n)
        if self.n >= self.cap:
            # H2: ninguém EXPÕE max_results — nem a GUI nem a CLI têm controle
            # pra isso; é um teto interno. Parar nele sem dizer é o programa
            # decidindo por conta própria que o usuário já viu o bastante.
            # Não-grave: o que foi mostrado está certo, só não é tudo.
            anota_incompleto(self.stats, "truncated",
                             detalhe="stopped at the cap of {cap} results; there may be more",
                             args={"cap": self.cap})
            self.parou = True
        return True


def _plano_extensao(q, roots, counts, parou, stats, on_event, excluidos=()):
    """Depois da rodada viva: decide, por raiz DIGITADA, quais árvores podadas
    entram na extensão, e escreve a nota de cada dono no funil E no painel
    (H6: a CLI só enxerga o funil). Devolve a lista de árvores a estender
    (dicts de _arvores_podadas), vazia se não há o que estender.

    `parou` (teto ou cancelamento na rodada viva): não estende nada — o teto
    já foi anunciado como 'truncated', e cancelar é cancelar."""
    arvores = _arvores_podadas(roots, q.paths, excluidos)
    if not arvores:
        return []
    achados = {}                         # raiz digitada -> achados vivos
    for r in roots:
        d = _raiz_mais_especifica(os.path.abspath(os.path.expanduser(r)), q.paths) or r
        achados[d] = achados.get(d, 0) + counts.get(r, 0)
    estender = []
    por_dono = {}
    for a in arvores:
        if parou:
            modo = "stopped"
        elif not q.skip_snapshots:
            modo = "requested"
        elif achados.get(a["digitada"], 0) == 0:
            modo = "searched"
        else:
            modo = "skipped"
        if modo in ("searched", "requested") and a["fallback"]:
            estender.append(a)
        por_dono.setdefault(a["dono"], []).append((a, modo))
    for dono, lst in por_dono.items():
        tipo = "ostree" if all(a["padrao"] in _PADROES_OSTREE for a, _m in lst) else "snapshot"
        modos = {m for a, m in lst if a["fallback"]} or {"skipped"}
        modo = next((m for m in ("requested", "searched", "stopped") if m in modos), "skipped")
        motivo = "snapshots_searched" if modo in ("requested", "searched") else "snapshots_skipped"
        anota_incompleto(stats, motivo, onde=dono, detalhe=_TEXTO_PODA[(tipo, modo)])
        on_event(motivo, {"path": dono, "ostree": tipo == "ostree",
                          "trees": [a["arvore"] for a, m in lst
                                    if m in ("requested", "searched") and a["fallback"]]})
    return estender


def _query_extensao(q, plano, forca_one_fs=False):
    """A Query da rodada de extensão: raízes = as árvores podadas, poda
    desligada (quem aponta pra dentro de um snapshot quer aquilo — F11 bug3,
    mesma regra), e as MONTAGENS sob cada árvore excluídas: no ostree o
    /var é bind de deploy/<os>/var e já foi varrido como raiz viva — varrer de
    novo por outro nome seria o próprio desperdício que o dedup esconderia."""
    disks = _mod_disks()
    trees = [a["arvore"] for a in plano]
    excl = set(q.excluded_paths)
    if disks is not None:
        for tr in trees:
            try:
                excl |= set(disks.mounts_under(tr))
            except Exception:
                pass
    excl = tuple(sorted(e for e in excl if any(_sob(e, tr) for tr in trees)))
    return replace(q, paths=trees, skip_snapshots=False, excluded_paths=excl,
                   one_file_system=q.one_file_system or forca_one_fs)


def _origem_de(plano):
    """path -> (arvore, padrao) da árvore podada de prefixo mais longo que o
    contém (a origem marcada no Match), e path -> dono (raiz viva) p/ contagem."""
    ordem = sorted(plano, key=lambda a: len(a["arvore"]), reverse=True)

    def origem(path):
        for a in ordem:
            if path == a["arvore"] or _sob(path, a["arvore"]):
                return (a["arvore"], a["padrao"])
        return None

    def dono(path):
        for a in ordem:
            if path == a["arvore"] or _sob(path, a["arvore"]):
                return a["dono"]
        return ordem[0]["dono"] if ordem else None
    return origem, dono


def _raiz_mais_especifica(path, roots):
    """A raiz de `roots` que contém `path` pelo prefixo mais longo (a mais
    próxima dele); None se nenhuma contém."""
    melhor, tam = None, -1
    for r in roots:
        ra = os.path.abspath(os.path.expanduser(r))
        if (path == ra or _sob(path, ra)) and len(ra) > tam:
            melhor, tam = r, len(ra)
    return melhor


def _sob(path, root) -> bool:
    """`path` está estritamente dentro de `root`?"""
    base = root.rstrip("/")
    return path != base and path.startswith(base + "/")


def _query_planejada(q: Query, roots, forca_one_fs: bool, mortas) -> Query:
    """A Query que os motores recebem depois do gate: raízes vivas, one-fs
    forçado quando houve expansão, e as montagens mortas sob alguma raiz em
    `excluded_paths`."""
    excl = tuple(sorted({m for m in mortas if any(_sob(m, r) for r in roots)}))
    if roots == list(q.paths) and not forca_one_fs and not excl:
        return q
    return replace(q, paths=roots, one_file_system=q.one_file_system or forca_one_fs,
                   excluded_paths=excl)


def _separa_raizes_com_mortas(grupos, excluidos):
    """F12b: o `--exclude '/rel'` do fd ancora na PRIMEIRA raiz do processo
    (medido: fd 10.4 — '/x' com raízes A e B exclui só A/x). Raiz com montagem
    morta embaixo ganha processo próprio, e aí a âncora é exata."""
    if not excluidos:
        return grupos
    out = []
    for g in grupos:
        com = [r for r in g if any(_sob(e, r) for e in excluidos)]
        sem = [r for r in g if r not in com]
        if sem:
            out.append(sem)
        out += [[r] for r in com]
    return out


def _excludes_fd(q: Query):
    """`--exclude` do fd para Query.excluded_paths, relativo à raiz (única, por
    _separa_raizes_com_mortas) e ancorado com '/'."""
    flags = []
    for r in q.paths:
        for e in q.excluded_paths:
            if _sob(e, r):
                flags += ["--exclude", "/" + os.path.relpath(e, r)]
    return flags


def _atribuidor(roots):
    """(counts, attribute): atribui cada achado ao root de prefixo mais longo,
    p/ o 'found' do evento root_done. H12: fatorado do search() porque o
    booleano emitia evento nenhum — a GUI ficava sem painel de narrativa numa
    busca booleana, e a mesma raiz inválida aparecia de um jeito na busca
    simples e de outro na booleana."""
    counts = {r: 0 for r in roots}
    ordered = sorted(roots, key=len, reverse=True)

    def attribute(path):
        for r in ordered:
            base = r.rstrip("/")
            if path == base or path == r or path.startswith(base + os.sep):
                counts[r] += 1
                return
        if roots:
            counts[roots[0]] += 1      # sem prefixo casável (ex.: '.') → 1º root
    return counts, attribute


def _mod_disks():
    try:
        from . import disks
        return disks
    except Exception:
        try:
            import disks  # type: ignore
            return disks
        except Exception:
            return None


# F12 (09/09/2026): sistemas de arquivos do KERNEL que moram sob "/" e não têm
# arquivo de usuário. Ficam fora da expansão e o walker do "/" roda com
# --one-file-system, então nunca são varridos. tmpfs/squashfs/overlay FICAM:
# há arquivo de verdade lá.
_PSEUDO_FS = frozenset({
    "proc", "sysfs", "devtmpfs", "devpts", "cgroup", "cgroup2", "securityfs",
    "pstore", "efivarfs", "bpf", "debugfs", "tracefs", "configfs", "fusectl",
    "hugetlbfs", "mqueue", "binfmt_misc", "nsfs", "rpc_pipefs", "selinuxfs",
})

_st_dev = lambda p: os.stat(p).st_dev     # injetável (topologias fictícias nos testes)
# identidade do DIRETÓRIO por trás de um caminho (Bazzite/ostree 09/09/2026):
# duas montagens com o mesmo par são o mesmo diretório (bind). Injetável.
_ident = lambda p: (lambda st: (st.st_dev, st.st_ino))(os.stat(p))


def planejar_raizes(paths, one_fs: bool, stats=None,
                    on_event=lambda ev, info: None, mounts=None, mortas=None,
                    probe_timeout: float = 3.0):
    """F12 — EXPANSÃO DE RAÍZES. Buscar em "/" ou "/mnt" quer dizer "em tudo que
    mora ali embaixo", inclusive NFS/SMB (decisão do Rodrigo, 09/09/2026). Até
    aqui o gate F9a só sondava o que o usuário DIGITOU: "/" passava como disco
    local e o fd descia sozinho até a montagem de rede morta — o congelamento
    que o gate existe para evitar. Agora cada montagem sob uma raiz vira RAIZ
    PRÓPRIA (passa pelo gate uma a uma, ganha grupo por disco, paraleliza) e o
    walker da raiz-mãe roda com --one-file-system para não entrar de novo.

    Devolve (roots, expandidas, forcar_one_fs). `one_fs` explícito do usuário
    desliga a expansão: aí ele pediu UMA pasta e só ela.

    Fora da expansão, sempre DITO: pseudo-fs do kernel (nota, não perda —
    stats['pruned_mounts']); montagens que a política F9a não enumera por
    padrão (gvfs = celular, autofs = gatilho que acordaria todo mount da casa)
    entram no funil como `mount_not_entered`, não-grave: "não entrei; busque
    pelo caminho dela". Bind mount do MESMO sistema de arquivos (st_dev igual
    ao da raiz-mãe) não vira raiz: o --one-file-system não a separa e ela
    seria varrida duas vezes. Subvolume btrfs tem st_dev próprio e vira raiz.

    Bazzite/ostree (09/09/2026): a comparação de st_dev acima só enxerga a
    raiz-mãe, não as IRMÃS. No ostree /var é bind de
    /sysroot/ostree/deploy/default/var — mesmo diretório, duas montagens, ambas
    com st_dev diferente de "/" (composefs) — e as duas viravam raiz; a de
    dentro de ostree/deploy ainda ganhava grupo próprio com a poda de snapshots
    DESLIGADA (_pula_snapshot), e o /var era varrido 2× com prefixos
    diferentes. Agora montagens expandidas que são o MESMO diretório
    ((st_dev, st_ino) do ponto de montagem — fato do kernel, vale pra qualquer
    bind em qualquer distro) entram uma vez: o que o usuário digitou tem
    precedência; entre expandidas fica a de caminho mais curto, que é o nome
    pelo qual ele conhece a pasta (/var, não /sysroot/ostree/…). Não é perda:
    o diretório é varrido, sob o outro nome — por isso não passa pelo funil."""
    roots = []
    seen = set()
    for r in paths:
        if r not in seen:
            roots.append(r); seen.add(r)
    disks = _mod_disks()
    if disks is None:
        return roots, set(), False
    if one_fs:
        # F12b: sem expansão, mas o walker da raiz ainda faz stat em cada ponto
        # de montagem sob ela (é assim que --one-file-system compara st_dev), e
        # num NFS/FUSE em D-state esse stat TRAVA. Sonda cada montagem sob a
        # raiz (0,7 ms cada, medido) e condena as mortas: entram em
        # `mortas` -> Query.excluded_paths, e nenhum motor as toca.
        for r in roots:
            try:
                sob = disks.mounts_under(r, mounts)
            except Exception:
                continue
            for mp in sob:
                try:
                    fstype = next((fs for _d, m, fs in
                                   (mounts if mounts is not None else disks._read_mounts())
                                   if m == mp), "")
                except OSError:
                    fstype = ""
                if fstype.lower() in _PSEUDO_FS:
                    continue
                status = disks.mount_status(mp, timeout=probe_timeout)
                if status != "alive":
                    _condena_montagem(mp, fstype, None, status, stats, on_event, mortas)
        return roots, set(), False
    expandidas, podadas = set(), []
    ids_digitadas = set()     # identidade das raízes digitadas: elas mandam
    candidatas = []           # (mp, identidade|None) na ordem de descoberta
    for r in list(roots):
        try:
            sob = disks.mounts_under(r, mounts)
        except Exception:
            continue
        try:
            dev_mae = _st_dev(r)
        except OSError:
            dev_mae = None
        try:
            ids_digitadas.add(_ident(r))
        except OSError:
            pass
        for mp in sob:
            if mp in seen:
                continue
            try:
                prof = disks.search_profile(mp, mounts) if mounts is not None else disks.search_profile(mp)
            except Exception:
                prof = None
            fstype = (prof.fstype if prof else "").lower()
            if fstype in _PSEUDO_FS:
                podadas.append(mp); seen.add(mp)
                continue
            if prof is not None and not prof.enumerate_default:
                seen.add(mp)
                anota_incompleto(stats, "mount_not_entered", onde=mp,
                                 detalhe="not entered by default ({klass}); search it by its own path",
                                 args={"klass": prof.klass})
                on_event("root_skipped", {"path": mp, "mount": mp, "fstype": prof.fstype,
                                          "klass": prof.klass, "reason": "not_entered"})
                continue
            # bind do mesmo FS: só em disco LOCAL de bloco dá pra fazer stat com
            # segurança (rede/FUSE pode travar — isso é trabalho da sonda do gate)
            ident = None
            if prof is not None and not prof.is_network and not fstype.startswith("fuse"):
                if dev_mae is not None:
                    try:
                        if _st_dev(mp) == dev_mae:
                            seen.add(mp)
                            continue
                    except OSError:
                        pass
                try:
                    ident = _ident(mp)
                except OSError:
                    ident = None
            candidatas.append((mp, ident)); seen.add(mp)
    # bind do MESMO diretório entre irmãs/digitadas (ver docstring): uma só
    vencedora = {}
    for mp, ident in candidatas:
        if ident is not None and ident not in ids_digitadas:
            atual = vencedora.get(ident)
            if atual is None or (len(mp), mp) < (len(atual), atual):
                vencedora[ident] = mp
    for mp, ident in candidatas:
        if ident is not None and vencedora.get(ident) != mp:
            continue          # mesmo diretório que outra raiz: já é varrido por ela
        roots.append(mp); expandidas.add(mp)
    if podadas and stats is not None:
        stats.setdefault("pruned_mounts", []).extend(podadas)
    return roots, expandidas, bool(expandidas)


def _condena_montagem(mp, fstype, klass, status, stats, on_event, mortas, path=None):
    """Registra uma montagem morta nos três canais — funil (dead_mount),
    stats['skipped_mounts'] (CLI/JSON) e painel (root_skipped) — e em `mortas`,
    que vira Query.excluded_paths: o que o gate condenou, nenhum motor toca."""
    if stats is not None:
        stats.setdefault("skipped_mounts", []).append(
            {"path": path or mp, "mount": mp, "fstype": fstype, "reason": status})
        anota_incompleto(stats, "dead_mount", onde=mp,
                         detalhe=f"{fstype}: {status}")   # 'no_response' | 'broken_mount'
    on_event("root_skipped", {"path": path or mp, "mount": mp, "fstype": fstype,
                              "klass": klass, "reason": status})
    if mortas is not None:
        mortas.append(mp)


def _live_roots(paths, stats, probe_timeout: float = 3.0,
                on_event=lambda ev, info: None, classes=None,
                expandidas=frozenset(), mortas=None):
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
            # sem `disks` não há sonda de rede, mas o gate de existência (H3)
            # continua valendo — é o que menos custa e o que mais mentia
            return [r for r in paths if _raiz_existe(r, stats, on_event)]
    live = []
    for root in paths:
        try:
            prof = disks.search_profile(root)
        except Exception:
            if not _raiz_existe(root, stats, on_event):
                continue
            if classes is not None:
                classes[root] = "unknown"
            live.append(root)          # não sei classificar → não bloqueio
            on_event("root_scanning",   # F10a §2: badge de classe p/ o painel
                     {"path": root, "klass": "unknown", "mountpoint": None})
            continue
        # F12: raiz que veio da EXPANSÃO é uma montagem que ninguém digitou —
        # sonda TODA classe (um FUSE de portal/RustDesk preso em D trava igual
        # a NFS) e, morta, é perda não-grave (dead_mount), não raiz inválida.
        if prof.is_network or root in expandidas:
            mp = prof.mountpoint or root
            status = disks.mount_status(mp, timeout=probe_timeout)
            if status != "alive":
                # linha VERMELHA ao vivo (não popup no fim) — F10a §2
                _condena_montagem(mp, prof.fstype, prof.klass, status, stats, on_event,
                                  mortas, path=root)
                continue
        # H3: só DEPOIS da sonda de rede — os.path.exists() numa montagem NFS em
        # D-state trava o processo, que é o congelamento que o F9a existe para
        # evitar. Aqui a montagem já respondeu (ou é local), e o stat é barato.
        if root not in expandidas and not _raiz_existe(root, stats, on_event):
            continue                      # expandida: está montada, por definição
        live.append(root)
        if classes is not None:
            classes[root] = prof            # perfil inteiro: _jobs_para_classe lê serialize
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


def _jobs_para_classe(classes_do_grupo, conteudo: bool = False):
    """Pool de um processo particionado. Grupo com classes mistas (roots do mesmo
    disco não deveriam divergir, mas acontece com bind mount) leva a política
    MAIS conservadora — errar para menos só custa tempo; errar para mais faz o
    cabeçote de um disco mecânico passear.

    `conteudo` (medido em 09/09/2026, SMR de 8 TB, cache frio): a regra "um
    cabeçote, uma thread" vale para a busca por NOME (metadados, sequenciais no
    disco: 1 thread 38 s vs pool cheio 48 s). Busca por CONTEÚDO abre cada
    arquivo, e aí é o contrário — o disco reordena leituras quando há vários
    pedidos em voo: pool cheio 35 s (duas rodadas), 4 threads 38 s, 1 thread
    52 s e 657 s. Estrangular o rg em disco mecânico só custava. Rede continua
    com o teto por montagem: lá o limite é a latência, não o cabeçote."""
    rede = _jobs_de_rede()
    valores = []
    for c in classes_do_grupo:          # str (classe) ou IOProfile (classe + serialize)
        k = getattr(c, "klass", c)
        if k in ("network", "gvfs", "autofs"):
            valores.append(rede)
        elif conteudo:
            valores.append(None)        # conteúdo: fila funda ajuda até no SMR
        elif getattr(c, "serialize", False):
            valores.append(1)           # o perfil pediu um de cada vez: um cabeçote
        else:                           # (ou algo que não sei medir, sob /mnt)
            valores.append(_JOBS_POR_CLASSE.get(k))
    valores = valores or [None]
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
            ent = disks._mount_entry(os.path.abspath(root))
            dev, _mp, fstype = ent
            # ZFS: o "dev" é pool/dataset, não um nó de bloco. Sem isto cada
            # dataset viraria um grupo e abriríamos N processos no MESMO pool.
            if (fstype or "").lower() == "zfs" and dev:
                return ("zpool", dev.split("/")[0])
            # composefs (Bazzite/ostree, 09/09/2026): "/" não tem nó de bloco,
            # mas o kernel declara datadir+=/sysroot/... — o mesmo prato de
            # /sysroot, /var e /etc. Sem isto "/" caía no reserva (st_dev) e
            # virava grupo próprio: dois processos no mesmo disco.
            dev = disks._backing_dev(ent)
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
        if k == "incompleto":
            # H7: NÃO concatenar — cada worker já agregou por (motivo, onde).
            # Um extend devolvia 'sem_permissao (×3)' e 'sem_permissao (×5)'
            # em vez de (×8): o relatório mentia pra menos em cada linha.
            for e in v:
                anota_incompleto(dst, e["motivo"], e.get("onde", ""),
                                 e.get("detalhe", ""), e.get("n", 1),
                                 args=e.get("args"))   # sem isto o particionado
                                                       # mostrava "{rc}: {msg}" cru
        elif isinstance(v, list):
            dst.setdefault(k, []).extend(v)
        elif isinstance(v, (int, float)):
            dst[k] = dst.get(k, 0) + v
        else:
            dst.setdefault(k, v)


def _iter_particionado(q: Query, cancel, stats, grupos, fabrica, ao_fim=None,
                       limite_s: float = 5.0):
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
    fins = set()        # H9: grupos cujo FIM (e stats) chegou — ver o finally

    def trabalha(paths):
        meu = {}
        try:
            for m in fabrica(replace(q, paths=paths), _cancel, meu, procs):
                if _cancel():
                    break
                fila.put(m)
        except Exception as e:                # um disco quebrar não derruba a busca
            meu.setdefault("erros", []).append({"paths": paths, "erro": repr(e)})
            anota_incompleto(meu, "disk_failed", onde=paths[0] if paths else "",
                             detalhe=repr(e))
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
                fins.add(tuple(paths))
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

        limite = time.time() + limite_s   # teto: são daemon threads, jamais seguram
        while time.time() < limite:       # a busca refém de um I/O que não volta
            _mata()
            if not any(t.is_alive() for t in threads):
                break
            try:
                item = fila.get(timeout=0.05)
            except queue.Empty:
                continue
            # não perde o 'denied' de quem foi interrompido no meio
            if isinstance(item, tuple) and item and item[0] is FIM:
                fins.add(tuple(item[1]))
                _funde_stats(stats, item[2])
        _mata()
        for t in threads:
            t.join(timeout=0.2)
        # H9: quem não respondeu dentro do teto levou consigo o próprio dict de
        # stats — as perdas DAQUELE disco não foram contadas. Era o último
        # caminho em que o funil perdia entrada por desenho; agora ele diz
        # que não sabe, em vez de fingir que sabe.
        for g in grupos:
            if tuple(g) not in fins:
                anota_incompleto(stats, "interrupted", onde=g[0] if g else "",
                                 detalhe="the disk did not answer the cancel in time; its losses were not counted")


def _rodada(q, roots, classes, cancel, stats, on_event, entrega, origem_de=None,
            dono_de=None, counts=None, eventos_por_grupo=True):
    """UMA rodada de varredura sobre `roots` (raízes vivas, ou as árvores
    podadas na extensão), particionada por disco, entregue em streaming pelo
    funil `entrega`. Devolve True se parou antes do fim (teto ou cancel).

    `origem_de(path)` marca a árvore podada de cada achado (só na extensão);
    `dono_de(path)` diz a que raiz viva o achado conta; `eventos_por_grupo`
    fecha a narrativa de cada raiz assim que o disco dela termina (na
    extensão o dono é fechado pelo chamador, depois da rodada inteira)."""
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

    grupos = _separa_raizes_com_mortas(_grupos_por_disco(roots), q.excluded_paths)
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
    pendentes = set(roots)
    if paralelo:
        def _grupo_terminou(paths, meu=None):
            # o disco acabou: já dá pra fechar a narrativa dos roots dele, sem
            # esperar os discos lentos (era isso que o iterador serial impedia)
            if not eventos_por_grupo:
                return
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
                jobs=_jobs_para_classe([classes.get(r, "unknown") for r in qq.paths],
                                       conteudo=bool(q.content))),
            ao_fim=_grupo_terminou)
    else:
        it = _fabrica(replace(q, skip_snapshots=_pula_snapshot(roots, q.skip_snapshots)),
                      cancel, stats,
                      jobs=_jobs_para_classe([classes.get(r, "unknown") for r in roots],
                                             conteudo=bool(q.content)))
    parou = False
    for m in it:
        if cancel():
            parou = True
            break
        origem = origem_de(m.path) if origem_de is not None else None
        if entrega.entrega(m, origem):
            d = dono_de(m.path) if dono_de is not None else None
            if d is not None and counts is not None:
                counts[d] = counts.get(d, 0) + 1
        if entrega.parou:
            parou = True
            break
    # Fechar o gerador AQUI, não quando o GC quiser: é no finally dele que o
    # _reap lê o stderr e escreve no funil (e, no particionado, que os stats
    # dos workers são fundidos). Com o `break` acima, sem isto o funil só
    # ficaria completo por acidente de ordem de coleta.
    fechar = getattr(it, "close", None)
    if fechar is not None:
        fechar()
    if eventos_por_grupo:
        for r in roots:                   # F11: no modo particionado a maioria já
            if r in pendentes:            # foi anunciada assim que o disco fechou;
                on_event("root_done", {"path": r, "found": counts[r]})   # aqui sobram
    return parou                          # os interrompidos por cancel/max_results


def _estende_snapshots(q, roots, classes, counts, parou, cancel, stats, on_event,
                       entrega, forca_one_fs, rodada):
    """Segunda rodada: "vivo primeiro, snapshots só se faltar". Decide (e
    anota) com _plano_extensao, varre as árvores podadas com a MESMA
    maquinaria (`rodada` = _rodada ou a do booleano), contando os achados no
    dono e fechando a narrativa dele ao fim. Chamado por search() e por
    search_boolean(): uma mecânica, dois motores."""
    plano = _plano_extensao(q, roots, counts, parou or cancel(), stats, on_event,
                            excluidos=q.excluded_paths)
    if not plano:
        return
    q2 = _query_extensao(q, plano, forca_one_fs)
    origem, dono = _origem_de(plano)
    donos = []
    for a in plano:
        if a["dono"] not in donos:
            donos.append(a["dono"])
    for d in donos:
        prof = classes.get(d, "unknown")
        on_event("root_scanning", {"path": d, "klass": getattr(prof, "klass", prof),
                                   "mountpoint": getattr(prof, "mountpoint", d)})
    classes2 = dict(classes)
    for a in plano:
        classes2[a["arvore"]] = classes.get(a["dono"], "unknown")
    rodada(q2, q2.paths, classes2, cancel, stats, on_event, entrega,
           origem_de=origem, dono_de=dono, counts=counts, eventos_por_grupo=False)
    for d in donos:
        on_event("root_done", {"path": d, "found": counts.get(d, 0)})


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
    09/09/2026: 'snapshots_skipped' / 'snapshots_searched' {path, ostree, trees}
    depois da rodada viva (ver _plano_extensao) e 'copy' {path, of, snapshot}
    por resultado absorvido pelo dedup (ver _Entrega).
    Padrão no-op: chamadores e testes antigos seguem intactos."""
    t0 = time.time()
    classes = {}
    mortas: list = []
    plano, expandidas, forca_one_fs = planejar_raizes(q.paths, q.one_file_system,
                                                      stats, on_event, mortas=mortas)  # F12
    roots = _live_roots(plano, stats, on_event=on_event, classes=classes,
                        expandidas=expandidas, mortas=mortas)
    if not roots:
        return 0, time.time() - t0
    q_digitada = q
    q = _query_planejada(q, roots, forca_one_fs, mortas)
    counts, _attribute = _atribuidor(roots)   # 'found' por root do root_done
    entrega = _Entrega(on_result, on_progress, stats, q.max_results, on_event)

    def _dono_vivo(path):
        # o atribuidor conta; devolvemos None para _rodada não contar de novo
        _attribute(path)
        return None

    # A rodada viva é SEMPRE podada — inclusive com --snapshots: "incluir" agora
    # significa "estender às podadas sem esperar zero", não "varrer tudo junto"
    # (varrer junto misturaria vivo e snapshot na ordem de chegada, e o dedup
    # não teria como dar precedência ao vivo).
    parou = _rodada(replace(q, skip_snapshots=True), roots, classes, cancel, stats,
                    on_event, entrega, dono_de=_dono_vivo, counts=counts)
    # 09/09/2026: vivo primeiro, podadas só se faltar (ou se pedido). A decisão
    # olha a raiz DIGITADA (q_digitada.paths), não as expandidas.
    _estende_snapshots(replace(q, paths=q_digitada.paths, excluded_paths=q.excluded_paths),
                       roots, classes, counts, parou, cancel, stats, on_event,
                       entrega, forca_one_fs, _rodada)
    return entrega.n, time.time() - t0


if __name__ == "__main__":
    # teste rápido de linha de comando
    import sys
    q = Query(paths=[sys.argv[1] if len(sys.argv) > 1 else "."],
              name_patterns=["*.py"], content=sys.argv[2] if len(sys.argv) > 2 else "")
    print("engine:", engine_info())
    tot, dt = search(q, lambda m: print(f"{m.size:>10} {m.path}"
                                        + (f"  [{m.nmatch} matches]" if m.nmatch else "")))
    print(f"\n{tot} resultados em {dt:.2f}s")
