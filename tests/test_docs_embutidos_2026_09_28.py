#!/usr/bin/env python3
"""Modo documentos sem pandoc e com o rga dos pacotes (28/09/2026).

Campo: no ServidorCedro o modo documentos sumiu — o rga era embutido na pasta
do app antigo e o .deb não o traz. Decisão do Rodrigo: rga embutido nos pacotes,
e docx/odt/epub lidos pelo PRÓPRIO SFS (o pandoc tem ~160–200 MB).

1. lfs/docs_text.py extrai docx/odt/epub: parágrafo por linha, cabeçalho e
   nota de rodapé, sem texto apagado, sem caixa de texto em dobro, espaço do
   ODF colapsado, ordem de leitura do epub (spine), e ERRO — nunca texto
   parcial — em zip inválido ou membro grande demais.
2. engine.rga_config: o adaptador do SFS entra no config do rga SEM apagar os
   adaptadores do usuário (que vêm na frente); config ilegível = não mexer.
3. engine._which acha binário na pasta bin/ ao lado de lfs/ (.deb, AppImage).
4. engine.rga_env põe no PATH a pasta do rg (o rga só o procura no PATH).
5. Ponta a ponta (se houver rga): busca -D em docx/odt/epub com PATH sem pandoc.
   No código antigo: 0 arquivos + "incomplete".
Rode:  python3 tests/test_docs_embutidos_2026_09_28.py
"""
from __future__ import annotations
import io, json, os, shutil, subprocess, sys, tempfile, zipfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)
import engine, docs_text                                     # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

def zipa(membros: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in membros.items():
            z.writestr(n, c)
    return b.getvalue()

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
DOCX = zipa({
    "word/document.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document {W}><w:body>
  <w:p><w:r><w:t>Laudo de </w:t></w:r><w:r><w:t>ultrassonografia</w:t></w:r></w:p>
  <w:p><w:r><w:t>Fígado</w:t><w:tab/><w:t>normal</w:t></w:r>
       <w:del><w:r><w:delText>APAGADO</w:delText></w:r></w:del></w:p>
  <w:p><w:r><mc:AlternateContent><mc:Choice><w:p><w:r><w:t>caixa de texto</w:t></w:r></w:p></mc:Choice>
       <mc:Fallback><w:p><w:r><w:t>caixa de texto</w:t></w:r></w:p></mc:Fallback></mc:AlternateContent></w:r></w:p>
</w:body></w:document>""",
    "word/header1.xml": f'<w:hdr {W}><w:p><w:r><w:t>Cabeçalho da clínica</w:t></w:r></w:p></w:hdr>',
    "word/footnotes.xml": f'<w:footnotes {W}><w:footnote><w:p><w:r><w:t>nota zebrafoca</w:t></w:r></w:p></w:footnote></w:footnotes>',
})
T_ = 'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" ' \
     'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
ODT = zipa({
    "mimetype": "application/vnd.oasis.opendocument.text",
    "content.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {T_}><office:body><office:text>
    <text:h>Título</text:h>
    <text:p>três<text:s text:c="3"/>espaços e
      quebra literal</text:p>
    <text:p>antes da nota<text:note><text:note-citation>1</text:note-citation><text:note-body><text:p>corpo da nota</text:p></text:note-body></text:note> depois</text:p>
</office:text></office:body></office:document-content>""",
})
EPUB = zipa({
    "mimetype": "application/epub+zip",
    "META-INF/container.xml": '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                              '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
    "OEBPS/content.opf": '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
                         '<item id="a" href="z_primeiro.xhtml"/><item id="b" href="a_segundo.xhtml"/>'
                         '</manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>',
    "OEBPS/z_primeiro.xhtml": '<html><head><title>NAO</title><style>p{}</style></head>'
                              '<body><p>Primeiro &amp; capítulo</p><script>NAO()</script></body></html>',
    "OEBPS/a_segundo.xhtml": '<html><body><div><p>Segundo   capítulo</p></div></body></html>',
})

T = tempfile.mkdtemp(prefix="sfs_docs_")
try:
    # ------------------------------------------------------------ 1. extração
    d = docs_text.extrai(DOCX, "docx").splitlines()
    ok(d[:2] == ["Laudo de ultrassonografia", "Fígado\tnormal"], f"docx: parágrafo por linha, tab ({d[:2]})")
    ok("APAGADO" not in "\n".join(d), "docx: texto apagado (controle de alterações) fica fora")
    ok(d.count("caixa de texto") == 1, f"docx: caixa de texto uma vez só, não em dobro ({d})")
    ok("Cabeçalho da clínica" in d and "nota zebrafoca" in d, "docx: cabeçalho e nota de rodapé entram")

    o = docs_text.extrai(ODT, "odt").splitlines()
    ok(o[0] == "Título", "odt: título")
    ok(o[1] == "três   espaços e quebra literal", f"odt: <text:s c=3> vale 3; quebra literal vira espaço ({o[1]!r})")
    ok(o[2] == "antes da nota depois" and o[-1] == "corpo da nota",
       f"odt: nota vai para o fim, sem partir a frase ({o})")

    e = docs_text.extrai(EPUB, "epub").splitlines()
    ok(e == ["Primeiro & capítulo", "Segundo capítulo"], f"epub: ordem do spine, sem head/script ({e})")

    for dados, ext, o_que in ((b"isto nao e zip", "docx", "zip inválido"),
                              (zipa({"x.txt": "a"}), "docx", "zip sem word/document.xml"),
                              (zipa({"x.txt": "a"}), "epub", "epub sem capítulo")):
        try:
            docs_text.extrai(dados, ext); ok(False, f"{o_que}: deveria ser erro")
        except docs_text.ErroDocumento:
            ok(True, f"{o_que}: erro, não texto vazio")
    antigo = docs_text.MAX_MEMBRO
    docs_text.MAX_MEMBRO = 100
    try:
        docs_text.extrai(DOCX, "docx"); ok(False, "membro acima do teto deveria ser erro")
    except docs_text.ErroDocumento:
        ok(True, "membro acima do teto: erro, não corte calado")
    finally:
        docs_text.MAX_MEMBRO = antigo

    # pelo stdin, como o rga chama
    r = subprocess.run([sys.executable, "-I", os.path.join(LFS, "docs_text.py"), "odt"],
                       input=ODT, capture_output=True)
    ok(r.returncode == 0 and "corpo da nota" in r.stdout.decode(), "docs_text.py: stdin -> stdout, rc 0")
    r = subprocess.run([sys.executable, "-I", os.path.join(LFS, "docs_text.py"), "docx"],
                       input=b"lixo", capture_output=True)
    ok(r.returncode == 1 and b"sombrero docs_text" in r.stderr, "docs_text.py: falha = rc 1 + causa no stderr")

    # ------------------------------------------------------------ 2. config do rga
    deles = {"name": "meu", "description": "d", "version": 1, "extensions": ["xyz"], "binary": "cat", "args": []}
    cfg = engine.rga_config({"$schema": "./x.json", "cache_max_blob_len": 1000, "custom_adapters": [deles]})
    nomes = [a["name"] for a in cfg["custom_adapters"]]
    ok(nomes == ["meu", "sombrero_docs"], f"adaptador do usuário preservado e NA FRENTE ({nomes})")
    ok(cfg.get("cache_max_blob_len") == 1000 and "$schema" not in cfg, "opções do usuário ficam; $schema relativo sai")
    nosso = cfg["custom_adapters"][-1]
    ok(nosso["version"] == docs_text.VERSAO and set(nosso["extensions"]) == {"docx", "odt", "epub"},
       "adaptador: versão do leitor (chave do cache) e as 3 extensões")
    ok(nosso["args"][0] == "-I" and nosso["args"][1].endswith("docs_text.py"), "adaptador roda o leitor isolado (-I)")

    xdg = os.path.join(T, "xdg"); os.makedirs(os.path.join(xdg, "ripgrep-all"))
    velho = os.environ.get("XDG_CONFIG_HOME"); os.environ["XDG_CONFIG_HOME"] = xdg
    try:
        with open(os.path.join(xdg, "ripgrep-all", "config.jsonc"), "w") as f:
            f.write('{\n // comentário\n "custom_adapters": [ /* bloco */ {"name":"url","description":"http://x//y",'
                    '"version":1,"extensions":["q"],"binary":"cat","args":[]} ]\n}\n')
        u = engine._rga_config_usuario()
        ok(u is not None and u["custom_adapters"][0]["description"] == "http://x//y",
           "JSONC: comentários saem, '//' dentro de string fica")
        with open(os.path.join(xdg, "ripgrep-all", "config.jsonc"), "w") as f:
            f.write('{ isto não é json')
        ok(engine._rga_config_usuario() is None and engine.rga_config() is None,
           "config do usuário ilegível: o SFS não passa config nenhuma (não atropela)")
        os.remove(os.path.join(xdg, "ripgrep-all", "config.jsonc"))
        ok(engine._rga_config_usuario() == {}, "sem config do usuário: {}")
    finally:
        if velho is None: os.environ.pop("XDG_CONFIG_HOME", None)
        else: os.environ["XDG_CONFIG_HOME"] = velho

    cache = os.path.join(T, "cache_cfg"); velho_c = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = cache; engine._rga_args_cache = None
    try:
        a1 = engine.rga_args()
        ok(len(a1) == 1 and os.path.isfile(a1[0].split("=", 1)[1]), f"rga_args grava o config no cache ({a1})")
        os.remove(a1[0].split("=", 1)[1])
        a2 = engine.rga_args()
        ok(a2 == a1 and os.path.isfile(a2[0].split("=", 1)[1]),
           "config apagado do cache no meio da sessão: é recriado, não fica apontando para o nada")
    finally:
        engine._rga_args_cache = None
        if velho_c is None: os.environ.pop("XDG_CACHE_HOME", None)
        else: os.environ["XDG_CACHE_HOME"] = velho_c

    # ------------------------------------------------------------ 3. bin/ ao lado de lfs/
    ok(os.path.realpath(engine._APP_BINS[0]) == os.path.realpath(os.path.join(RAIZ, "bin")),
       "primeira pasta de binário empacotado = bin/ ao lado de lfs/")
    fake = os.path.join(T, "pkgbin"); os.makedirs(fake)
    exe = os.path.join(fake, "sfs-sonda-inexistente")
    with open(exe, "w") as f: f.write("#!/bin/sh\n")
    os.chmod(exe, 0o755)
    engine._APP_BINS.insert(0, fake)
    try:
        ok(engine._which("sfs-sonda-inexistente") == exe, "_which acha binário que só existe na pasta do pacote")
    finally:
        engine._APP_BINS.pop(0)

    # ------------------------------------------------------------ 4. rg no PATH do rga
    rg_orig = engine.RG
    engine.RG = os.path.join(T, "fora_do_path", "rg")
    try:
        env = engine.rga_env()
        ok(env is not None and env["PATH"].split(os.pathsep)[-1] == os.path.join(T, "fora_do_path"),
           "rg fora do PATH: a pasta dele entra no FIM do PATH do rga")
        engine.RG = shutil.which("sh")
        ok(engine.rga_env() is None, "rg já no PATH: ambiente herdado sem mudança")
    finally:
        engine.RG = rg_orig

    # ------------------------------------------------------------ 5. ponta a ponta
    rga = shutil.which("rga")
    rg = shutil.which("rg")
    if not (rga and rg):
        print("(pulado: sem rga/rg nesta máquina)")
    else:
        # rga COPIADO para uma pasta limpa: medido, o rga procura pandoc & cia
        # também na pasta dele — um rga ao lado de um pandoc falsearia o teste
        p = os.path.join(T, "path"); os.makedirs(p)
        for b in ("rga", "rga-preproc"):
            src = os.path.realpath(shutil.which(b) or os.path.join(os.path.dirname(os.path.realpath(rga)), b))
            shutil.copy2(src, os.path.join(p, b))
        for b in ("rg", "sh"):
            os.symlink(os.path.realpath(shutil.which(b)), os.path.join(p, b))
        docs = os.path.join(T, "docs"); os.makedirs(docs)
        for n, dados in (("a.docx", DOCX), ("b.odt", ODT), ("c.epub", EPUB)):
            with open(os.path.join(docs, n), "wb") as f: f.write(dados)
        env = dict(os.environ, PATH=p, XDG_CACHE_HOME=os.path.join(T, "cache"),
                   XDG_CONFIG_HOME=os.path.join(T, "sem_config"))
        def busca(termo):
            r = subprocess.run([sys.executable, os.path.join(LFS, "cli.py"), docs, "-D", "-c", termo, "-l"],
                               capture_output=True, text=True, env=env, timeout=120)
            return r, sorted(os.path.basename(l) for l in r.stdout.splitlines() if l.strip())
        r, achou = busca("capítulo")
        ok(achou == ["c.epub"], f"-D sem pandoc acha no epub ({achou}; {r.stderr[-200:]!r})")
        r, achou = busca("nota")
        ok(achou == ["a.docx", "b.odt"], f"-D sem pandoc acha no docx e no odt ({achou})")
        ok("incomplete" not in r.stderr, "sem aviso de incompleto (o leitor do SFS respondeu)")
        rb = subprocess.run([sys.executable, os.path.join(LFS, "cli.py"), docs, "-D", "-b", "nota AND clínica", "-l"],
                            capture_output=True, text=True, env=env, timeout=120)
        ok([os.path.basename(l) for l in rb.stdout.splitlines() if l.strip()] == ["a.docx"],
           f"booleano -D sem pandoc ({rb.stdout!r})")
finally:
    shutil.rmtree(T, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
