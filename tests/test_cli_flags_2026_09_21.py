#!/usr/bin/env python3
"""CLI: --max-size, --depth e --follow (21/09/2026, item 7 do parecer do Fable).

A Query já suportava os três; a CLI não os expunha. Junto, a CLI deixa de
IGNORAR EM SILÊNCIO tamanho inválido: `--min-size 10X` rodava a busca sem
filtro nenhum (parse_size devolve None), e o usuário concluía que o filtro
valera. Agora é exit 2 com a frase do erro — o mesmo vale para o --max-size,
para mínimo > máximo e para --depth < 1. E `--index --follow` é recusado: o
plocate não segue symlink, então o índice omitiria em silêncio o que só se
alcança por link.

Tudo em tempdir, rodando o cli.py de verdade. Rode:
    python3 tests/test_cli_flags_2026_09_21.py
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CLI = os.path.join(RAIZ, "lfs", "cli.py")

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)


def sfs(*args):
    """Roda a CLI; devolve (rc, caminhos relativos ao tmp encontrados, stderr)."""
    p = subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True,
                       env=dict(os.environ, LANG="C.UTF-8"), timeout=120)
    achados = sorted(os.path.relpath(L, T) for L in p.stdout.splitlines()
                     if L.startswith(T))
    return p.returncode, achados, p.stderr


T = tempfile.mkdtemp(prefix="sfs_cliflags_")
FORA = tempfile.mkdtemp(prefix="sfs_cliflags_fora_")
try:
    def escreve(rel, dados, base=T):
        p = os.path.join(base, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(dados)
    escreve("a.txt", "laudo\n")                          # 6 B, profundidade 1
    escreve("grande.txt", "laudo\n" + "x" * 3000)        # ~3 KiB, profundidade 1
    escreve("sub/b.txt", "laudo\n")                      # profundidade 2
    escreve("sub/fundo/c.txt", "laudo\n")                # profundidade 3
    escreve("e.txt", "laudo\n", base=FORA)               # só se alcança pelo link
    os.symlink(FORA, os.path.join(T, "atalho"))

    todos = ["a.txt", "grande.txt", "sub/b.txt", "sub/fundo/c.txt"]

    # ------------------------------------------------------------ linha de base
    rc, ach, _ = sfs(T, "-n", "*.txt", "-l")
    ok(rc == 0 and ach == todos, f"sem flags: acha os 4 e NÃO segue o link ({ach})")

    # ------------------------------------------------------------ --max-size
    rc, ach, _ = sfs(T, "-n", "*.txt", "-l", "--max-size", "1K")
    ok(ach == ["a.txt", "sub/b.txt", "sub/fundo/c.txt"], f"--max-size 1K tira o grande ({ach})")
    rc, ach, _ = sfs(T, "-c", "laudo", "-l", "--max-size", "1K")
    ok("grande.txt" not in ach and "a.txt" in ach, f"--max-size vale na busca de CONTEÚDO ({ach})")
    rc, ach, _ = sfs(T, "-b", "laudo", "-l", "--max-size", "1K")
    ok("grande.txt" not in ach and "a.txt" in ach, f"--max-size vale no BOOLEANO ({ach})")
    rc, ach, _ = sfs(T, "-n", "*.txt", "-l", "--min-size", "1K", "--max-size", "1M")
    ok(ach == ["grande.txt"], f"--min-size + --max-size juntos ({ach})")

    # ------------------------------------------------------------ --depth
    rc, ach, _ = sfs(T, "-n", "*.txt", "-l", "--depth", "1")
    ok(ach == ["a.txt", "grande.txt"], f"--depth 1 = só a pasta dada ({ach})")
    rc, ach, _ = sfs(T, "-n", "*.txt", "-l", "--depth", "2")
    ok(ach == ["a.txt", "grande.txt", "sub/b.txt"], f"--depth 2 desce um nível ({ach})")
    rc, ach, _ = sfs(T, "-c", "laudo", "-l", "--depth", "1")
    ok(ach == ["a.txt", "grande.txt"], f"--depth vale na busca de CONTEÚDO ({ach})")
    rc, ach, _ = sfs(T, "-b", "laudo", "-l", "--depth", "1")
    ok(ach == ["a.txt", "grande.txt"], f"--depth vale no BOOLEANO ({ach})")

    # ------------------------------------------------------------ --follow
    rc, ach, _ = sfs(T, "-n", "*.txt", "-l", "--follow")
    ok("atalho/e.txt" in ach and len(ach) == 5, f"--follow atravessa o link ({ach})")
    rc, ach, _ = sfs(T, "-c", "laudo", "-l", "--follow")
    ok("atalho/e.txt" in ach, f"--follow vale na busca de CONTEÚDO ({ach})")

    # ------------------------------------------------------------ --follow + LAÇO
    # Medido antes do conserto: link apontando para uma pasta ANCESTRAL fazia o
    # rg sair 2 ("File system loop found") e o _reap pintava "search engine
    # failed" + exit 2 no conteúdo e no booleano; no nome, o fd virava
    # "read error". Nada ficou de fora — o ancestral é varrido na mesma busca —,
    # então nada disso é incompleto (o walker Python já cortava calado: E4).
    L = tempfile.mkdtemp(prefix="sfs_cliflags_laco_")
    try:
        os.makedirs(os.path.join(L, "p", "q"))
        with open(os.path.join(L, "p", "q", "x.txt"), "w") as f:
            f.write("laudo\n")
        os.symlink(os.path.join(L, "p"), os.path.join(L, "p", "q", "volta"))
        for modo in (["-n", "*.txt"], ["-c", "laudo"], ["-b", "laudo"]):
            p = subprocess.run([sys.executable, CLI, L, *modo, "-l", "--follow"],
                               capture_output=True, text=True, timeout=120)
            achou = [x for x in p.stdout.splitlines() if x.endswith("x.txt")]
            ok(p.returncode == 0 and len(achou) == 1 and "incomplete" not in p.stderr,
               f"--follow com laço ({modo[0]}): acha 1, exit 0, sem 'incompleto' "
               f"(rc={p.returncode}, achou={len(achou)}, "
               f"{'INCOMPLETO' if 'incomplete' in p.stderr else 'limpo'})")
    finally:
        shutil.rmtree(L, ignore_errors=True)

    # ------------------------------------------------------------ recusas (exit 2)
    for args, oque in [(["--max-size", "10X"], "--max-size inválido"),
                       (["--min-size", "10X"], "--min-size inválido (antes: ignorado mudo)"),
                       (["--min-size", "2M", "--max-size", "1M"], "mínimo > máximo"),
                       (["--depth", "0"], "--depth 0"),
                       (["--depth", "-3"], "--depth negativo")]:
        rc, ach, err = sfs(T, "-n", "*.txt", *args)
        # "unrecognized arguments" = a flag nem existe: passaria de graça
        ok(rc == 2 and not ach and "error" in err and "unrecognized" not in err,
           f"{oque} -> exit 2 com a frase certa, nada buscado (rc={rc}: {err.strip()[-70:]!r})")
    rc, ach, err = sfs(T, "-n", "*.txt", "--index", "--follow")
    ok(rc == 2 and "symlink" in err and "unrecognized" not in err, f"--index --follow recusado (rc={rc}: {err.strip()[-90:]!r})")
finally:
    shutil.rmtree(T, ignore_errors=True)
    shutil.rmtree(FORA, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
