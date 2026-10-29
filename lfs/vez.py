"""A vez do disco físico, compartilhada entre buscas (desenho do Fable, 29/10/2026).

Pedido do Rodrigo: "a segunda busca deve começar assim que os discos estão livres
da primeira (...) nenhum disco fica ocioso em múltiplas buscas". O gate antigo era
por BUSCA (a aba inteira esperava a outra terminar em todos os discos); agora cada
thread-por-disco do engine pede a vez do SEU disco e a solta ao terminar o grupo.

- FIFO por disco: quem pediu antes vai antes, sem prioridade entre abas.
- Grupo que funde discos (VG em 2 PVs) pede o CONJUNTO e só toma com todos livres
  e sendo cabeça em todos — atômico sob uma Condition só, sem ordem de lock e sem
  deadlock. Custo aceito: head-of-line nessa topologia rara.
- `baixa=True` (updatedb do Flash): só toma com o disco livre E a fila vazia —
  nunca passa na frente de uma busca.
- Esperar é cancelável: cancel() é sondado a cada 0,2 s.
Sem Qt e sem disco: puro threading, vale no Windows também."""
from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager


class Cancelado(Exception):
    """cancel() ficou verdadeiro enquanto o ticket esperava a vez."""


class Ticket:
    __slots__ = ("discos", "dono", "t_pedido", "baixa", "solto")

    def __init__(self, discos, dono, baixa):
        self.discos, self.dono, self.baixa = frozenset(discos), dono, baixa
        self.t_pedido = time.time()
        self.solto = False

    def __repr__(self):
        return "Ticket(%r, %s)" % (self.dono, sorted(map(str, self.discos)))


_COND = threading.Condition()
_DONO: dict = {}          # disco -> Ticket que o segura agora
_FILA: dict = {}          # disco -> deque[Ticket], FIFO


def discos_de(chave) -> frozenset:
    """Chave de `engine._chave_de_disco` -> conjunto de discos que ela ocupa.
    ("?", root) = stat falhou: não há disco a proteger."""
    if not isinstance(chave, tuple) or len(chave) != 2:
        return frozenset([chave])
    tipo, val = chave
    if tipo == "?":
        return frozenset()
    if tipo == "disco" and isinstance(val, frozenset):
        return val
    return frozenset([chave])


def _pode(tk) -> bool:
    for d in tk.discos:
        if d in _DONO:
            return False
        fila = _FILA.get(d)
        if tk.baixa:
            if fila:                     # baixa: ninguém pode estar esperando
                return False
        elif not fila or fila[0] is not tk:
            return False
    return True


def _sai_da_fila(tk):
    for d in tk.discos:
        fila = _FILA.get(d)
        if fila is not None:
            try:
                fila.remove(tk)
            except ValueError:
                pass
            if not fila:
                del _FILA[d]


def soltar(tk):
    """Solta o que o ticket segura (ou desiste da fila). Idempotente: o consumidor
    do engine pode soltar à força um worker preso, e o finally dele solta de novo."""
    with _COND:
        if tk.solto:
            return
        tk.solto = True
        _sai_da_fila(tk)
        for d in tk.discos:
            if _DONO.get(d) is tk:
                del _DONO[d]
        _COND.notify_all()


def pedir(discos, dono="", cancel=None, on_espera=None, baixa=False,
          _sleep=0.2, espera_min_s=0.1) -> Ticket:
    """Bloqueia até tomar a vez de todos os `discos`. Devolve o Ticket (soltar com
    `soltar`). `on_espera(ticket, quem_segura, posicao)` é chamado UMA vez, se a
    espera passar de `espera_min_s` (sem ruído na narrativa para esperas curtas).
    Levanta Cancelado se cancel() ficar verdadeiro na espera."""
    tk = Ticket(discos, dono, baixa)
    if not tk.discos:
        return tk
    avisado = False
    with _COND:
        if not baixa:
            for d in tk.discos:
                _FILA.setdefault(d, deque()).append(tk)
        while not _pode(tk):
            if cancel is not None and cancel():
                tk.solto = True
                _sai_da_fila(tk)
                _COND.notify_all()
                raise Cancelado()
            if (not avisado and on_espera is not None
                    and time.time() - tk.t_pedido >= espera_min_s):
                avisado = True
                d = next(iter(tk.discos))
                quem = _DONO.get(d) or next(iter(_FILA.get(d) or ()), None)
                pos = posicao(tk, d)
                _COND.release()           # o callback emite sinal Qt: fora do lock
                try:
                    on_espera(tk, quem, pos)
                finally:
                    _COND.acquire()
                continue
            _COND.wait(_sleep)
        _sai_da_fila(tk)
        for d in tk.discos:
            _DONO[d] = tk
    return tk


@contextmanager
def vez(discos, dono="", cancel=None, on_espera=None, baixa=False, _sleep=0.2):
    tk = pedir(discos, dono, cancel, on_espera, baixa, _sleep)
    try:
        yield tk
    finally:
        soltar(tk)


def quem_segura(disco):
    with _COND:
        return _DONO.get(disco)


def posicao(tk, disco) -> int:
    """1 = o próximo a tomar o disco. 0 = não está na fila desse disco."""
    fila = _FILA.get(disco) or ()
    for i, x in enumerate(fila):
        if x is tk:
            return i + 1
    return 0


def ocupados() -> dict:
    """Retrato p/ testes e log: {disco: dono}, {disco: [donos na fila]}."""
    with _COND:
        return ({d: t.dono for d, t in _DONO.items()},
                {d: [t.dono for t in f] for d, f in _FILA.items()})


def _reset():
    with _COND:
        _DONO.clear(); _FILA.clear(); _COND.notify_all()
