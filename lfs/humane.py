#!/usr/bin/env python3
"""Mensagens de erro humanas para a GUI (F10b #6 do desenho do Fable).

Regra de projeto: **toda** string de erro que alcança a tela do usuário passa
por `human_error()`. O usuário nunca vê um errno cru, um `strerror` do sistema
ou o texto de uma exceção Python. O detalhe técnico (errno/strerror) continua
disponível para o log e para o `--json` — máquina gosta dele; gente, não.

O desenho: mapear um `OSError` / errno / exceção genérica para UMA frase curta e
calma, traduzida via `i18n.t()`. Opcionalmente nomear o alvo (um nome de
arquivo) e o que o programa estava fazendo (`context`), para a mensagem ficar
concreta sem ficar técnica.

    "ENOTCONN"  ->  "O local de rede parou de responder. A busca continuou nos
                     demais locais."

Fonte é inglês (convenção do i18n): as strings-fonte aqui são em inglês e as
traduções vivem no `_PT` do i18n.py.
"""
from __future__ import annotations

import errno as _errno

import i18n

t = i18n.t


# --- baldes de errno -> categoria estável --------------------------------
# Cada balde vira UMA frase-fonte (traduzida). Agrupar por errno mantém a
# lista de traduções pequena e a mensagem previsível.
_NETWORK = frozenset({
    _errno.ENOTCONN, _errno.EHOSTDOWN, _errno.EHOSTUNREACH,
    _errno.ENETUNREACH, _errno.ENETDOWN, _errno.ENETRESET,
    _errno.ECONNREFUSED, _errno.ECONNRESET, _errno.ECONNABORTED,
    _errno.ETIMEDOUT, _errno.ESTALE,
})
_PERMISSION = frozenset({_errno.EACCES, _errno.EPERM})
_MISSING    = frozenset({_errno.ENOENT})
_NO_SPACE   = frozenset({_errno.ENOSPC, getattr(_errno, "EDQUOT", _errno.ENOSPC)})
_READ_ONLY  = frozenset({_errno.EROFS})
_NAME_LONG  = frozenset({_errno.ENAMETOOLONG})
_MEDIA      = frozenset({_errno.EIO})
_BUSY       = frozenset({_errno.EBUSY, _errno.ETXTBSY})
_TOO_MANY   = frozenset({_errno.EMFILE, _errno.ENFILE})
_EXISTS     = frozenset({_errno.EEXIST})
_IS_DIR     = frozenset({_errno.EISDIR})
_NOT_DIR    = frozenset({_errno.ENOTDIR})
_LOOP       = frozenset({_errno.ELOOP})

# Ordem de teste -> (categoria, frase-fonte em inglês).
_BUCKETS = (
    (_NETWORK,    "network", "The network location stopped responding."),
    (_PERMISSION, "file",    "No permission to read this."),
    (_MISSING,    "file",    "This item no longer exists."),
    (_NO_SPACE,   "space",   "The destination ran out of space."),
    (_READ_ONLY,  "file",    "The destination is read-only."),
    (_NAME_LONG,  "file",    "The name is too long for the destination."),
    (_MEDIA,      "file",    "Read/write error — the disk may be failing."),
    (_BUSY,       "file",    "The file is in use by another program."),
    (_TOO_MANY,   "file",    "Too many files are open at once — try again in a moment."),
    (_EXISTS,     "file",    "A file with this name already exists."),
    (_IS_DIR,     "file",    "This is a folder, not a file."),
    (_NOT_DIR,    "file",    "Part of this path is not a folder."),
    (_LOOP,       "file",    "There are too many symbolic links in this path."),
)

_GENERIC = "The operation could not be completed."

# Cláusula de contexto: o que o programa estava fazendo. Chave (context, cat).
_CLAUSES = {
    ("search", "network"): "The search continued in the other locations.",
    ("search", "space"):   "This item was skipped.",
    ("search", "file"):    "This item was skipped.",
    ("copy",   "network"): "This file was not copied.",
    ("copy",   "space"):   "The copy stopped.",
    ("copy",   "file"):    "This file was skipped.",
    ("mount",  "network"): "This location was skipped.",
    ("mount",  "space"):   "This location was skipped.",
    ("mount",  "file"):    "This location was skipped.",
}


# Todas as strings-fonte (inglês) que este módulo entrega a t(). Derivada dos
# dados acima para não divergir deles — a guarda de i18n consome esta lista.
SOURCE_STRINGS = frozenset(
    [phrase for _members, _cat, phrase in _BUCKETS]
    + [_GENERIC]
    + list(_CLAUSES.values())
)


def _to_errno(err):
    """int -> ele mesmo; OSError -> .errno; qualquer outra coisa -> None."""
    if isinstance(err, bool):            # bool é int; nunca é um errno
        return None
    if isinstance(err, int):
        return err
    if isinstance(err, OSError):
        return err.errno
    return None


def _lookup(code):
    """errno -> (categoria, frase-fonte). Desconhecido -> ('file', genérico)."""
    for members, cat, phrase in _BUCKETS:
        if code in members:
            return cat, phrase
    return "file", _GENERIC


def human_error(err, context: str = "", target: str = "") -> str:
    """Transforma erro/errno/exceção em uma frase humana traduzida.

    err     : OSError | int(errno) | Exception | None
    context : "search" | "copy" | "mount" | ""  (o que o programa fazia)
    target  : nome curto do alvo (basename de um arquivo), opcional

    Nunca devolve errno, strerror ou repr técnico. Exceções de domínio
    (não-OSError) já vêm com texto humano do próprio SFS e passam direto.
    """
    code = _to_errno(err)

    if code is None:
        if isinstance(err, OSError):
            # OSError sem errno utilizável -> não vaza o str() (traz "[Errno..]").
            return _decorate(t(_GENERIC), target, "file", context)
        text = str(err).strip() if err is not None else ""
        return _decorate(text or t(_GENERIC), target, None, context)

    cat, phrase = _lookup(code)
    return _decorate(t(phrase), target, cat, context)


def _decorate(base: str, target: str, cat, context: str) -> str:
    """Prefixa o alvo ("arquivo.txt: …") e anexa a cláusula de contexto."""
    msg = base
    if target:
        msg = "%s: %s" % (target, msg)
    if cat and context:
        clause = _CLAUSES.get((context, cat))
        if clause:
            msg = "%s %s" % (msg, t(clause))
    return msg
