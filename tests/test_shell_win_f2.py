#!/usr/bin/env python3
"""F2 do SFS para Windows: operações de arquivo e shell (03/10/2026).

Roda no Linux e no Windows. O risco que esta fase fecha: no Windows a caixa não
distingue pasta, então "copiar C:\\Fotos para c:\\fotos\\backup" é copiar uma
pasta para dentro dela mesma — o preflight comparava texto e deixava passar.
O shell_win (Abrir com / Mostrar na pasta) só se prova num Windows de verdade.
"""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, fileops as F, plat as P, shell_win as SW

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

REAL_WIN = os.name == "nt"
tmp = tempfile.mkdtemp(prefix="sfs_f2_")
try:
    src = os.path.join(tmp, "Fotos")
    os.makedirs(os.path.join(src, "Ferias"))
    with open(os.path.join(src, "Ferias", "a.jpg"), "wb") as f:
        f.write(b"x" * 10)

    # ------------------------------------------------ laço: pasta em si mesma
    pf = F.preflight([src], os.path.join(src, "Ferias"))
    ok(any(r == F.SKIP_LOOP for _, r in pf.errors), "destino dentro da origem é recusado")
    ok(P.same_or_under(os.path.join(src, "x"), src) and P.same_or_under(src, src),
       "same_or_under: dentro e igual")
    ok(not P.same_or_under(src + "2", src), "same_or_under: prefixo de nome não é 'dentro'")
    raiz = os.path.splitdrive(tmp)[0] + os.sep       # o volume do tmp (no CI, C:; o cwd é D:)
    ok(P.same_or_under(tmp, raiz), f"same_or_under: tudo está sob a raiz do volume ({raiz})")

    if REAL_WIN:
        pf = F.preflight([src], os.path.join(src.upper(), "FERIAS"))
        ok(any(r == F.SKIP_LOOP for _, r in pf.errors),
           "Windows: destino com outra caixa (FOTOS\\FERIAS) também é recusado")
        pf = F.preflight([src.lower()], os.path.join(src, "Ferias", "novo"))
        ok(any(r == F.SKIP_LOOP for _, r in pf.errors),
           "Windows: origem em minúsculas, destino em caixa original: recusado")
        ok(P.path_key(src.upper()) == P.path_key(src), "Windows: path_key ignora caixa")
        ok(P.path_key(src.replace("\\", "/")) == P.path_key(src), "Windows: path_key aceita '/'")
        # destino é irmão da origem, dentro do pai: o walk não pode descer no destino
        pf = F.preflight([tmp], os.path.join(tmp.upper(), "FOTOS"))
        ok(any(r == F.SKIP_LOOP for _, r in pf.errors) or
           not any(e.src.lower().startswith(src.lower() + "\\") for e in pf.entries),
           "Windows: walk não desce no destino com outra caixa")
    else:
        ok(not P.same_or_under(src.upper(), src),
           "Linux: caixa distingue pasta (FOTOS ≠ Fotos), como sempre")

    # ------------------------- link de PASTA num destino sem symlink: pulado
    alvo = os.path.join(tmp, "alvo_dir"); os.makedirs(alvo)
    with open(os.path.join(alvo, "f.txt"), "w") as f:
        f.write("x")
    org = os.path.join(tmp, "org"); os.makedirs(org)
    try:
        os.symlink(alvo, os.path.join(org, "atalho"), target_is_directory=True)
        tem_link = True
    except OSError:                                    # Windows sem privilégio
        tem_link = False
        print("~skip  link de pasta: este usuário não cria symlink")
    if tem_link:
        dst = os.path.join(tmp, "dst"); os.makedirs(dst)
        caps_reais = F.disks.dest_caps
        def sem_symlink(d):
            c = caps_reais(d); c.symlinks = False; return c
        F.disks.dest_caps = sem_symlink
        try:
            pf = F.preflight([org], dst)
            ok(pf.links_dir and not pf.links_degraded, "preflight: link de pasta vai p/ links_dir, não vira 'cópia'")
            res = F.copy_to([org], dst)
            ok(not res.failed and any(r == F.SKIP_SYMLINK for _, r in res.skipped),
               f"cópia: link de pasta é PULADO com motivo, não falha (failed={res.failed})")
        finally:
            F.disks.dest_caps = caps_reais

    # -------------------------------------------- motor: raiz × achado
    if REAL_WIN:
        ok(E._sob(r"C:\Users\luca\a.txt", r"c:\users") and E._sob_ou_igual(r"c:\USERS", "C:\\Users\\"),
           "Windows: motor atribui achado à raiz sem ligar para caixa")
        ok(E._sob("C:/Users/luca/a.txt", r"C:\Users"), "Windows: motor aceita '/' na raiz digitada")
    else:
        ok(E._sob("/home/x/a", "/home") and not E._sob("/Home/x/a", "/home"),
           "Linux: _sob segue sensível a caixa")
        ok(E._sob_ou_igual("/home/", "/home") and E._sob_ou_igual("/a", "/"),
           "Linux: _sob_ou_igual cobre barra final e a raiz /")
    counts, attribute = E._atribuidor(["/", "/home"] if not REAL_WIN else ["C:\\", r"C:\Users"])
    attribute("/home/x" if not REAL_WIN else r"c:\users\x")
    ok(counts[("/home" if not REAL_WIN else r"C:\Users")] == 1,
       "atribuidor: a raiz mais específica leva o achado")

    # ------------------------------------------------------------ shell_win
    if not REAL_WIN:
        ok(SW.apps_for("/tmp/a.txt") == [] and SW.reveal(["/tmp"]) is False,
           "Linux: shell_win importa e não faz nada")
        ok(P.shell().__name__.endswith("xdg"), "Linux: plat.shell() é o xdg")
    else:
        ok(P.shell().__name__.endswith("shell_win"), "Windows: plat.shell() é o shell_win")
        txt = os.path.join(tmp, "nota.txt")
        open(txt, "w").close()
        apps = SW.apps_for(txt)
        nomes = [a.name for a in apps]
        ok(len(apps) >= 1, f"Windows: 'Abrir com' de .txt lista apps ({nomes})")
        ok(any("notepad" in a.key.lower() or "bloco" in a.name.lower()
               or "notepad" in a.name.lower() for a in apps),
           "Windows: o Bloco de Notas está entre eles")
        ok(SW.apps_for(os.path.join(tmp, "semextensao")) == [],
           "Windows: sem extensão → lista vazia (GUI oferece a caixa nativa)")
        falso = SW.WinApp("C:\\nao\\existe.exe", "Fantasma", ".txt")
        ok(SW.launch(falso, [txt]) is False, "Windows: launch de app que sumiu → False, sem exceção")
        ok(SW.reveal([os.path.join(tmp, "nao_existe", "x.txt")]) is False,
           "Windows: reveal de caminho inexistente → False")
        ok(SW.mime_for(tmp) == "inode/directory" and SW.mime_for(txt) == "text/plain",
           "Windows: mime_for")
        ok(SW.launch_command("   ", [txt]) is False, "Windows: comando vazio não lança nada")

    # ------------------------------------- URI de arquivo (abrir, clipboard)
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lfs"))
        import app as A
    except ImportError:
        A = None
        print("~skip URI: sem PySide6 aqui (roda no CI)")
    if A is not None and REAL_WIN:
        casos = [(r"C:\Users\Luca\Fotos 1\á#.jpg", "file:///C:/Users/Luca/Fotos%201/%C3%A1%23.jpg"),
                 (r"\\nas\share\x y.txt", "file://nas/share/x%20y.txt")]
        for cam, uri in casos:
            ok(A.path_to_uri(cam) == uri, f"Windows: path_to_uri({cam!r}) = {A.path_to_uri(cam)}")
            ok(os.path.normcase(A.url_local(cam).toLocalFile().replace("/", "\\")) == os.path.normcase(cam),
               f"Windows: url_local({cam!r}) volta ao mesmo caminho")
        md = A.build_paths_mime([src])
        ok(md.hasUrls() and not md.hasFormat("x-special/gnome-copied-files"),
           "Windows: clipboard leva URLs (CF_HDROP), sem formatos do GNOME/KDE")
    elif A is not None:
        ok(A.path_to_uri("/tmp/a b") == "file:///tmp/a%20b", "Linux: path_to_uri inalterado")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
