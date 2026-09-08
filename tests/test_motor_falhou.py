#!/usr/bin/env python3
"""F11b — motor que FALHA não pode virar "nada encontrado".

Achado do Fable 5 na revisão de 08/09/2026: o rg sai com código 2 quando não
entende uma flag (p.ex. --glob-case-insensitive, que só existe do rg 12 pra
cima e falta no Ubuntu 20.04). O stderr ia pro tempfile, o _reap só contava
"permission denied", e a busca devolvia ZERO RESULTADOS EM SILÊNCIO — o pior
modo de falha possível numa ferramenta cujo lema é "honestidade > completude",
porque o usuário conclui que o arquivo não existe.
"""
import os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)


raiz = tempfile.mkdtemp(prefix="sfs-falha-")
open(os.path.join(raiz, "a.txt"), "w").write("laudo\n")
real_popen = subprocess.Popen


def com_flag_invalida(binario):
    """Injeta uma flag que nenhum fd/rg conhece — simula binário antigo."""
    def popen(cmd, *a, **k):
        if cmd and os.path.basename(cmd[0]).startswith(binario):
            cmd = cmd[:1] + ["--flag-que-nao-existe"] + cmd[1:]
        return real_popen(cmd, *a, **k)
    return popen


try:
    # 1) caminho saudável não inventa erro
    st, out = {}, []
    E.search(E.Query(paths=[raiz], content="laudo"), out.append, stats=st)
    ok(len(out) == 1 and not st.get("engine_errors"),
       "busca saudável acha e não reporta erro de motor")

    # 2) rg quebrado: zero achados, MAS com o erro registrado
    for binario, modo in (("rg", {"content": "laudo"}), ("fd", {"name_patterns": ["*.txt"]})):
        if binario == "rg" and not E.RG:
            print(f"~pula {binario} (ausente)"); continue
        if binario == "fd" and not E.FD:
            print(f"~pula {binario} (ausente)"); continue
        subprocess.Popen = com_flag_invalida(binario)
        st, out = {}, []
        try:
            E.search(E.Query(paths=[raiz], **modo), out.append, stats=st)
        finally:
            subprocess.Popen = real_popen
        errs = st.get("engine_errors") or []
        ok(bool(errs), f"{binario} que falha registra engine_errors (não some)")
        ok(errs and errs[0].get("rc") not in (0, 1),
           f"{binario}: o código de saída do erro é preservado")
        ok(errs and "flag" in (errs[0].get("erro") or "").lower(),
           f"{binario}: a mensagem real do binário chega ao chamador")

    # 3) o CLI sai 2 (erro), não 1 (nada encontrado)
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    r = subprocess.run([sys.executable, "-m", "lfs.cli", "-n", "*.zzz", raiz],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ok(r.returncode == 1, "CLI: nada encontrado continua saindo 1")
finally:
    subprocess.Popen = real_popen
    shutil.rmtree(raiz, ignore_errors=True)

print(f"\n{'FALHOU: ' + '; '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
