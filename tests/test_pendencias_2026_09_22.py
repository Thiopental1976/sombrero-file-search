#!/usr/bin/env python3
"""Pendências pequenas levantadas na atualização da documentação (§23.2, 22/09/2026).

1. `-i/--ignore-case` era aceito e ignorado → agora vence `-s`.
2. `human_error(context="eject")` não tinha cláusula → "The disk was not ejected."
3. `dupes.export` gravava direto no destino → temporário + os.replace.
5. `{"warn":"mount_dead"}` sem `reason`, e o texto dizia "not responding" também
   para montagem QUEBRADA → `reason` no JSON e "broken" no texto.
7. `--index` com várias raízes: a cobertura era checada raiz a raiz dentro do
   gerador — uma raiz íntegra imprimia resultados antes de a seguinte recusar.
Rode:  python3 tests/test_pendencias_2026_09_22.py
"""
from __future__ import annotations
import errno, json, os, shutil, subprocess, sys, tempfile, types

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LFS = os.path.join(RAIZ, "lfs")
sys.path.insert(0, LFS)
import engine, humane, dupes, indexed, i18n                   # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

T = tempfile.mkdtemp(prefix="sfs_pend_")
try:
    # ---------------------------------------------------------- 1. -i vence -s
    with open(os.path.join(T, "a.txt"), "w") as f:
        f.write("Laudo normal\n")
    def cli(*a):
        return subprocess.run([sys.executable, os.path.join(LFS, "cli.py"), *a],
                              capture_output=True, text=True, timeout=60)
    ok(cli(T, "-c", "laudo", "-s", "-l").returncode == 1, "-s sozinho: 'laudo' não casa 'Laudo'")
    r = cli(T, "-c", "laudo", "-s", "-i", "-l")
    ok(r.returncode == 0 and "a.txt" in r.stdout, "-i junto de -s: -i vence (antes era ignorado)")

    # ---------------------------------------------------------- 2. cláusula do ejetar
    i18n.set_lang("en")
    for e in (errno.ENOTCONN, errno.ENOSPC, errno.EBUSY):
        msg = humane.human_error(OSError(e, os.strerror(e)), context="eject", target="/media/PEN")
        ok(msg.endswith("The disk was not ejected."), f"ejetar ({errno.errorcode[e]}): {msg!r}")
    ok("The disk was not ejected." in humane.SOURCE_STRINGS, "frase nova entra na guarda de i18n")
    i18n.set_lang("pt")
    ok(humane.human_error(OSError(errno.EBUSY, "busy"), context="eject").endswith("O disco não foi ejetado."),
       "ejetar traduzido")
    i18n.set_lang(None)

    # ---------------------------------------------------------- 3. export atômico
    destino = os.path.join(T, "dup.csv")
    with open(destino, "w") as f:
        f.write("EXPORTAÇÃO ANTERIOR\n")
    g = types.SimpleNamespace(digest="ab", size=3, wasted=3, paths=["/a", "/b"])
    orig = dupes._export_para
    def quebra(groups, path, fmt):
        with open(path, "w") as f:
            f.write("pela metade")
        raise OSError(errno.ENOSPC, "No space left on device")
    dupes._export_para = quebra
    try:
        try:
            dupes.export([g], destino, "csv"); ok(False, "export com disco cheio deveria falhar")
        except OSError:
            pass
    finally:
        dupes._export_para = orig
    ok(open(destino).read() == "EXPORTAÇÃO ANTERIOR\n", "falha no meio NÃO destrói a exportação anterior")
    ok(not os.path.exists(destino + ".sombrero-part"), "falha no meio não deixa o temporário")
    dupes.export([g], destino, "csv")
    ok(open(destino).read().startswith("group,hash,size,path"), "export normal segue igual (vírgula)")

    # ---------------------------------------------------------- 5. reason no mount_dead
    envolto = os.path.join(T, "cli_com_morta.py")
    with open(envolto, "w") as f:
        f.write(f'''import sys; sys.path.insert(0, {LFS!r})
import engine
def falsa(q, on_result, cancel=None, on_progress=None, stats=None, on_event=None):
    stats.setdefault("skipped_mounts", []).append(
        {{"path": "/mnt/nas", "mount": "/mnt/nas", "fstype": "nfs", "reason": "broken_mount"}})
    return 0, 0.0
engine.search = falsa
sys.argv = ["cli.py"] + sys.argv[1:]
import runpy; runpy.run_path({os.path.join(LFS, "cli.py")!r}, run_name="__main__")
''')
    r = subprocess.run([sys.executable, envolto, T, "-n", "x", "--json"], capture_output=True, text=True, timeout=60)
    ev = [json.loads(l) for l in r.stdout.splitlines() if '"mount_dead"' in l]
    ok(ev and ev[0].get("reason") == "broken_mount", f"--json mount_dead traz reason ({ev})")
    r = subprocess.run([sys.executable, envolto, T, "-n", "x"], capture_output=True, text=True, timeout=60)
    ok("mount broken — skipped: /mnt/nas" in r.stderr, "texto diz 'broken' para montagem quebrada")

    # ---------------------------------------------------------- 7. --index pré-confere tudo
    boa, podada = os.path.join(T, "boa"), os.path.join(T, "podada")
    os.makedirs(boa); os.makedirs(podada)
    open(os.path.join(boa, "laudo.txt"), "w").close()
    conf = indexed.parse_updatedb_conf(f'PRUNEPATHS="{podada}"')
    q = engine.Query(paths=[boa, podada], name_patterns=["*laudo*"])
    saiu = []
    try:
        for m in indexed.search_indexed(q, conf=conf, mounts=[],
                                        _run=lambda a: (os.path.join(boa, "laudo.txt") + "\0").encode()):
            saiu.append(m.path)
        ok(False, "raiz podada deveria recusar")
    except indexed.IndexError_:
        pass
    ok(saiu == [], f"nenhum resultado sai antes da recusa ({saiu})")
    ok([m.path for m in indexed.search_indexed(engine.Query(paths=[boa], name_patterns=["*laudo*"]),
                                               conf=conf, mounts=[],
                                               _run=lambda a: (os.path.join(boa, "laudo.txt") + "\0").encode())]
       == [os.path.join(boa, "laudo.txt")], "raiz íntegra sozinha segue funcionando")
finally:
    shutil.rmtree(T, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
