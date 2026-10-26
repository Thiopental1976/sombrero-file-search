#!/usr/bin/env python3
"""Um documento ilegível não derruba a busca em documentos (26/10/2026, Fable §2.1).

Com --docs, um PDF sem xref ou um docx que não é zip faz o adaptador do rga sair
≠ 0, e o rga escreve a queixa em BLOCO multilinha:

    rg: /x/ruim.pdf: preprocessor command failed: '"…/rga-preproc" "/x/ruim.pdf"':
    -------------------------------------------------------------------------------
    /x/ruim.pdf adapter: poppler
    Syntax Error: Couldn't read xref table
    Error: copying adapter output to stdout
    …

Nenhuma linha termina em "(os error N)", então o _reap não via erro POR ARQUIVO:
o rc 2 virava `engine_failed` grave ("search engine failed", exit 2, ⚠ na GUI)
com o resto dos resultados certo — e a causa real sumia.

Contratos presos aqui:
  1. o bloco vira `read_error` naquele arquivo (não-grave), com a causa real
     ("Couldn't read xref table", "not a valid zip container");
  2. queixa de motor de verdade (sem caminho) junto com um bloco continua
     `engine_failed`;
  3. ponta a ponta (com rga): acha o arquivo bom, avisa o ilegível, sai 0.

Rode:
    python3 tests/test_documento_ilegivel_2026_10_26.py
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

RULER = "-" * 79
BLOCO_PDF = f"""rg: /x/ruim.pdf: preprocessor command failed: '"/b/rga-preproc" "/x/ruim.pdf"':
{RULER}
/x/ruim.pdf adapter: poppler
/x/ruim.pdf.txt.asciipagebreaks adapter: postprocpagebreaks
Syntax Error: Couldn't find trailer dictionary
Syntax Error: Couldn't read xref table
Error: copying adapter output to stdout

Caused by:
    0: adapting /x/ruim.pdf.txt.asciipagebreaks via postprocpagebreaks failed
    1: subprocess: Command {{ std: "pdftotext" "-" "-", kill_on_drop: false }}
    2: ExitStatus(unix_wait_status(256))
{RULER}
"""
BLOCO_DOCX = f"""rg: /x/ruim.docx: preprocessor command failed: '"/b/rga-preproc" "/x/ruim.docx"':
{RULER}
Warning: found multiple adapters for ruim.docx:
 - sombrero_docs
 - pandoc
/x/ruim.docx adapter: sombrero_docs
/x/ruim.docx.txt adapter: postprocprefix
sombrero docs_text: not a valid zip container (File is not a zip file)
Error: copying adapter output to stdout

Caused by:
    0: subprocess: Command {{ std: "/py" "-I" "/l/docs_text.py" "docx", kill_on_drop: false }}
    1: ExitStatus(unix_wait_status(256))
{RULER}
"""

class ProcFalso:
    def __init__(self, rc): self.returncode = rc
    def poll(self): return self.returncode

def reap(stderr, rc=2):
    errf = tempfile.TemporaryFile(mode="w+"); errf.write(stderr); errf.flush()
    stats = {}
    engine._reap(ProcFalso(rc), errf, stats)
    return stats.get("incompleto") or []

def por_motivo(inc, m):
    return [e for e in inc if e["motivo"] == m]

# 1. blocos do rga = erro por arquivo
inc = reap(BLOCO_PDF + BLOCO_DOCX)
ok(not por_motivo(inc, "engine_failed"), f"bloco do rga não vira engine_failed ({[e['motivo'] for e in inc]})")
lidos = {e["onde"]: engine.texto_detalhe(e) for e in por_motivo(inc, "read_error")}
ok(set(lidos) == {"/x/ruim.pdf", "/x/ruim.docx"}, f"read_error nos dois arquivos ({sorted(lidos)})")
ok("xref" in lidos.get("/x/ruim.pdf", ""), f"causa real do PDF ({lidos.get('/x/ruim.pdf')!r})")
ok("zip container" in lidos.get("/x/ruim.docx", ""), f"causa real do docx ({lidos.get('/x/ruim.docx')!r})")
ok(not any(e.get("grave") for e in inc) and not any(e["motivo"] in engine.MOTIVOS_GRAVES for e in inc),
   "nenhuma perda grave")

# 2. motor quebrado de verdade continua engine_failed
inc = reap(BLOCO_PDF + "error: unexpected argument '--flag-que-nao-existe' found\n")
ok(por_motivo(inc, "engine_failed"), "queixa sem caminho + bloco: segue engine_failed")

# 2b. rc 2 só com o bloco, mas sem nada mais: não é falha de motor
inc = reap(BLOCO_PDF)
ok(not por_motivo(inc, "engine_failed") and len(por_motivo(inc, "read_error")) == 1,
   "um bloco só: um read_error, sem engine_failed")

# 3. ponta a ponta
if not engine.RGA:
    print("(sem rga nesta máquina: ponta a ponta pulada)")
else:
    d = tempfile.mkdtemp(prefix="sfs_doc_ilegivel_")
    with open(os.path.join(d, "ruim.pdf"), "w") as f: f.write("%PDF-1.4\nlixo agulha\n")
    with open(os.path.join(d, "ruim.docx"), "w") as f: f.write("PK isto nao e zip agulha\n")
    with open(os.path.join(d, "bom.txt"), "w") as f: f.write("linha\nagulha aqui\n")
    cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
    env = dict(os.environ, LANG="C.UTF-8")
    p = subprocess.run(cli + ["-D", "-c", "agulha", d], capture_output=True, text=True, env=env, timeout=120)
    ok(p.returncode == 0, f"CLI -D sai 0 ({p.returncode}): {p.stderr[-300:]!r}")
    ok("bom.txt" in p.stdout, "acha o arquivo bom")
    ok("search engine failed" not in p.stderr, "não diz 'search engine failed'")
    ok("ruim.pdf" in p.stderr and "ruim.docx" in p.stderr, "avisa os dois ilegíveis pelo nome")
    p = subprocess.run(cli + ["-D", "-c", "agulha", "--json", d], capture_output=True, text=True, env=env, timeout=120)
    objs = [json.loads(L) for L in p.stdout.splitlines() if L.startswith("{")]
    inc = [o for o in objs if "incomplete" in (o.get("warn"), o.get("error"))]
    ok(inc and all(o.get("warn") == "incomplete" and o.get("reason") == "read_error" for o in inc),
       f"--json: só warn read_error ({[(o.get('warn') or o.get('error'), o.get('reason')) for o in inc]})")

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
