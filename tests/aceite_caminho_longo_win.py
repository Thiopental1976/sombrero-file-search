#!/usr/bin/env python3
"""Aceite REAL de caminho longo no Windows (24/11/2026; cuidados apontados pela Vega).

Roda no CI com a política LongPathsEnabled DESLIGADA: raiz curta, árvore com mais
de 300 caracteres lá embaixo. Mede o que o pacote faz de verdade (fd/rg empacotados
pelo sfs.exe) e o que os nossos walkers em Python fazem (nomes e duplicatas).

Uso:  python tests\\aceite_caminho_longo_win.py dist\\SombreroFileSearch\\sfs.exe
Sai 0 se tudo certo (ou se não é Windows), 1 se algo falhou.
"""
import os, shutil, subprocess, sys

if os.name != "nt":
    print("~pula: aceite de caminho longo e so-Windows"); sys.exit(0)

SFS = os.path.abspath(sys.argv[1])
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, dupes                                  # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok     " if cond else "FALHOU ") + msg, flush=True)
    if not cond:
        falhas.append(msg)

# fora do checkout: a limpeza do runner engasga em caminho > 260 com a politica desligada
base = os.path.abspath(os.path.join(os.environ.get("RUNNER_TEMP") or os.environ["TEMP"],
                                    "sfs_lp_%d" % os.getpid()))
nc = os.path.normcase                                 # d:\ x D:\ não pode dar falso-vermelho
V = "\\\\?\\"
fundo = base + ("\\" + "n" * 25) * 12                 # > 300 caracteres
try:
    os.makedirs(V + fundo)
    txt = fundo + "\\a_longo.txt"
    with open(V + txt, "w", encoding="utf-8") as f:
        f.write("palavra_laudo_longo aqui\n")
    for n in ("copia1.bin", "copia2.bin"):
        with open(V + fundo + "\\" + n, "wb") as f:
            f.write(b"sombrero-caminho-longo\n" * 400)
    print("raiz %s (%d) | arquivo com %d caracteres" % (base, len(base), len(txt)), flush=True)

    # a politica pegou? Num processo NOVO, o caminho longo SEM prefixo tem de falhar.
    r = subprocess.run([sys.executable, "-c", "import os,sys; os.stat(sys.argv[1])", txt],
                       capture_output=True)
    conclusivo = r.returncode != 0
    if not conclusivo:
        print("::warning::LongPathsEnabled=0 nao teve efeito neste runner: o aceite de "
              "caminho longo passou sem provar nada (INCONCLUSIVO)", flush=True)

    def roda(*args):
        p = subprocess.run([SFS, base, *args, "-l"], capture_output=True)
        saida = p.stdout.decode("utf-8", "replace").splitlines()
        return p.returncode, [l for l in saida if l.strip()], p.stderr.decode("utf-8", "replace")

    def confere(nome, rc, linhas, err, final):
        achou = [l for l in linhas if l.endswith(final)]
        ok(rc == 0, "%s: saiu 0, busca completa (rc=%s)" % (nome, rc))      # 2 = incompleta
        ok(len(achou) == 1 and nc(achou[0]) == nc(txt),
           "%s: achou exatamente o arquivo fundo (%d linha(s))" % (nome, len(linhas)))
        ok(not any(l.startswith(V) for l in linhas), "%s: caminho impresso sem o prefixo \\\\?\\" % nome)
        ok(bool(achou) and all(os.path.exists(V + l) for l in achou), "%s: o caminho impresso existe" % nome)
        if len(achou) != 1:
            print("   stdout: %r\n   stderr: %s" % (linhas[:5], err[-600:]), flush=True)

    confere("sfs.exe -n", *roda("-n", "a_longo.txt"), final="a_longo.txt")
    confere("sfs.exe -c", *roda("-c", "palavra_laudo_longo"), final="a_longo.txt")

    st = {}
    ms = [m.path for m in engine._iter_names_python(
        engine.Query(paths=[base], name_patterns=["a_longo.txt"]), st)]
    ok([nc(m) for m in ms] == [nc(txt)] and not ms[0].startswith(V),
       "walker Python de nomes acha o arquivo fundo, sem prefixo (%r)" % (ms[:2],))
    ok(not st.get("incompleto") and not st.get("denied"), "walker de nomes: nada incompleto nem negado (%r)" % st)

    st = {}
    mc = [m.path for m in engine._iter_content_python(
        engine.Query(paths=[base], content="palavra_laudo_longo"), lambda: False, st)]
    ok([nc(m) for m in mc] == [nc(txt)] and not mc[0].startswith(V),
       "conteudo pelo caminho Python acha o arquivo fundo, sem prefixo (%r)" % (mc[:2],))
    ok(not st.get("incompleto") and not st.get("denied"), "conteudo Python: nada incompleto nem negado (%r)" % st)

    st = {}
    grupos = dupes.find_duplicates([base], stats=st)
    caminhos = sorted(p for g in grupos for c in g.members for p in c.paths)
    ok([nc(c) for c in caminhos] == [nc(fundo + "\\copia1.bin"), nc(fundo + "\\copia2.bin")]
       and not any(c.startswith(V) for c in caminhos),
       "duplicatas: as 2 copias no fundo formam 1 grupo, sem prefixo (%d grupo(s))" % len(grupos))
    ok(not st.get("denied"), "duplicatas: nenhum diretorio contado como negado (%r)" % st)
finally:
    shutil.rmtree(V + base, ignore_errors=True)

print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas))
      + ("" if conclusivo else " (INCONCLUSIVO: a politica nao pegou)"))
sys.exit(1 if falhas else 0)
