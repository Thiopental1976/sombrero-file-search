"""Barra de progresso por disco (24/10/2026, pedido do Rodrigo; desenho Fable).

O fd e o rg só falam dos ACHADOS: nenhum dos dois diz quantos arquivos já
percorreu, e listar tudo para contar em Python custaria 10–20 % da busca fria
e mudaria o casador (paridade). Então a barra é uma ESTIMATIVA honesta:

    fração = trabalho já feito / trabalho da última passagem COMPLETA aqui

"Trabalho" = tempo de CPU do processo-motor (utime+stime, mais o dos filhos
que ele já colheu — o rga roda o rg como filho). CPU, e não relógio: o relógio
varia 30× entre cache fria e quente, com a Coleção disputando o prato e com a
fragmentação; a CPU por entrada é quase constante. Quando o SMR engasga, a
barra PARA — que é a verdade.

Por que CPU também na busca de conteúdo (o desenho pedia `rchar`): medido em
24/10, o /proc/<pid>/io de um processo zumbi dá EACCES, então o total final de
bytes não é legível no fim; e o `summary` do rg vem com bytes_searched=0 sem
--stats (mudar a linha de comando está fora de questão). O /proc/<pid>/stat
do zumbi é legível — o total de CPU fecha certo. Os bytes ficam só para o
"MB/s" da linha, que é número real, não estimativa.

Sem histórico → fração None ("primeira passagem aqui", barra indeterminada).
Passou do histórico → fração None ("além da última passagem"). Nunca 100 %
sem a passagem ter terminado: quem diz "terminou" é o root_done(completo).

Módulo puro, sem Qt: testável com um /proc falso (`base`) e um kernel32 falso.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Callable, Optional

try:                       # pacote (GUI) e flat (cli.py/testes)
    from . import plat
except ImportError:
    import plat                                  # type: ignore

INTERVALO = 0.5          # emissão por processo (2 Hz); o tick pode vir mais rápido
MAX_CHAVES = 400         # teto do histórico (LRU pelo 'quando')
_HIST_LOCK = threading.Lock()


# ------------------------------------------------------------------ histórico
def _arq_historia() -> str:
    return os.path.join(plat.cache_dir(), "progresso.json")


def historia_carrega(arq: Optional[str] = None) -> dict:
    """JSON corrompido ou ausente → {} (é cache: descartável, nunca erro)."""
    arq = arq or _arq_historia()
    try:
        with open(arq, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def historia_grava(chave: str, rec: dict, arq: Optional[str] = None) -> None:
    """Escrita atômica (tmp + os.replace), com teto de MAX_CHAVES por LRU.
    Falha de disco é engolida: perder o histórico só tira a barra da próxima."""
    arq = arq or _arq_historia()
    with _HIST_LOCK:
        d = historia_carrega(arq)
        rec = dict(rec)
        rec["quando"] = time.time()
        d[chave] = rec
        if len(d) > MAX_CHAVES:
            velhas = sorted(d, key=lambda k: (d[k] or {}).get("quando", 0))
            for k in velhas[:len(d) - MAX_CHAVES]:
                d.pop(k, None)
        try:
            os.makedirs(os.path.dirname(arq), exist_ok=True)
            tmp = f"{arq}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, arq)
        except OSError:
            try:
                os.unlink(tmp)
            except (OSError, UnboundLocalError):
                pass


def chave_de(roots, q, modo: str) -> str:
    """Identidade da TRAVESSIA. No modo nome o padrão NÃO entra (a caminhada é
    a mesma para *.mkv e *.odt — é isso que dá barra a buscas diferentes); no
    conteúdo entram os globs e o modo documentos, que mudam o que é lido."""
    partes = [sorted(roots), modo, q.include_hidden, q.respect_gitignore,
              q.follow_symlinks, q.one_file_system, q.max_depth, q.recursive,
              q.skip_snapshots, sorted(q.excluded_paths or ())]
    if modo not in ("nome", "py_nome"):
        partes += [list(q.name_patterns or ()), q.name_is_regex,
                   q.case_sensitive, q.documents]
    bruto = json.dumps(partes, ensure_ascii=False, default=str)
    return hashlib.sha1(bruto.encode("utf-8", "surrogateescape")).hexdigest()[:16]


TOLERANCIA = 1.15       # medido 24/10: a mesma passagem varia ~10 % de CPU


def estima(feito: float, meta: Optional[float]):
    """(fração|None, estado). estado ∈ sem_historico / estimado / alem.
    Entre a meta e TOLERANCIA×meta a barra segura em 99 % — sem isso, a
    variação natural de uma passagem para a outra jogava quase toda busca
    para "além da última passagem" bem no finzinho."""
    if not meta or meta <= 0:
        return None, "sem_historico"
    if feito > meta * TOLERANCIA:
        return None, "alem"
    return min(feito / meta, 0.99), "estimado"


# ------------------------------------------------------- leitura do processo
_TICK = None


def _clk() -> float:
    global _TICK
    if _TICK is None:
        try:
            _TICK = float(os.sysconf("SC_CLK_TCK"))
        except (ValueError, OSError, AttributeError):
            _TICK = 100.0
    return _TICK


def _filhos_linux(pid, base):
    out = []
    try:
        for tid in os.listdir(f"{base}/{pid}/task"):
            try:
                with open(f"{base}/{pid}/task/{tid}/children") as f:
                    out += [int(x) for x in f.read().split()]
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    return out


def _cpu_um(pid, base):
    """utime+stime+cutime+cstime em segundos (cutime = filhos já colhidos)."""
    with open(f"{base}/{pid}/stat") as f:
        campos = f.read().rsplit(")", 1)[1].split()
    # depois do ')' : [0]=estado ... [11]=utime [12]=stime [13]=cutime [14]=cstime
    return sum(int(campos[i]) for i in (11, 12, 13, 14)) / _clk()


def le_cpu_linux(pid, base="/proc") -> Optional[float]:
    """CPU do processo + dos descendentes VIVOS (os colhidos já estão no
    cutime de quem colheu). None se o processo sumiu."""
    try:
        total = _cpu_um(pid, base)
    except (OSError, ValueError, IndexError):
        return None
    pilha, vistos = _filhos_linux(pid, base), {pid}
    while pilha:
        c = pilha.pop()
        if c in vistos:
            continue
        vistos.add(c)
        try:
            total += _cpu_um(c, base)
        except (OSError, ValueError, IndexError):
            continue
        pilha += _filhos_linux(c, base)
    return total


def le_io_linux(pid, base="/proc"):
    """(rchar, read_bytes) do processo, ou None (zumbi dá EACCES)."""
    try:
        with open(f"{base}/{pid}/io") as f:
            d = dict(l.split(":", 1) for l in f.read().splitlines() if ":" in l)
        return int(d["rchar"]), int(d["read_bytes"])
    except (OSError, ValueError, KeyError):
        return None


def pasta_atual_linux(pid, roots, base="/proc") -> Optional[str]:
    """O caminho mais fundo, sob uma das raízes, entre os fds abertos do motor:
    é a pasta (ou o arquivo, no rg) que ele está lendo AGORA. Arquivo → a pasta."""
    melhor = None
    try:
        fds = os.listdir(f"{base}/{pid}/fd")
    except OSError:
        return None
    raizes = [r.rstrip("/") or "/" for r in roots]
    for fd in fds:
        try:
            alvo = os.readlink(f"{base}/{pid}/fd/{fd}")
        except OSError:
            continue
        if not alvo.startswith("/"):
            continue
        if not any(alvo == r or alvo.startswith(r if r == "/" else r + "/") for r in raizes):
            continue
        if melhor is None or len(alvo) > len(melhor):
            melhor = alvo
    if melhor and not os.path.isdir(melhor):
        melhor = os.path.dirname(melhor)
    return melhor


# Windows: GetProcessTimes / GetProcessIoCounters pelo handle que o Popen já
# segura (vale mesmo depois de o processo sair — o handle mantém os contadores)
_k32 = None


def _kernel32():
    global _k32
    if _k32 is None:
        import ctypes
        _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    return _k32


def le_cpu_win(handle) -> Optional[float]:
    try:
        import ctypes
        from ctypes import wintypes
        k = _kernel32()
        c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
        if not k.GetProcessTimes(wintypes.HANDLE(int(handle)), ctypes.byref(c),
                                 ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
            return None
        ft = lambda x: (x.dwHighDateTime << 32 | x.dwLowDateTime) / 1e7
        return ft(kt) + ft(ut)
    except Exception:
        return None


def le_io_win(handle):
    try:
        import ctypes
        from ctypes import wintypes

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        io = IO()
        if not _kernel32().GetProcessIoCounters(wintypes.HANDLE(int(handle)), ctypes.byref(io)):
            return None
        return int(io.ReadTransferCount), None     # sem "bytes do disco" no Windows
    except Exception:
        return None


# --------------------------------------------------------------------- sonda
class Sonda:
    """Uma por iterador-motor (um disco/grupo). `processo(p)` aponta o processo
    da vez (o fd com padrões não fundidos roda um por padrão, em sequência — a
    CPU se acumula); `tick()` lê e emite no máximo a cada INTERVALO; `soma(n)`
    é o modo contador dos fallbacks Python (sem processo). `fecha(completo)`
    grava o histórico SÓ se a passagem foi inteira.

    Tudo à prova de exceção: um bug aqui jamais pode atrapalhar busca ou
    cancelamento — o pior caso é a linha ficar sem barra."""

    def __init__(self, roots, chave: str, modo: str, emitir: Callable[[dict], None],
                 historia: Optional[dict] = None, base: str = "/proc",
                 relogio: Callable[[], float] = time.monotonic, arq: Optional[str] = None):
        self.roots, self.chave, self.modo, self.emitir = list(roots), chave, modo, emitir
        h = (historia if historia is not None else historia_carrega(arq)).get(chave) or {}
        self.meta = h.get("trabalho")
        self.base, self.relogio, self.arq = base, relogio, arq
        self.lock = threading.Lock()
        self.proc = None
        self.acum = 0.0          # trabalho dos processos anteriores (sequência)
        self.atual = 0.0         # trabalho do processo da vez (última leitura boa)
        self.contador = 0        # modo soma()
        self.bytes_ant = None    # (t, rchar, read_bytes) p/ as taxas
        self.taxa = self.disco = None
        self.pasta = None
        self.n_ticks = 0
        self.ult_emit = None
        self.t0 = relogio()
        self.fechada = False

    # -- leitura
    def _le(self):
        p = self.proc
        if p is None:
            return
        if plat.IS_WIN:
            h = getattr(p, "_handle", None)
            cpu = le_cpu_win(h) if h is not None else None
            io = le_io_win(h) if h is not None else None
        else:
            cpu = le_cpu_linux(p.pid, self.base)
            io = le_io_linux(p.pid, self.base)
        if cpu is not None and cpu >= self.atual:
            self.atual = cpu
        if io is not None:
            agora = self.relogio()
            if self.bytes_ant is not None:
                t_a, r_a, d_a = self.bytes_ant
                dt = agora - t_a
                if dt >= 1.0:          # janela de ≥1 s: taxa sem serrilhado
                    self.taxa = max(0.0, (io[0] - r_a) / dt)
                    self.disco = (max(0.0, (io[1] - d_a) / dt)
                                  if io[1] is not None and d_a is not None else None)
                    self.bytes_ant = (agora, io[0], io[1])
            else:
                self.bytes_ant = (agora, io[0], io[1])
        if not plat.IS_WIN and self.n_ticks % 2 == 0:
            pasta = pasta_atual_linux(p.pid, self.roots, self.base)
            if pasta:
                self.pasta = pasta

    def feito(self) -> float:
        return self.acum + self.atual + self.contador

    def processo(self, p):
        """Troca o processo da vez; o trabalho do anterior vira acumulado."""
        with self.lock:
            try:
                if self.proc is not None:
                    self._le()
                    self.acum += self.atual
                self.proc, self.atual, self.bytes_ant = p, 0.0, None
            except Exception:
                pass

    def soma(self, n: int = 1):
        self.contador += n          # só a thread do iterador mexe: sem lock
        self.tick()

    def tick(self, forca: bool = False):
        try:
            with self.lock:
                if self.fechada:
                    return
                agora = self.relogio()
                if not forca and self.ult_emit is not None and agora - self.ult_emit < INTERVALO:
                    return
                self._le()
                self.n_ticks += 1
                self.ult_emit = agora
                info = self._info(agora)
            self.emitir(info)
        except Exception:
            pass

    def _info(self, agora):
        feito = self.feito()
        frac, estado = estima(feito, self.meta)
        return {"paths": list(self.roots), "modo": self.modo, "frac": frac,
                "estado": estado, "trabalho": feito, "meta": self.meta,
                "taxa_bps": self.taxa, "disco_bps": self.disco, "pasta": self.pasta,
                "decorrido": agora - self.t0}

    def fecha(self, completo: bool):
        """Última leitura (o zumbi ainda tem /proc/<pid>/stat) e, se a passagem
        foi inteira, o histórico. Idempotente."""
        try:
            with self.lock:
                if self.fechada:
                    return
                self._le()
                self.fechada = True
                feito = self.feito()
            if completo and feito > 0:
                historia_grava(self.chave, {"trabalho": feito, "modo": self.modo,
                                            "parede_s": round(self.relogio() - self.t0, 2)},
                               self.arq)
        except Exception:
            pass


def nova_sonda(progresso, q, modo: str):
    """Fábrica usada pelos iteradores do motor: None se ninguém pediu progresso."""
    if progresso is None:
        return None
    try:
        return Sonda(q.paths, chave_de(q.paths, q, modo), modo, progresso)
    except Exception:
        return None
