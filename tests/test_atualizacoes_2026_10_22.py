#!/usr/bin/env python3
"""Atualizações (22/10/2026): aviso de release nova + botão de upgrade.

Contratos presos aqui (decisões do Rodrigo, ver lfs/updates.py):
  1. só RELEASE estável conta: tag com sufixo ('-windows', '-rc1') não é versão;
  2. a consulta automática roda no máximo 1×/dia, respeita o "desligado" e
     some em silêncio sem rede — só a consulta pedida na mão mostra o erro;
  3. cada instalação recebe o SEU pacote; worktree com .git nunca se atualiza;
  4. download cortado ou com sha256 errado NUNCA substitui o arquivo bom;
  5. AppImage troca o próprio arquivo mantendo o nome; código-fonte roda o
     install.sh da release com --app-only e o PREFIX atual.

Sem rede e sem tela: as "releases" são arquivos locais servidos por file://.

Rode:
    python3 tests/test_atualizacoes_2026_10_22.py
"""
from __future__ import annotations
import hashlib, io, os, stat, subprocess, sys, tarfile, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import updates, version

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

def url(p):
    return "file://" + p

tmp = tempfile.mkdtemp(prefix="sfs-test-upd-")

# ---------------------------------------------------------------- 1. versões
ok(updates.parse("v1.2.0") == (1, 2, 0), "parse('v1.2.0')")
ok(updates.parse("1.10.3") == (1, 10, 3), "parse sem 'v'")
ok(updates.parse("v1.2.0-windows") is None, "tag com sufixo não é versão")
ok(updates.parse("") is None, "tag vazia não é versão")
ok(updates.is_newer("v1.10.0", "1.9.9"), "1.10.0 > 1.9.9 (numérico, não texto)")
ok(not updates.is_newer("v1.2.0", "1.2.0"), "mesma versão não é atualização")
ok(not updates.is_newer("v1.1.0", "1.2.0"), "versão mais velha não é atualização")
ok(not updates.is_newer("v9.0.0-rc1", "1.2.0"), "pré-release nunca aciona aviso")

# ---------------------------------------------------------------- 3. tipo de instalação
dev = os.path.join(tmp, "dev"); os.makedirs(os.path.join(dev, ".git"))
src = os.path.join(tmp, "src"); os.makedirs(src)
img = os.path.join(tmp, "Sombrero.AppImage"); open(img, "wb").close()
ok(updates.install_kind(dev, env={}) == "dev", "worktree com .git = dev")
ok(updates.install_kind(src, env={}) == "source", "cópia do install.sh = source")
ok(updates.install_kind("/usr/lib/sombrero-file-search", env={}) == "deb", "/usr/lib = deb")
ok(updates.install_kind("/usr/lib/sombrero-file-search", env={"APPIMAGE": img}) == "appimage",
   "$APPIMAGE vence o caminho")
ok(updates.install_kind(src, env={"APPIMAGE": "/nao/existe"}) == "source",
   "$APPIMAGE apontando para o nada é ignorado")

# ---------------------------------------------------------------- 2. consulta 1×/dia
def rel(tag, assets=(), tarball=""):
    return {"tag": tag, "name": tag, "page": "", "notes": "", "published": "",
            "tarball": tarball, "assets": list(assets)}

nova = "v%d.0.0" % (updates.parse(version.RELEASE)[0] + 1)
chamadas = []
def fetch_nova():
    chamadas.append(1); return rel(nova)
def fetch_sem_rede():
    chamadas.append(1); raise OSError("network down")

cfg = {}
r = updates.check(cfg, now=1000, fetch=fetch_nova)
ok(r and r["tag"] == nova and len(chamadas) == 1, "1ª consulta acha a release nova")
r = updates.check(cfg, now=1000 + 3600, fetch=fetch_nova)
ok(r and len(chamadas) == 1, "dentro de 24 h reaproveita a consulta (sem rede)")
r = updates.check(cfg, now=1000 + updates.CHECK_EVERY + 1, fetch=fetch_nova)
ok(len(chamadas) == 2, "depois de 24 h consulta de novo")
cfg["updates"]["auto"] = False
r = updates.check(cfg, now=10 ** 9, fetch=fetch_nova)
ok(r is None and len(chamadas) == 2, "automático desligado: nem consulta")
r = updates.check(cfg, force=True, now=10 ** 9, fetch=fetch_nova)
ok(r and len(chamadas) == 3, "'Verificar agora' consulta mesmo desligado")
cfg2 = {}
ok(updates.check(cfg2, now=5, fetch=fetch_sem_rede) is None, "sem rede, automático: silêncio")
ok("last_check" not in cfg2["updates"], "falha de rede não conta como consulta do dia")
try:
    updates.check(cfg2, force=True, fetch=fetch_sem_rede); ok(False, "erro na consulta manual")
except OSError:
    ok(True, "sem rede, manual: o erro chega a quem pediu")
ok(updates.check({}, now=1, fetch=lambda: rel(version.RELEASE)) is None,
   "release igual à instalada: nada a fazer")

# ---------------------------------------------------------------- 3. o pacote certo
assets = [{"name": "Sombrero_File_Search-1.3.0-x86_64.AppImage", "url": "a", "size": 1, "digest": ""},
          {"name": "sombrero-file-search_1.3.0_all.deb", "url": "d", "size": 1, "digest": ""},
          {"name": "SombreroFileSearch-windows-x64.zip", "url": "w", "size": 1, "digest": ""}]
R = rel("v1.3.0", assets, tarball="t")
ok(updates.pick_asset("appimage", R)["url"] == "a", "AppImage pega o .AppImage")
ok(updates.pick_asset("deb", R)["url"] == "d", ".deb pega o _all.deb")
ok(updates.pick_asset("windows", R)["url"] == "w", "Windows pega o zip do Windows")
ok(updates.pick_asset("source", R)["url"] == "t", "código-fonte pega o tarball da release")
# O .deb é por arquitetura desde o rga embutido (amd64/arm64): procurar só o
# `_all.deb` deixava quem usa .deb sem botão a partir da v1.3.0.
R2 = rel("v1.3.0", [{"name": "sombrero-file-search_1.3.0_arm64.deb", "url": "arm", "size": 1, "digest": ""},
                    {"name": "sombrero-file-search_1.3.0_amd64.deb", "url": "amd", "size": 1, "digest": ""}])
ok((updates.pick_asset("deb", R2, arch="amd64") or {}).get("url") == "amd", ".deb amd64 pega o _amd64.deb")
ok((updates.pick_asset("deb", R2, arch="arm64") or {}).get("url") == "arm", ".deb arm64 pega o _arm64.deb")
ok(updates.pick_asset("deb", R2, arch="riscv64") is None, "arquitetura sem pacote: sem botão")
ok(updates.deb_arch("x86_64") == "amd64" and updates.deb_arch("aarch64") == "arm64",
   "nome da máquina -> arquitetura do Debian")
ok(not updates.can_apply("dev", R), "dev nunca tem botão")
ok(not updates.can_apply("appimage", rel("v1.3.0")), "release sem AppImage: sem botão no AppImage")

# ---------------------------------------------------------------- 4. download à prova de corte
dados = os.urandom(200_000)
pub = os.path.join(tmp, "pub.bin"); open(pub, "wb").write(dados)
sha = "sha256:" + hashlib.sha256(dados).hexdigest()
dest = os.path.join(tmp, "baixado.bin")
updates.download(url(pub), dest, size=len(dados), digest=sha)
ok(open(dest, "rb").read() == dados and not os.path.exists(dest + ".part"),
   "download íntegro: arquivo final e nenhum .part")
for nome, kw in (("tamanho errado", dict(size=len(dados) + 1)),
                 ("sha256 errado", dict(size=len(dados), digest="sha256:" + "0" * 64))):
    d2 = os.path.join(tmp, "ruim-" + nome.replace(" ", "_"))
    try:
        updates.download(url(pub), d2, **kw); ok(False, nome + " deveria falhar")
    except updates.UpdateError:
        ok(not os.path.exists(d2) and not os.path.exists(d2 + ".part"),
           nome + ": falha e não deixa arquivo nenhum")
d3 = os.path.join(tmp, "cancelado")
try:
    updates.download(url(pub), d3, cancelled=lambda: True); ok(False, "cancelar")
except InterruptedError:
    ok(not os.path.exists(d3 + ".part"), "cancelado: .part apagado")

# ---------------------------------------------------------------- 5a. AppImage
velho = os.path.join(tmp, "Meu_SFS.AppImage"); open(velho, "wb").write(b"velho")
novo = os.path.join(tmp, "novo.AppImage"); open(novo, "wb").write(b"#!novo")
R = rel("v9.9.9", [{"name": "Sombrero_File_Search-9.9.9-x86_64.AppImage", "url": url(novo),
                    "size": 6, "digest": ""}])
res = updates.apply("appimage", R, env={"APPIMAGE": velho})
ok(open(velho, "rb").read() == b"#!novo", "AppImage: conteúdo trocado")
ok(os.stat(velho).st_mode & stat.S_IXUSR, "AppImage: continua executável")
ok(res["restart"] == [velho], "AppImage: relança pelo MESMO caminho (atalhos continuam valendo)")
R["assets"][0]["size"] = 999
open(velho, "wb").write(b"bom")
try:
    updates.apply("appimage", R, env={"APPIMAGE": velho}); ok(False, "AppImage truncado")
except updates.UpdateError:
    ok(open(velho, "rb").read() == b"bom", "AppImage truncado NÃO substitui o bom")

# ---------------------------------------------------------------- 5b. código-fonte
tgz = os.path.join(tmp, "rel.tar.gz")
script = b'#!/bin/bash\nprintf "%s|%s" "$*" "$PREFIX" > "$PREFIX/marca"\n'
with tarfile.open(tgz, "w:gz") as tf:
    ti = tarfile.TarInfo("Thiopental1976-sombrero-file-search-abc123/install.sh")
    ti.size = len(script); ti.mode = 0o755
    tf.addfile(ti, io.BytesIO(script))
prefix = os.path.join(tmp, "prefix"); os.makedirs(prefix)
res = updates.apply("source", rel("v9.9.9", tarball=url(tgz)), root=prefix, env=dict(os.environ))
marca = open(os.path.join(prefix, "marca")).read()
ok(marca == "-y --app-only|" + prefix, "código-fonte: install.sh -y --app-only com o PREFIX atual")
ok(res["restart"][-1] in (os.path.join(prefix, "lfs", "app.py"),
                          os.path.expanduser("~/.local/bin/sombrero-file-search")),
   "código-fonte: relança pelo lançador (ou o app.py instalado)")
mau = os.path.join(tmp, "mau.tar.gz")
with tarfile.open(mau, "w:gz") as tf:
    ti = tarfile.TarInfo("../fora.sh"); ti.size = 1
    tf.addfile(ti, io.BytesIO(b"x"))
try:
    updates.apply("source", rel("v9.9.9", tarball=url(mau)), root=prefix, env=dict(os.environ))
    ok(False, "tarball com '..'")
except Exception:
    ok(not os.path.exists(os.path.join(tmp, "fora.sh")), "tarball com '..' é recusado")

# ---------------------------------------------------------------- install.sh --app-only
out = subprocess.run(["bash", os.path.join(RAIZ, "install.sh"), "--help"],
                     capture_output=True, text=True).stdout
ok("--app-only" in out, "install.sh --help documenta --app-only")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S)")
    sys.exit(1)
print("tudo ok")
