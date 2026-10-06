#!/usr/bin/env python3
"""Costura de plataforma, F0 do SFS para Windows (desenho do Fable, 02/10/2026).

Roda no Linux e no Windows. No Linux, a costura tem de ser invisível (mesmas
pastas XDG, nenhum kwarg extra no Popen); o comportamento do Windows é
simulado trocando plat.IS_WIN, o que cobre as funções puras. O que só o
Windows de verdade prova (CREATE_NO_WINDOW existir, rg.exe real) roda quando
os.name == "nt" — no CI windows-latest e na VM.
"""
import os, shutil, stat, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, plat as P

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

REAL_WIN = os.name == "nt"


class como_windows:
    """Simula o Windows nas funções puras de plat (não toca no os.name)."""
    def __enter__(self):
        self.antes = P.IS_WIN; P.IS_WIN = True; return self
    def __exit__(self, *a):
        P.IS_WIN = self.antes


# ---------------------------------------------------------- Linux intacto
if not REAL_WIN:
    ok(P.popen_flags() == {} and P.popen_flags(nice_io=True) == {},
       "Linux: popen_flags() vazio (nenhum Popen muda)")
    antes = os.environ.get("XDG_CONFIG_HOME"), os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CONFIG_HOME"] = "/tmp/xc"; os.environ["XDG_CACHE_HOME"] = "/tmp/xk"
    ok(P.config_dir() == "/tmp/xc/sombrero-file-search", f"Linux: config segue XDG_CONFIG_HOME na hora ({P.config_dir()})")
    ok(P.cache_dir() == "/tmp/xk/sombrero-file-search", f"Linux: cache segue XDG_CACHE_HOME na hora ({P.cache_dir()})")
    ok(P.rga_user_config() == "/tmp/xc/ripgrep-all/config.jsonc", "Linux: config do rga no mesmo lugar de antes")
    for k, v in zip(("XDG_CONFIG_HOME", "XDG_CACHE_HOME"), antes):
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    ok(P.exe_candidates("rg") == ["rg"], "Linux: binário sem extensão")
    ok(P.longpath("/x" * 300) == "/x" * 300, "Linux: longpath é identidade")
    ok(P.background_mode() is False, "Linux: background_mode não se aplica (cli usa nice+ionice)")
    ok(P.disks().__name__.endswith("disks"), "Linux: plat.disks() é o módulo disks real")

# -------------------------------------------------- Windows (funções puras)
with como_windows():
    ok(P.exe_candidates("rg") == ["rg.exe", "rg"] and P.exe_candidates("rg.exe") == ["rg.exe"],
       "Windows: _which tenta rg.exe antes de rg")
    antes = {k: os.environ.get(k) for k in ("APPDATA", "LOCALAPPDATA")}
    os.environ["APPDATA"] = r"C:\Users\luca\AppData\Roaming"
    os.environ["LOCALAPPDATA"] = r"C:\Users\luca\AppData\Local"
    ok(P.config_dir() == os.path.join(r"C:\Users\luca\AppData\Roaming", "Sombrero File Search"),
       f"Windows: config em %APPDATA% ({P.config_dir()})")
    ok(P.cache_dir() == os.path.join(r"C:\Users\luca\AppData\Local", "Sombrero File Search"),
       "Windows: cache em %LOCALAPPDATA%")
    ok(P.rga_user_config() == os.path.join(r"C:\Users\luca\AppData\Roaming", "ripgrep-all", "config.jsonc"),
       "Windows: config do rga em %APPDATA%\\ripgrep-all")
    for k, v in antes.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    ok(P.displaypath("\\\\?\\C:\\a\\b") == "C:\\a\\b" and
       P.displaypath("\\\\?\\UNC\\srv\\share\\x") == "\\\\srv\\share\\x" and
       P.displaypath("C:\\a") == "C:\\a",
       "Windows: displaypath tira \\\\?\\ e \\\\?\\UNC\\")
    curto = "C:\\" + "a" * 50
    ok(P.longpath(curto) == curto, "Windows: caminho curto não ganha prefixo")
    ja = "\\\\?\\C:\\" + "a" * 300
    ok(P.longpath(ja) == ja, "Windows: prefixo não é duplicado")

# --------------------------------------- _which acha o binário empacotado .exe
tmp = tempfile.mkdtemp(prefix="sfs_plat_")
try:
    bindir = os.path.join(tmp, "bin"); os.makedirs(bindir)
    exe = os.path.join(bindir, "sfsfalso.exe")
    with open(exe, "w") as f:
        f.write("")
    os.chmod(exe, 0o755)
    apps = E._APP_BINS
    E._APP_BINS = [bindir]
    try:
        with como_windows():
            ok(E._which("sfsfalso") == exe, "Windows: _which acha bin/sfsfalso.exe pelo nome sem extensão")
        if not REAL_WIN:
            ok(E._which("sfsfalso") is None, "Linux: _which não inventa o .exe")
        os.makedirs(os.path.join(bindir, "sfsdirfalso.exe"))
        with como_windows():
            ok(E._which("sfsdirfalso") is None, "_which ignora diretório com nome de binário")
    finally:
        E._APP_BINS = apps
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------- leitor de documentos no exe congelado
cfg = E.rga_config({})
if cfg is not None:
    nosso = [a for a in cfg["custom_adapters"] if a.get("name") == E._RGA_ADAPTADOR][0]
    ok(nosso["args"][0] == "-I", "não congelado: leitor roda como python -I docs_text.py")
    sys.frozen = True
    try:
        nosso = [a for a in E.rga_config({})["custom_adapters"] if a.get("name") == E._RGA_ADAPTADOR][0]
        ok(nosso["args"] == ["--docs-adapter", "$input_file_extension"] and nosso["binary"] == sys.executable,
           "congelado: leitor é o modo --docs-adapter do próprio executável")
    finally:
        del sys.frozen

# ------------------------- CRLF: rg e fallback Python concordam nas âncoras
# (CI windows-latest 02/10/2026: `laudo$` sumia com todo arquivo CRLF no rg)
if E.RG:
    tmp = tempfile.mkdtemp(prefix="sfs_crlf_")
    try:
        with open(os.path.join(tmp, "crlf.txt"), "wb") as f:
            f.write(b"laudo\r\nfim\r\n")
        with open(os.path.join(tmp, "lf.txt"), "wb") as f:
            f.write(b"laudo\nfim\n")
        for pad in ("laudo$", "^fim$"):
            q = E.Query(paths=[tmp], content=pad, content_is_regex=True)
            a = []; E.search(q, a.append)
            rg = E.RG; E.RG = ""
            try:
                b = []; E.search(q, b.append)
            finally:
                E.RG = rg
            ra = sorted((os.path.basename(m.path), m.lines) for m in a)
            rb = sorted((os.path.basename(m.path), m.lines) for m in b)
            ok(ra == rb and len(ra) == 2, f"CRLF: '{pad}' acha os 2 arquivos no rg e no Python ({ra} | {rb})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ----------------------- profundidade do fallback Python conta o separador do SO
ok(E._nivel(os.path.join("a", "b", "c")) == 2 and E._nivel(os.path.join("a", "b") + os.sep) == 1,
   "_nivel conta os.sep (no Windows contava '/' e --max-depth sumia no fallback)")

# ------------------------------------------------------- só no Windows real
if REAL_WIN:
    fl = P.popen_flags()
    ok(fl.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW, "Windows real: CREATE_NO_WINDOW em todo motor")
    ok(P.popen_flags(nice_io=True)["creationflags"] & subprocess.BELOW_NORMAL_PRIORITY_CLASS,
       "Windows real: --nice-io baixa a prioridade dos filhos")
    ok(bool(E.RG) and E.RG.lower().endswith(".exe"), f"Windows real: rg.exe encontrado ({E.RG})")
    ok(bool(E.FD) and E.FD.lower().endswith(".exe"), f"Windows real: fd.exe encontrado ({E.FD})")
    ok(P.config_dir().endswith("Sombrero File Search"), f"Windows real: config ({P.config_dir()})")

print(f"\n{'FALHOU: ' + '; '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
