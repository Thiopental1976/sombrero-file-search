#!/usr/bin/env python3
"""A TABELA DE HONESTIDADE — (backend) × (perda de completude).

Por que este arquivo existe (08/09/2026). O lema do projeto é
"honestidade > completude", e o funil `stats['incompleto']` promete que TODA
perda passa por ele. Quatro rodadas de revisão do desenho não pegaram que a
busca por NOME nunca reportou pasta sem permissão — o `fd` esconde
"Permission denied" a menos que receba `--show-errors`, e as suítes só testavam
`denied` com o `rg`, com o walker Python e com o booleano. Ou seja: mediram
honestidade com um instrumento que não alcança o modo PADRÃO do programa.

A lição não é "revisar mais". É que honestidade é um invariante ENTRE módulos
(fd↔_reap, booleano↔engine, engine↔app) e revisão por módulo não o alcança.
Esta tabela é o instrumento que alcança: cada célula afirma que, dada uma perda
real, o funil tem a entrada certa. Célula que hoje não passa fica PINADA em
LACUNAS_CONHECIDAS com o motivo — mesma convenção da suíte de paridade.

Revisão do instrumento (Fable 5.1, 08/09/2026) — pontos cegos da 1a versão:
  - `max_results` só era medido no fd/nome, mas o corte mora em engine.search
    (compartilhado por fd/rg/py) E, separado, em search_boolean. Agora é coluna
    de todos os cinco.
  - a poda de snapshots (F11) não era coluna nenhuma: avisava por on_event, que
    a CLI não passa. Perda de cobertura deliberada continua sendo perda.
  - células podem passar pelo motivo ERRADO: rg com raiz inexistente saía 2 e
    virava 'engine_failed' (grave, mas rótulo falso). A célula exige o motivo.
  - raiz que é ARQUIVO: os backends divergiam (rg aceita, fd e walker calam).
  - erro de LEITURA (EIO de disco ruim): só provocável por mock de open(), e
    só nos backends Python — o rg não tem como ser induzido sem dispositivo.
  - o fallback Python do booleano era invisível (linha 'booleano/py').
  - fora da tabela: cancelamento com disco que não responde (nível 4).

A catraca corre nos dois sentidos:
  - célula verde que fica vermelha  -> falha (regressão)
  - lacuna pinada que passa a funcionar -> falha, pedindo pra despinar
    (senão a lista de lacunas vira ficção, que é a doença que tratamos)
"""
import builtins, errno, os, shutil, stat, subprocess, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, boolean as B

# ---------------------------------------------------------------- as lacunas
# (backend, perda): por que ainda não passa. Despinar ao consertar.
LACUNAS_CONHECIDAS = {
    # (08/09/2026, Fable 5.1) todas as 11 lacunas da 1a versão foram fechadas
    # (H1-H8 no engine/boolean). Lacuna nova entra aqui com o motivo REAL.
}

REAL_POPEN = subprocess.Popen


# ---------------------------------------------------------------- fixture
class Arvore:
    """Árvore com um achado legítimo e as armadilhas de cada perda."""
    def __init__(self):
        self.raiz = tempfile.mkdtemp(prefix="sfs-honesto-")
        self.ok = os.path.join(self.raiz, "achado.txt")
        open(self.ok, "w").write("laudo\n")
        self.dir_negado = os.path.join(self.raiz, "negado")
        os.makedirs(self.dir_negado)
        open(os.path.join(self.dir_negado, "b.txt"), "w").write("laudo\n")
        self.arq_negado = os.path.join(self.raiz, "arquivo_negado.txt")
        open(self.arq_negado, "w").write("laudo\n")

    def fecha_dir(self):  os.chmod(self.dir_negado, 0o000)
    def abre_dir(self):   os.chmod(self.dir_negado, 0o755)
    def fecha_arq(self):  os.chmod(self.arq_negado, 0o000)
    def abre_arq(self):   os.chmod(self.arq_negado, 0o644)
    def limpa(self):
        self.abre_dir(); self.abre_arq()
        shutil.rmtree(self.raiz, ignore_errors=True)


# ---------------------------------------------------------------- backends
def _busca(paths, stats, **kw):
    out = []
    E.search(E.Query(paths=paths, **kw), out.append, stats=stats)
    return out


def bk_fd(a, paths, stats, **kw):      # busca por NOME (modo padrão da GUI)
    if not E.FD: return None
    return _busca(paths, stats, name_patterns=["*.txt"], **kw)


def bk_rg(a, paths, stats, **kw):      # busca por CONTEÚDO
    if not E.RG: return None
    return _busca(paths, stats, content="laudo", **kw)


def bk_py_nome(a, paths, stats, **kw):
    fd = E.FD; E.FD = None
    try:    return _busca(paths, stats, name_patterns=["*.txt"], **kw)
    finally: E.FD = fd


def bk_py_conteudo(a, paths, stats, **kw):
    rg, rga = E.RG, E.RGA; E.RG = E.RGA = None
    try:    return _busca(paths, stats, content="laudo", **kw)
    finally: E.RG, E.RGA = rg, rga


def bk_booleano(a, paths, stats, **kw):
    out = []
    B.search_boolean(E.Query(paths=paths, **kw), "laudo", out.append, stats=stats)
    return out


def bk_booleano_py(a, paths, stats, **kw):   # booleano sem rg: fallback Python
    rg, rga = E.RG, E.RGA; E.RG = E.RGA = None
    try:    return bk_booleano(a, paths, stats, **kw)
    finally: E.RG, E.RGA = rg, rga


BACKENDS = [("fd/nome", bk_fd), ("rg/conteudo", bk_rg),
            ("py/nome", bk_py_nome), ("py/conteudo", bk_py_conteudo),
            ("booleano", bk_booleano), ("booleano/py", bk_booleano_py)]


# ---------------------------------------------------------------- perdas
# (nome, motivo esperado, grave?, aplica_em) — aplica_em None = todos
def p_dir_negado(a, bk, stats):
    a.fecha_dir()
    try:    bk(a, [a.raiz], stats)
    finally: a.abre_dir()

def p_arq_negado(a, bk, stats):
    a.fecha_arq()
    try:    bk(a, [a.raiz], stats)
    finally: a.abre_arq()

def _popen_flag_ruim(cmd, *ar, **kw):
    base = os.path.basename(cmd[0]) if cmd else ""
    if base.startswith(("rg", "fd")):
        cmd = cmd[:1] + ["--flag-que-nao-existe"] + cmd[1:]
    return REAL_POPEN(cmd, *ar, **kw)

def p_flag_invalida(a, bk, stats):
    subprocess.Popen = _popen_flag_ruim
    try:    bk(a, [a.raiz], stats)
    finally: subprocess.Popen = REAL_POPEN

def p_motor_ausente(a, bk, stats):
    def morre(*ar, **kw): raise OSError("binário não encontrado")
    subprocess.Popen = morre
    try:    bk(a, [a.raiz], stats)
    finally: subprocess.Popen = REAL_POPEN

def p_raiz_inexistente(a, bk, stats):
    bk(a, [os.path.join(a.raiz, "nao_existe_mesmo")], stats)

def p_raiz_arquivo(a, bk, stats):
    bk(a, [a.ok], stats)                  # existe, mas é arquivo

REAL_OPEN = builtins.open

def p_erro_leitura(a, bk, stats):
    open(os.path.join(a.raiz, "eio.txt"), "w").write("laudo\n")
    def open_eio(f, *ar, **kw):
        if isinstance(f, str) and os.path.basename(f) == "eio.txt":
            raise OSError(errno.EIO, "Input/output error")
        return REAL_OPEN(f, *ar, **kw)
    builtins.open = open_eio
    try:    bk(a, [a.raiz], stats)
    finally: builtins.open = REAL_OPEN

def _com_montagem(fstab, mountpoint, vaga):
    """Injeta os fatos de montagem no gate (a máquina de teste não tem o disco)."""
    orig = (E._fstab_alvos, E._eh_mountpoint, E._eh_vaga_de_montagem)
    E._fstab_alvos = lambda: fstab
    E._eh_mountpoint = lambda p: mountpoint
    E._eh_vaga_de_montagem = lambda p: vaga
    return orig

def _restaura_montagem(orig):
    E._fstab_alvos, E._eh_mountpoint, E._eh_vaga_de_montagem = orig

def p_raiz_nao_montada(a, bk, stats):
    # a raiz está no fstab e não é ponto de montagem ativo: disco ausente
    orig = _com_montagem({a.raiz.rstrip("/")}, False, True)
    try:    bk(a, [a.raiz], stats)
    finally: _restaura_montagem(orig)

def p_mountpoint_vazio(a, bk, stats):
    vazia = os.path.join(a.raiz, "vaga")
    os.makedirs(vazia)
    orig = _com_montagem(set(), False, True)
    try:    bk(a, [vazia], stats)
    finally: _restaura_montagem(orig)

def p_max_results(a, bk, stats):
    for i in range(30):
        open(os.path.join(a.raiz, f"m{i}.txt"), "w").write("laudo\n")
    bk(a, [a.raiz], stats, max_results=5)

def p_snapshots(a, bk, stats):
    # a poda F11 é por componente de caminho: timeshift/snapshots/<data>/...
    d = os.path.join(a.raiz, "timeshift", "snapshots", "2026-09-01", "home")
    os.makedirs(d)
    open(os.path.join(d, "so_no_snapshot.txt"), "w").write("laudo\n")
    bk(a, [a.raiz], stats)

PERDAS = [
    ("pasta negada",     "permission_denied",  False, p_dir_negado,      None),
    ("arquivo negado",   "permission_denied",  False, p_arq_negado,
     {"rg/conteudo", "py/conteudo", "booleano"}),          # nome não lê o arquivo
    ("flag invalida",    "engine_failed",   True,  p_flag_invalida,
     {"fd/nome", "rg/conteudo", "booleano"}),              # walker não tem binário
    ("motor ausente",    "engine_missing",  True,  p_motor_ausente,
     {"fd/nome", "rg/conteudo", "booleano"}),
    ("raiz inexistente", "invalid_root",  True,  p_raiz_inexistente, None),
    ("raiz e arquivo",   "invalid_root",  True,  p_raiz_arquivo,    None),
    ("raiz nao montada", "not_mounted",   True,  p_raiz_nao_montada, None),
    ("mountpoint vazio", "empty_mountpoint", False, p_mountpoint_vazio, None),
    ("max_results",      "truncated",       False, p_max_results,     None),
    ("snapshots",        "snapshots_skipped", False, p_snapshots,     None),
    ("erro de leitura",  "read_error",   False, p_erro_leitura,
     {"py/conteudo", "booleano/py"}),                      # rg: sem como induzir
]


# ---------------------------------------------------------------- execução
def celula(bk_nome, bk, perda):
    nome, motivo_esp, grave_esp, roda, aplica = perda
    if aplica is not None and bk_nome not in aplica:
        return "—", ""
    a = Arvore()
    stats = {}
    try:
        roda(a, bk, stats)
    except Exception as e:
        return "ERRO", repr(e)[:60]
    finally:
        a.limpa()
    motivos = {e["motivo"] for e in (stats.get("incompleto") or [])}
    if motivo_esp not in motivos:
        return "MUDO", f"funil={sorted(motivos) or 'vazio'}"
    grave, _ = E.resumo_incompleto(stats)
    if grave != grave_esp:
        return "GRAV", f"grave={grave}, esperado {grave_esp}"
    return "ok", ""


print(f"{'':<14}" + "".join(f"{p[0]:<17}" for p in PERDAS))
verdes = vermelhas = 0
regressoes, curadas = [], []
detalhes = []
for bk_nome, bk in BACKENDS:
    linha = f"{bk_nome:<14}"
    for perda in PERDAS:
        r, det = celula(bk_nome, bk, perda)
        chave = (bk_nome, perda[0])
        pinada = chave in LACUNAS_CONHECIDAS
        if r == "ok":
            verdes += 1
            if pinada:
                curadas.append(chave)
                r = "ok!"                      # consertou: despinar
        elif r != "—":
            vermelhas += 1
            if pinada:
                r = "~"                        # lacuna conhecida
            else:
                regressoes.append((chave, det))
        linha += f"{r:<17}"
        if det and r not in ("ok", "—"):
            detalhes.append(f"  {bk_nome:<14} {perda[0]:<18} {det}")
    print(linha)

print(f"\nverdes {verdes} · vermelhas {vermelhas} · pinadas {len(LACUNAS_CONHECIDAS)}")

# ------------------------------------------------- fora da tabela (nível 4)
# Cancelamento com um disco que não responde dentro do teto: o worker leva o
# próprio dict de stats embora. O funil tem de dizer que NÃO SABE as perdas
# daquele disco, em vez de fingir que o relatório está completo.
def _worker_surdo(qq, cc, ss, procs=None):
    if qq.paths == ["/surdo"]:
        ss["denied"] = 1                       # perda que nunca chega ao stats
        time.sleep(1.0)                        # ignora o cancel (I/O que não volta)
    yield E.Match(f"{qq.paths[0]}/x", 0, 0)

extra_falhas = []
st = {}
it = E._iter_particionado(E.Query(paths=["/vivo", "/surdo"]), lambda: False, st,
                          [["/vivo"], ["/surdo"]], _worker_surdo, limite_s=0.2)
next(it); it.close()                            # como o break por max_results
mot = {e["motivo"]: e for e in st.get("incompleto") or []}
if "interrupted" not in mot or mot["interrupted"]["onde"] != "/surdo":
    extra_falhas.append(f"cancel: disco surdo não virou 'interrupted' (funil={sorted(mot)})")
grave, _ = E.resumo_incompleto(st)
if grave:
    extra_falhas.append("cancel: 'interrupted' não pode ser grave (foi o usuário que cancelou)")
print("fora da tabela: cancelamento c/ disco surdo ->",
      "ok" if not extra_falhas else "FALHA")
regressoes += [(("particionado", "cancel"), d) for d in extra_falhas]
if detalhes:
    print("\ndetalhe:")
    print("\n".join(detalhes))
if regressoes:
    print("\nCÉLULAS VERMELHAS NÃO PINADAS (regressão ou lacuna a declarar):")
    for (bk, p), d in regressoes:
        print(f"  ({bk!r}, {p!r})  {d}")
if curadas:
    print("\nLACUNAS QUE PASSARAM A FUNCIONAR — remova de LACUNAS_CONHECIDAS:")
    for c in curadas:
        print(f"  {c}")
sys.exit(1 if (regressoes or curadas) else 0)
