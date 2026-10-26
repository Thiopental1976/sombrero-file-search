#!/usr/bin/env python3
"""Programa ausente no sistema: dito como tal, com como resolver (26/10/2026).

Pedido do Rodrigo: "a GUI [deve indicar] a falta dos módulos de forma
evidente ... ou eles sempre pensarão que é uma falha do SFS". Antes: sem o
pdftotext cada PDF virava um read_error; sem fd/rg a busca caía no walker
Python sem nada na janela.

Contratos presos aqui:
  1. bloco do rga 'Could not find executable "pdftotext"' em N PDFs vira UMA
     entrada component_missing (onde=pdftotext, n=N), não N read_error; um
     PDF ruim de verdade no mesmo stderr continua read_error;
  2. sem fd (busca por nome) / sem rg (conteúdo): component_missing fd / rg;
     com os dois presentes, nada;
  3. orientação: fd/rg/rga -> pacote completo (URL); pdftotext -> comando da
     distro (apt/dnf/rpm-ostree/pacman/zypper, pelo os-release);
  4. CLI: '# missing: pdftotext' no stderr; --json com 'hint';
  5. GUI: diálogo não modal, uma vez por programa por sessão, com
     "Copiar comando" quando há comando.

Rode:
    QT_QPA_PLATFORM=offscreen python3 tests/test_componente_ausente_2026_10_26.py
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile

os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sfs-test-comp-")   # config descartável
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="sfs-test-comp-")
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, componentes
from engine import Query

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

RULER = "-" * 79
# formato real do rga 0.10 sem o pdftotext no PATH (capturado em 26/10/2026)
def bloco_sem_programa(caminho):
    return (f"rg: {caminho}: preprocessor command failed: '\"/b/rga-preproc\" \"{caminho}\"': \n"
            f"{RULER}\n{caminho} adapter: poppler\nError: during preprocessing\n\n"
            f"Caused by:\n    0: run_adapter({caminho})\n"
            f"    1: adapting {caminho} via poppler failed\n"
            f"    2: Could not find executable \"pdftotext\".\n{RULER}\n")

def bloco_pdf_ruim(caminho):
    return (f"rg: {caminho}: preprocessor command failed: '\"/b/rga-preproc\" \"{caminho}\"':\n"
            f"{RULER}\n{caminho} adapter: poppler\nSyntax Error: Couldn't read xref table\n"
            f"Error: copying adapter output to stdout\n\nCaused by:\n"
            f"    0: subprocess: Command {{ std: \"pdftotext\" }}\n{RULER}\n")

class ProcFalso:
    def __init__(self, rc): self.returncode = rc
    def poll(self): return self.returncode

def reap(stderr):
    errf = tempfile.TemporaryFile(mode="w+"); errf.write(stderr); errf.flush()
    stats = {}
    engine._reap(ProcFalso(2), errf, stats)
    return stats

# 1. pdftotext ausente em 3 PDFs + 1 PDF ruim de verdade
st = reap("".join(bloco_sem_programa(f"/x/{i}.pdf") for i in range(3))
          + bloco_pdf_ruim("/x/ruim.pdf"))
inc = st.get("incompleto") or []
comp = [e for e in inc if e["motivo"] == "component_missing"]
ok(len(comp) == 1 and comp[0]["onde"] == "pdftotext" and comp[0]["n"] == 3,
   f"3 PDFs sem pdftotext: uma entrada, n=3 ({comp})")
ok([e["onde"] for e in inc if e["motivo"] == "read_error"] == ["/x/ruim.pdf"],
   "o PDF ruim de verdade segue read_error")
ok(not any(e["motivo"] == "engine_failed" for e in inc), "nada de engine_failed")
ok(engine.componentes_faltando(st) == [("pdftotext", 3)], "componentes_faltando")
_, linhas = engine.resumo_incompleto(st)
ok(any(L.startswith("program missing: pdftotext (×3)") for L in linhas), f"linha do resumo ({linhas})")

# 2. fd / rg ausentes
base = tempfile.mkdtemp(prefix="sfs_comp_")
with open(os.path.join(base, "a.txt"), "w") as f:
    f.write("agulha\n")
salvo = (engine.FD, engine.RG)
try:
    engine.FD = engine.RG = None
    st = {}
    engine.search(Query(paths=[base], name_patterns=["*.txt"]), lambda m: None, stats=st)
    ok(engine.componentes_faltando(st) == [("fd", 1)], f"sem fd: aponta fd ({engine.componentes_faltando(st)})")
    st = {}
    engine.search(Query(paths=[base], content="agulha"), lambda m: None, stats=st)
    ok(engine.componentes_faltando(st) == [("rg", 1)], f"sem rg: aponta rg ({engine.componentes_faltando(st)})")
finally:
    engine.FD, engine.RG = salvo
if engine.FD and engine.RG:
    st = {}
    engine.search(Query(paths=[base], content="agulha"), lambda m: None, stats=st)
    ok(engine.componentes_faltando(st) == [], "com fd e rg: nada")
shutil.rmtree(base, ignore_errors=True)

# 3. orientação
WIN = os.name == "nt"
for prog in ("fd", "rg", "rga") + (("pdftotext",) if WIN else ()):
    o = componentes.orientacao(prog)
    ok(o["url"] == componentes.SITE_INSTALL and o["cmd"] is None, f"{prog}: pacote completo")
d = tempfile.mkdtemp(prefix="sfs_osrel_")
if WIN:   # sem gerenciador de pacotes: o zip do Windows traz o pdftotext
    ok(componentes.gestor() is None, "Windows: sem gestor de pacotes")
casos = {('ID=linuxmint\nID_LIKE="ubuntu debian"\n', None): "sudo apt install poppler-utils",
         ('ID=fedora\n', None): "sudo dnf install poppler-utils",
         ('ID=bazzite\nID_LIKE="fedora"\n', "sim"): "rpm-ostree install poppler-utils",
         ('ID=arch\n', None): "sudo pacman -S poppler",
         ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', None): "sudo zypper install poppler-tools"}
for (conteudo, ostree), esperado in ({} if WIN else casos).items():
    osr = os.path.join(d, "os-release")
    with open(osr, "w") as f:
        f.write(conteudo)
    flag = os.path.join(d, "ostree-booted")
    if ostree:
        open(flag, "w").close()
    elif os.path.exists(flag):
        os.remove(flag)
    g = componentes.gestor(osr, flag)
    o = componentes.orientacao("pdftotext", g)
    ok(o["cmd"] == esperado, f"pdftotext em {conteudo.split()[0]}: {o['cmd']!r}")
if not WIN:
    os.remove(os.path.join(d, "os-release"))
ok(componentes.gestor(os.path.join(d, "os-release"), os.path.join(d, "nada")) is None,
   "sem os-release: sem gestor")
if not WIN:
    o = componentes.orientacao("pdftotext", "desconhecido")
    ok(o["cmd"] is None and "poppler-utils" in o["args"].get("pkg", ""),
       "distro desconhecida: nome do pacote, sem comando")
shutil.rmtree(d, ignore_errors=True)

# 4. CLI (pdftotext fora do PATH)
pdftotext = shutil.which("pdftotext")
pdf = None
for raiz, _ds, fs in os.walk(os.path.expanduser("~/sfs_demo")):
    pdf = next((os.path.join(raiz, f) for f in fs if f.endswith(".pdf")), None)
    if pdf:
        break
if not (engine.RGA and pdftotext and pdf):
    print("(sem rga, pdftotext ou um PDF de amostra: checagem da CLI pulada)")
else:
    d = tempfile.mkdtemp(prefix="sfs_comp_cli_")
    binp = os.path.join(d, "bin"); os.makedirs(binp)
    for b in ("rg", "rga", "rga-preproc", "fd"):
        w = shutil.which(b) or os.path.join(os.path.dirname(engine.RGA), b)
        if os.path.exists(w):
            os.symlink(w, os.path.join(binp, b))
    docs = os.path.join(d, "docs"); os.makedirs(docs)
    shutil.copy(pdf, os.path.join(docs, "novo.pdf"))
    env = dict(os.environ, LANG="C.UTF-8", PATH=binp, XDG_CACHE_HOME=os.path.join(d, "cache"))
    cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
    p = subprocess.run(cli + ["-D", "-c", "qualquer", docs], capture_output=True, text=True, env=env, timeout=120)
    ok("# missing: pdftotext is not installed" in p.stderr, f"CLI: '# missing: pdftotext' ({p.stderr[-300:]!r})")
    env["XDG_CACHE_HOME"] = os.path.join(d, "cache2")
    p = subprocess.run(cli + ["-D", "-c", "qualquer", "--json", docs], capture_output=True, text=True, env=env, timeout=120)
    objs = [json.loads(L) for L in p.stdout.splitlines() if L.startswith("{")]
    ok(any(o.get("reason") == "component_missing" and o.get("where") == "pdftotext" and o.get("hint")
           for o in objs), f"--json: component_missing com hint ({objs})")
    shutil.rmtree(d, ignore_errors=True)

# 5. GUI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox
import app as gui
qa = QApplication.instance() or QApplication([])
w = gui.MainWindow()
w.cfg.setdefault("updates", {})["auto"] = False
st = {"incompleto": [{"motivo": "component_missing", "onde": "pdftotext", "detalhe": "x", "n": 12}]}
w._avisa_componentes(st)
box = getattr(w, "_dialogo_componentes", None)
ok(box is not None and box.isVisible(), "GUI: diálogo aberto")
ok(box is not None and not box.isModal() or box.windowModality() != gui.Qt.ApplicationModal,
   "GUI: diálogo não trava o programa")
botoes = [b.text() for b in box.buttons()] if box else []
if WIN:   # pdftotext vem no zip: a saída é a página de download
    ok(any("download" in b.lower() for b in botoes), f"GUI: botão da página de download ({botoes})")
else:
    ok(any("Copy command" in b or "Copiar comando" in b for b in botoes), f"GUI: botão de copiar ({botoes})")
ok(box is not None and "pdftotext" in box.text() and "12" in box.text(), "GUI: nomeia o programa e a contagem")
box.close(); qa.processEvents()
w._dialogo_componentes = None
w._avisa_componentes(st)
ok(w._dialogo_componentes is None, "GUI: o mesmo programa não abre o diálogo de novo")
w.close()

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
