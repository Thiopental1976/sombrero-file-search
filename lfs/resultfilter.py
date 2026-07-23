#!/usr/bin/env python3
"""Filtro DENTRO dos resultados (F10a #1 do desenho do Fable).

"Busca cara uma vez, triagem grátis para sempre." Este módulo é o NÚCLEO puro
da caixa de filtro que fica acima da tabela: compila o texto do usuário num
predicado sobre resultados JÁ carregados (nome, caminho, mtime) — **nunca toca
o disco** (recebe valores, não caminhos; não há syscall possível aqui). A GUI o
liga no `QSortFilterProxyModel` que já existe e mostra o contador vivo
"3.000 → 214"; limpar o filtro restaura tudo sem tocar disco.

Mini-linguagem (deliberadamente pequena — nada além disto):
  * espaço            = E (todos os termos precisam casar)
  * `*.odt` / `.odt`  = extensão (case-insensitive)
  * `>2019-01`        = mtime DEPOIS do período (2019-01 inteiro)
  * `<2020-01`        = mtime ANTES do período
  * qualquer outro    = substring em NOME ou CAMINHO (case-insensitive)
Filtro vazio casa tudo. Termo com cara de data mas inválido cai para substring.
"""
from __future__ import annotations

import datetime
import re
from typing import Callable, List, Optional

# extensão: '.odt' ou '*.odt' (só letras/dígitos após o ponto)
_EXT_RE = re.compile(r"^\*?\.([A-Za-z0-9]+)$")
# data com comparador: '>2019', '<2019-01', '>2019-01-05'
_DATE_RE = re.compile(r"^([<>])(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")

# predicado recebe (nome_basename, caminho, mtime_epoch_ou_None) -> bool
Predicate = Callable[[str, str, Optional[float]], bool]


def _period_bounds(year: int, month: Optional[int], day: Optional[int]):
    """(lo, hi) em epoch para o período nomeado. hi é o instante logo APÓS ele.
    Levanta ValueError se a data for inválida (mês 13, dia 32…)."""
    if month is None:
        lo = datetime.datetime(year, 1, 1)
        hi = datetime.datetime(year + 1, 1, 1)
    elif day is None:
        lo = datetime.datetime(year, month, 1)
        hi = (datetime.datetime(year + 1, 1, 1) if month == 12
              else datetime.datetime(year, month + 1, 1))
    else:
        lo = datetime.datetime(year, month, day)
        hi = lo + datetime.timedelta(days=1)
    return lo.timestamp(), hi.timestamp()


def _date_term(op: str, lo: float, hi: float) -> Predicate:
    if op == ">":                         # depois do período inteiro
        return lambda name, path, mtime: mtime is not None and mtime >= hi
    return lambda name, path, mtime: mtime is not None and mtime < lo   # antes dele


def _ext_term(ext: str) -> Predicate:
    suf = "." + ext.lower()
    return lambda name, path, mtime: name.lower().endswith(suf)


def _substr_term(needle: str) -> Predicate:
    low = needle.lower()
    return lambda name, path, mtime: low in name.lower() or low in path.lower()


def _compile_token(tok: str) -> Predicate:
    m = _DATE_RE.match(tok)
    if m:
        op, y, mo, d = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        try:
            lo, hi = _period_bounds(y, int(mo) if mo else None,
                                    int(d) if d else None)
            return _date_term(op, lo, hi)
        except ValueError:
            pass                          # data inválida → cai para substring
    m = _EXT_RE.match(tok)
    if m:
        return _ext_term(m.group(1))
    return _substr_term(tok)


def compile_filter(text: str) -> Predicate:
    """Compila o texto da caixa num predicado E-de-todos-os-termos. Vazio => tudo."""
    terms: List[Predicate] = [_compile_token(t) for t in text.split()]
    if not terms:
        return lambda name, path, mtime: True
    return lambda name, path, mtime: all(term(name, path, mtime) for term in terms)
