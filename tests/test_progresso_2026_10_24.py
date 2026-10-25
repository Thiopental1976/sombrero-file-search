"""Barra de progresso por disco (24/10/2026, pedido do Rodrigo; desenho Fable).

Trava:
  1. leitura do /proc (falso): CPU soma utime+stime+cutime+cstime e os filhos
     vivos; processo sumido -> None; pasta atual = o fd mais fundo sob a raiz
  2. estima(): sem histórico / estimado / tolerância de 15 % (segura em 99 %) / além
  3. histórico: ida e volta, JSON corrompido -> {}, teto LRU
  4. chave_de: no modo nome o padrão NÃO entra; no conteúdo entra; ordem das raízes não importa
  5. Sonda: emite no máximo a cada INTERVALO; só grava com passagem completa
  6. motor de verdade (fd/rg ou fallback): 1ª passagem sem histórico, 2ª estimada;
     root_done.completo True; cancelado / teto de resultados -> completo False e
     NADA gravado; fallback Python conta entradas exatas
  7. Windows: kernel32 falso que falha -> None, nunca exceção
  8. GUI offscreen: 100 % só com completo; parado (cancel) não vai a 100;
     busca booleana sem barra

Rode com o Python do venv do app:
    ~/.local/share/sombrero-file-search/venv/bin/python tests/test_progresso_2026_10_24.py
"""
from __future__ import annotations
import json, os, sys, tempfile, time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="sfs-test-prog-")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sfs-test-prog-")
# no Windows o cache é %LOCALAPPDATA% (plat.cache_base): sem isto o teste lia o
# histórico deixado pelas outras suítes do CI (visto 25/10: 30300 -> 11.0)
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="sfs-test-prog-")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="sfs-test-prog-")

import progresso as P
import engine as E
import plat

falhas = []


def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)


# ------------------------------------------------------------ 1. /proc falso
def proc_falso():
    base = tempfile.mkdtemp(prefix="sfs-proc-")
    raiz = tempfile.mkdtemp(prefix="sfs-raiz-")
    os.makedirs(os.path.join(raiz, "a", "b", "c"))
    tick = P._clk()

    def processo(pid, ut, st, cut, cst, filhos=(), fds=()):
        d = os.path.join(base, str(pid))
        os.makedirs(os.path.join(d, "task", str(pid)))
        os.makedirs(os.path.join(d, "fd"))
        campos = ["S"] + ["0"] * 10 + [str(int(x * tick)) for x in (ut, st, cut, cst)] + ["0"] * 5
        with open(os.path.join(d, "stat"), "w") as f:
            f.write(f"{pid} (fd com espaço) " + " ".join(campos))
        with open(os.path.join(d, "task", str(pid), "children"), "w") as f:
            f.write(" ".join(str(c) for c in filhos))
        with open(os.path.join(d, "io"), "w") as f:
            f.write("rchar: 5000000\nwchar: 0\nread_bytes: 4096\n")
        for i, alvo in enumerate(fds):
            os.symlink(alvo, os.path.join(d, "fd", str(i + 3)))

    processo(100, 1.0, 0.5, 0.25, 0.25, filhos=(101,),
             fds=("/dev/null", raiz, os.path.join(raiz, "a", "b"), "/tmp"))
    processo(101, 0.5, 0.5, 0, 0)
    return base, raiz


base, raiz = proc_falso()
cpu = P.le_cpu_linux(100, base)
ok(cpu is not None and abs(cpu - 3.0) < 0.05, f"CPU = processo (2,0) + filho vivo (1,0) = 3,0 s ({cpu})")
ok(P.le_cpu_linux(999, base) is None, "processo sumido -> None")
ok(P.le_io_linux(100, base) == (5000000, 4096), "io: (rchar, read_bytes)")
if not plat.IS_WIN:              # symlink de /proc/<pid>/fd: coisa de Linux
    ok(P.pasta_atual_linux(100, [raiz], base) == os.path.join(raiz, "a", "b"),
       "pasta atual = o fd mais fundo sob a raiz (ignora /dev/null e /tmp)")

# ------------------------------------------------------------ 2. estima
ok(P.estima(5, None) == (None, "sem_historico"), "sem histórico")
f, e = P.estima(5, 10)
ok(e == "estimado" and abs(f - 0.5) < 1e-9, "metade do trabalho = 50 %")
ok(P.estima(11, 10) == (0.99, "estimado"), "até 15 % acima do histórico segura em 99 %")
ok(P.estima(12, 10)[1] == "alem" and P.estima(12, 10)[0] is None, "acima da tolerância = além (indeterminada)")

# ------------------------------------------------------------ 3. histórico
arq = os.path.join(tempfile.mkdtemp(), "sub", "progresso.json")
P.historia_grava("k1", {"trabalho": 2.5}, arq)
ok(P.historia_carrega(arq)["k1"]["trabalho"] == 2.5, "histórico: ida e volta (cria a pasta)")
with open(arq, "w") as fh:
    fh.write("{lixo")
ok(P.historia_carrega(arq) == {}, "JSON corrompido -> {} sem erro")
velho = P.MAX_CHAVES
P.MAX_CHAVES = 3
try:
    for i in range(5):
        P.historia_grava(f"c{i}", {"trabalho": i}, arq)
        time.sleep(0.002)
    d = P.historia_carrega(arq)
    ok(sorted(d) == ["c2", "c3", "c4"], f"teto LRU mantém as mais novas ({sorted(d)})")
finally:
    P.MAX_CHAVES = velho
ok(not [n for n in os.listdir(os.path.dirname(arq)) if n.endswith(".tmp")], "nenhum .tmp sobrando")

# ------------------------------------------------------------ 4. chave
qa = E.Query(paths=["/a", "/b"], name_patterns=["*.mkv"])
qb = E.Query(paths=["/b", "/a"], name_patterns=["*.odt"])
ok(P.chave_de(qa.paths, qa, "nome") == P.chave_de(qb.paths, qb, "nome"),
   "nome: padrão e ordem das raízes não mudam a chave")
qc = E.Query(paths=["/a"], name_patterns=["*.txt"], content="x")
qd = E.Query(paths=["/a"], name_patterns=["*.md"], content="x")
ok(P.chave_de(qc.paths, qc, "conteudo") != P.chave_de(qd.paths, qd, "conteudo"),
   "conteúdo: os globs mudam o que é lido -> chave diferente")
qe = E.Query(paths=["/a"], include_hidden=True)
ok(P.chave_de(["/a"], qe, "nome") != P.chave_de(["/a"], E.Query(paths=["/a"]), "nome"),
   "ocultos mudam a travessia -> chave diferente")


# ------------------------------------------------------------ 5. Sonda
class Rel:
    t = 0.0

    def __call__(self):
        return self.t


class ProcF:
    pid = 100
    _handle = None


_leitores_win = (P.le_cpu_win, P.le_io_win)
if plat.IS_WIN:
    # a sonda lê pelo kernel32 no Windows, não pelo /proc falso: o mesmo
    # processo (3,0 s de CPU) servido pelos leitores do Windows
    ProcF._handle = object()
    P.le_cpu_win = lambda h: 3.0
    P.le_io_win = lambda h: None


rel = Rel()
emit = []
arq2 = os.path.join(tempfile.mkdtemp(), "p.json")
s = P.Sonda([raiz], "kz", "nome", emit.append, historia={"kz": {"trabalho": 6.0}},
            base=base, relogio=rel, arq=arq2)
s.processo(ProcF())
s.tick()
s.tick()                       # mesmo instante: não emite de novo
rel.t = 0.6
s.tick()
ok(len(emit) == 2, f"emite no máximo a cada {P.INTERVALO}s ({len(emit)} emissões)")
ok(abs(emit[-1]["frac"] - 0.5) < 0.01 and emit[-1]["estado"] == "estimado",
   f"3,0 s de 6,0 s = 50 % ({emit[-1]['frac']})")
if not plat.IS_WIN:              # o Windows não mostra a pasta (sem /proc)
    ok(emit[-1]["pasta"] == os.path.join(raiz, "a", "b"), "a emissão leva a pasta atual")
s.fecha(False)
ok(not os.path.exists(arq2), "passagem cortada NÃO grava histórico")
s2 = P.Sonda([raiz], "kz", "nome", emit.append, historia={}, base=base, relogio=rel, arq=arq2)
s2.processo(ProcF())
s2.fecha(True)
ok(P.historia_carrega(arq2).get("kz", {}).get("trabalho") == 3.0, "passagem completa grava o trabalho medido")
n = len(emit)
s2.tick(forca=True)
ok(len(emit) == n, "sonda fechada não emite mais")


def explode(info):
    raise RuntimeError("bug no consumidor")


s3 = P.Sonda([raiz], "kx", "nome", explode, historia={}, base=base, relogio=rel, arq=arq2)
s3.processo(ProcF())
try:
    s3.tick(forca=True)
    ok(True, "exceção no consumidor não escapa da sonda")
except Exception:
    ok(False, "exceção no consumidor não escapa da sonda")
P.le_cpu_win, P.le_io_win = _leitores_win     # o motor de verdade lê o kernel32 real


# ------------------------------------------------------------ 6. motor de verdade
arvore = tempfile.mkdtemp(prefix="sfs-arvore-")
for i in range(300):            # grande o bastante para o motor gastar CPU mensurável
    d = os.path.join(arvore, f"d{i}")
    os.makedirs(d)
    for j in range(100):
        with open(os.path.join(d, f"f{j}.txt"), "w") as fh:
            fh.write("agulha\n" if j == 7 else "palha\n")


def roda(q, cancel=lambda: False):
    evs = []
    E.search(q, lambda m: None, cancel=cancel, on_event=lambda ev, i: evs.append((ev, dict(i))))
    return ([i for ev, i in evs if ev == "root_progress"],
            [i for ev, i in evs if ev == "root_done"])


def chave_motor(q, modo):
    return P.chave_de(q.paths, q, modo)


for rotulo, q, modo in (
        ("nome", E.Query(paths=[arvore], name_patterns=["f7.txt"]), "nome"),
        ("conteúdo", E.Query(paths=[arvore], content="agulha"), "conteudo")):
    ativo = (E.FD if modo == "nome" else E.RG)
    if not ativo:
        modo = "py_nome" if modo == "nome" else "py_conteudo"
    pr1, dn1 = roda(q)
    ok(pr1 and pr1[0]["estado"] == "sem_historico", f"{rotulo}: 1ª passagem sem histórico")
    ok(dn1 and dn1[0].get("completo") is True, f"{rotulo}: root_done completo")
    h = P.historia_carrega()
    ok(any(v.get("modo") == modo for v in h.values()),
       f"{rotulo}: passagem completa entrou no histórico ({modo})")
    pr2, _ = roda(q)
    ok(pr2 and pr2[-1]["meta"] is not None and pr2[-1]["paths"] == [arvore],
       f"{rotulo}: 2ª passagem tem meta, e a barra é da raiz digitada")

# cancelado: nada gravado, completo False
qn = E.Query(paths=[arvore], name_patterns=["*.nada"], max_depth=3)
antes = P.historia_carrega()
_, dnc = roda(qn, cancel=lambda: True)
ok(not dnc or dnc[0].get("completo") is False, "cancelado: root_done.completo False")
ok(P.historia_carrega() == antes, "cancelado: histórico intocado")
antes = P.historia_carrega()

# teto de resultados: cortado não é completo
qt = E.Query(paths=[arvore], name_patterns=["*.txt"], max_results=5, include_hidden=True)
_, dnt = roda(qt)
ok(dnt and dnt[0].get("completo") is False, "teto de resultados: completo False (a barra não vai a 100)")
ok(P.historia_carrega() == antes, "teto de resultados: não grava histórico")

# regressão 24/10: na rodada viva, perguntar o dono a cada tick da barra CONTAVA
# um achado (o _dono_vivo atribui) — o placar inflava e "vivo zero" virava
# "vivo com achado", matando a extensão aos snapshots. A emissão final é forçada,
# então mesmo uma busca curta passa por ela.
for rotulo, extra in (("nome", {}), ("conteúdo", {"content": "agulha"})):
    qz = E.Query(paths=[arvore], name_patterns=["nao_existe_*.txt"], **extra)
    evs = []
    nz, _dt = E.search(qz, lambda m: None, on_event=lambda ev, i: evs.append((ev, dict(i))))
    prz = [i for ev, i in evs if ev == "root_progress"]
    dnz = [i for ev, i in evs if ev == "root_done"]
    ok(prz and nz == 0 and dnz and dnz[0]["found"] == 0,
       f"{rotulo}: a barra não infla o placar (0 achados continuam 0: {dnz and dnz[0]['found']})")

# fallback Python: contagem EXATA de entradas (40 pastas + 40×60 arquivos)
fd_salvo = E.FD
E.FD = None
try:
    qp = E.Query(paths=[arvore], name_patterns=["f7.txt"], respect_gitignore=True)
    roda(qp)
    h = [v for v in P.historia_carrega().values() if v.get("modo") == "py_nome"]
    ok(h and h[0]["trabalho"] == 300 + 300 * 100,
       f"fallback Python: conta {300 + 300 * 100} entradas exatas ({h and h[0]['trabalho']})")
finally:
    E.FD = fd_salvo


# ------------------------------------------------------------ 7. Windows
class K32Falha:
    def GetProcessTimes(self, *a):
        return 0

    def GetProcessIoCounters(self, *a):
        raise OSError("sem kernel32")


P._k32 = K32Falha()
try:
    ok(P.le_cpu_win(123) is None, "Windows: GetProcessTimes falhou -> None")
    ok(P.le_io_win(123) is None, "Windows: GetProcessIoCounters explodiu -> None")
finally:
    P._k32 = None


# ------------------------------------------------------------ 8. GUI
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("--  GUI: pulado (sem PySide6)")
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import app as A
    qapp = QApplication.instance() or QApplication([])
    w = A.MainWindow()
    w.cfg.setdefault("updates", {})["auto"] = False
    tab = w.tabs.currentWidget()
    tab.t0 = time.time()
    tab.worker = None
    w._reset_narrative(tab)
    w._on_root_event(tab, "root_scanning", {"path": "/mnt/X", "klass": "rotational"})
    w._on_root_event(tab, "root_progress", {"paths": ["/mnt/X"], "frac": 0.42, "estado": "estimado",
                                            "modo": "nome", "found_por": {"/mnt/X": 7}})
    w._render_narrative(tab)
    txt = w.narr_body.text()
    ok("~42%" in txt and "7 " in txt.replace("&nbsp;", " "), "varrendo: ~42 % e achados ao vivo")
    ok("100%" not in txt, "varrendo: nunca 100 %")
    w._on_root_event(tab, "root_done", {"path": "/mnt/X", "found": 9, "completo": True})
    w._render_narrative(tab)
    ok("100%" in w.narr_body.text(), "terminou completo: 100 %")
    # cancelado
    w._reset_narrative(tab)
    w._on_root_event(tab, "root_scanning", {"path": "/mnt/Y", "klass": "rotational"})
    w._on_root_event(tab, "root_progress", {"paths": ["/mnt/Y"], "frac": 0.3, "estado": "estimado", "modo": "nome"})
    w._on_root_event(tab, "root_done", {"path": "/mnt/Y", "found": 1, "completo": False})
    w._render_narrative(tab)
    txt = w.narr_body.text()
    ok("100%" not in txt and "30%" in txt and A.t("stopped") in txt, "cortado: congela em 30 % e diz 'parado'")
    # sem histórico: barra indeterminada, sem número
    w._reset_narrative(tab)
    w._on_root_event(tab, "root_scanning", {"path": "/mnt/Z", "klass": "ssd"})
    w._on_root_event(tab, "root_progress", {"paths": ["/mnt/Z"], "frac": None, "estado": "sem_historico", "modo": "nome"})
    w._render_narrative(tab)
    txt = w.narr_body.text()
    ok(A.t("first pass here") in txt and "%" not in txt, "sem histórico: sem porcentagem, avisa 1ª passagem")

    # booleano: sem barra
    class WB:
        boolexpr = "a AND b"

        def isRunning(self):
            return True
    tab.worker = WB()
    w._reset_narrative(tab)
    w._on_root_event(tab, "root_scanning", {"path": "/mnt/B", "klass": "ssd"})
    w._render_narrative(tab)
    ok("█" not in w.narr_body.text(), "booleana: sem barra")
    tab.worker = None
    # extensão a snapshots: a linha volta a varrer e a barra recomeça
    w._reset_narrative(tab)
    w._on_root_event(tab, "root_scanning", {"path": "/", "klass": "ssd"})
    w._on_root_event(tab, "root_done", {"path": "/", "found": 0, "completo": True})
    w._on_root_event(tab, "root_scanning", {"path": "/", "klass": "ssd"})
    rec = tab.roots["/"]
    ok(rec["state"] == "scanning" and rec["prog"] is None and rec["t_fim"] is None,
       "extensão a snapshots: a linha volta a 'varrendo' com a barra zerada")
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, w.close)                  # fechar para as threads da janela
    for _ in range(30):
        qapp.processEvents(); time.sleep(0.01)
    if w._upd_worker:
        w._upd_worker.wait(10000)

print()
print(f"{len(falhas)} falha(s)" if falhas else "tudo ok")
sys.exit(1 if falhas else 0)
