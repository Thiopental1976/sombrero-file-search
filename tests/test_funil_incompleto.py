#!/usr/bin/env python3
"""F11c — stats['incompleto'] é o canal ÚNICO de perda de completude.

A 3a revisão (Fable 5.1) acusou o lema do projeto de ser slogan: havia quatro
canais paralelos de "algo se perdeu" e várias perdas não iam para nenhum. Estes
testes travam a invariante — se um caminho novo perder resultado sem passar
pelo funil, é aqui que aparece.
"""
import os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

def motivos(st):
    return {e["motivo"] for e in (st.get("incompleto") or [])}


# ---- 1) o funil em si
st = {}
E.anota_incompleto(st, "permission_denied", n=3)
E.anota_incompleto(st, "permission_denied", n=5)
ok(len(st["incompleto"]) == 1 and st["incompleto"][0]["n"] == 8,
   "agrega por (motivo, onde) em vez de virar uma linha por ocorrência")

st2 = {}
for i in range(E._INCOMPLETO_MAX + 40):
    E.anota_incompleto(st2, "stat_failed", onde=f"/x/{i}")
ok(len(st2["incompleto"]) == E._INCOMPLETO_MAX and st2["incompleto_omitidos"] == 40,
   "o teto CONTA o que não coube (silenciar seria a própria doença)")

grave, linhas = E.resumo_incompleto({"incompleto": [
    {"motivo": "permission_denied", "onde": "", "detalhe": "", "n": 4}]})
ok(not grave, "falta de permissão é incompleto, NÃO grave (não pode mudar exit code)")
grave, _ = E.resumo_incompleto({"incompleto": [
    {"motivo": "engine_failed", "onde": "", "detalhe": "x", "n": 1}]})
ok(grave, "motor que falhou é grave")

# ---- 1b) a FUSÃO do particionado preserva os args do detalhe (09/09/2026:
# a revisão achou "exited with code {rc}: {msg}" cru na barra — cada worker
# anotava com args e _funde_stats os jogava fora ao reanotar no dict global)
w = {}
E.anota_incompleto(w, "engine_failed", detalhe="exited with code {rc}: {msg}",
                   args={"rc": 2, "msg": "bad flag"})
dst = {}
E._funde_stats(dst, w)
_, linhas = E.resumo_incompleto(dst)
ok("{rc}" not in linhas[0] and "code 2: bad flag" in linhas[0],
   "fusão do particionado mantém os args do detalhe (sem '{rc}' cru)")

# ---- 1c) o booleano só avisa 'snapshots_skipped' onde a poda está em vigor —
# raiz apontada para DENTRO de um snapshot não pula snapshot nenhum
_orig_tem = E.tem_snapshot
try:
    E.tem_snapshot = lambda r: True
    from lfs import boolean as B
    _d = tempfile.mkdtemp(prefix="lfs_snap_")
    _snap = os.path.join(_d, "timeshift", "snapshots", "2026-09-09", "home")
    os.makedirs(_snap); open(os.path.join(_snap, "a.txt"), "w").write("laudo\n")
    for raiz_b, espera, nome in ((_snap, False, "raiz dentro do snapshot: booleano NÃO avisa poda"),
                                 (_d, True, "raiz que hospeda snapshot: booleano avisa poda")):
        stb = {}
        B.search_boolean(E.Query(paths=[raiz_b], content="laudo"), "laudo", lambda m: None, stats=stb)
        ok(("snapshots_skipped" in motivos(stb)) is espera, nome)
    shutil.rmtree(_d, ignore_errors=True)
finally:
    E.tem_snapshot = _orig_tem


# ---- 2) perdas reais chegam ao funil
raiz = tempfile.mkdtemp(prefix="sfs-funil-")
open(os.path.join(raiz, "a.txt"), "w").write("laudo\n")
real_popen = subprocess.Popen
try:
    # motor que falha
    def popen_ruim(cmd, *a, **k):
        if cmd and os.path.basename(cmd[0]).startswith("rg"):
            cmd = cmd[:1] + ["--flag-que-nao-existe"] + cmd[1:]
        return real_popen(cmd, *a, **k)
    if E.RG:
        subprocess.Popen = popen_ruim
        st, out = {}, []
        try:
            E.search(E.Query(paths=[raiz], content="laudo"), out.append, stats=st)
        finally:
            subprocess.Popen = real_popen
        ok("engine_failed" in motivos(st), "rg que sai com erro chega ao funil")

    # motor AUSENTE: o fallback Python não é equivalente (UTF-16 com BOM)
    def popen_sumiu(cmd, *a, **k):
        raise OSError("binário não encontrado")
    subprocess.Popen = popen_sumiu
    st, out = {}, []
    try:
        E.search(E.Query(paths=[raiz], content="laudo"), out.append, stats=st)
    finally:
        subprocess.Popen = real_popen
    ok("engine_missing" in motivos(st),
       "cair no walker Python deixa de ser fallback SILENCIOSO")
    grave, _ = E.resumo_incompleto(st)
    ok(grave, "motor ausente é grave: o resultado pode estar errado, não só incompleto")

    # busca saudável não inventa incompletude
    st, out = {}, []
    E.search(E.Query(paths=[raiz], name_patterns=["*.txt"]), out.append, stats=st)
    ok(len(out) == 1 and not st.get("incompleto"),
       "busca saudável não reporta nada no funil")

    # pasta sem permissao NAO e falha de motor, mesmo com o rg saindo 2
    proibida = os.path.join(raiz, "segredo")
    os.makedirs(proibida, exist_ok=True)
    open(os.path.join(proibida, "b.txt"), "w").write("laudo\n")
    os.chmod(proibida, 0o000)
    try:
        st, out = {}, []
        E.search(E.Query(paths=[raiz], content="laudo"), out.append, stats=st)
        grave, _ = E.resumo_incompleto(st)
        ok("permission_denied" in motivos(st), "pasta proibida vira sem_permissao no funil")
        ok("engine_failed" not in motivos(st),
           "o rg saindo 2 SO por permissao nao e falha de motor")
        ok(not grave, "busca com pasta proibida nao e grave (exit code preservado)")
    finally:
        os.chmod(proibida, 0o755)

    # ---- 3) o exit code da CLI deriva do funil
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=base)
    r = subprocess.run([sys.executable, "-m", "lfs.cli", "-n", "*.zzz", raiz],
                       capture_output=True, text=True, env=env, cwd=base)
    ok(r.returncode == 1, "CLI: nada encontrado continua saindo 1 (contrato antigo)")
finally:
    subprocess.Popen = real_popen
    shutil.rmtree(raiz, ignore_errors=True)

print(f"\n{'FALHOU: ' + '; '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
