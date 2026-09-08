#!/usr/bin/env python3
"""F11 — exclusão de árvores de snapshot, nos TRÊS backends.

O projeto tem um contrato explícito de paridade (fd × rg × fallback Python).
Duas armadilhas achadas pelo Fable 5 na revisão de 08/09/2026:

  bug2 — no rg o ÚLTIMO glob que casa vence. Com os negativos de snapshot antes
         dos globs de nome, um padrão como '*shot*' (ou o '*' da CLI) reabria a
         árvore e a busca ficava 10x mais lenta sem explicação.
  bug3 — root apontado PRA DENTRO de um snapshot: o fd achava (o --exclude é
         relativo ao root), o rg e o fallback devolviam VAZIO em silêncio. Quem
         navega até .../timeshift/snapshots/<data>/home/... quer justamente ali.
"""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)


def arvore():
    raiz = tempfile.mkdtemp(prefix="sfs-snap-")
    for rel in ("normal/achado.txt",
                "timeshift/snapshots/2026-09-01/usr/achado.txt",
                "timeshift/snapshots-daily/2026-09-01/usr/achado.txt",
                ".snapshots/3/snapshot/achado.txt"):
        p = os.path.join(raiz, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("laudo\n")
    return raiz


def busca(q):
    out = []
    E.search(q, out.append)
    return sorted(m.path for m in out)


def com_backend(nome, fn):
    """Força um backend zerando os outros binários detectados."""
    fd, rg = E.FD, E.RG
    if nome == "python":
        E.FD, E.RG = None, None
    try:
        return fn()
    finally:
        E.FD, E.RG = fd, rg


raiz = arvore()
try:
    for modo, q_extra in (("nome", {}), ("conteudo", {"content": "laudo"})):
        for backend in ("nativo", "python"):
            # 1) root FORA: só o normal aparece
            q = E.Query(paths=[raiz], name_patterns=["achado.txt"], **q_extra)
            r = com_backend(backend, lambda: busca(q))
            ok(r == [os.path.join(raiz, "normal/achado.txt")],
               f"[{modo}/{backend}] root fora: snapshot escondido, normal aparece")

            # 2) bug2: padrão de nome que casa o próprio diretório 'snapshots'
            if modo == "conteudo":
                q2 = E.Query(paths=[raiz], name_patterns=["*"], content="laudo")
                r2 = com_backend(backend, lambda: busca(q2))
                ok(all("snapshot" not in p for p in r2),
                   f"[{modo}/{backend}] bug2: glob '*' não reabre a árvore de snapshot")

            # 3) bug3: root DENTRO do snapshot -> quem aponta pra lá quer aquilo
            dentro = os.path.join(raiz, "timeshift/snapshots/2026-09-01")
            q3 = E.Query(paths=[dentro], name_patterns=["achado.txt"], **q_extra)
            r3 = com_backend(backend, lambda: busca(q3))
            ok(r3 == [os.path.join(dentro, "usr/achado.txt")],
               f"[{modo}/{backend}] bug3: root dentro do snapshot acha o que está lá")

    # 4) o padrão do snapper mora num diretório OCULTO: só aparece com hidden,
    #    e é aí que a exclusão dele precisa valer.
    q4 = E.Query(paths=[raiz], name_patterns=["achado.txt"], include_hidden=True)
    r4 = busca(q4)
    ok(r4 == [os.path.join(raiz, "normal/achado.txt")],
       "com --hidden, .snapshots (snapper) continua excluído")

    # 5) o auto-desligar (bug3) é POR GRUPO, não pela consulta inteira: buscar
    #    dentro de um snapshot E na raiz normal ao mesmo tempo não pode reabrir
    #    os snapshots do lado normal.
    dentro = os.path.join(raiz, "timeshift/snapshots/2026-09-01")
    q_mix = E.Query(paths=[dentro, raiz], name_patterns=["achado.txt"])
    r_mix = busca(q_mix)
    ok(os.path.join(dentro, "usr/achado.txt") in r_mix,
       "consulta mista: o root dentro do snapshot acha o que está lá")
    ok(os.path.join(raiz, "timeshift/snapshots-daily/2026-09-01/usr/achado.txt") not in r_mix,
       "consulta mista: o root normal NÃO reabre as outras árvores de snapshot")

    # 6) desligável
    q5 = E.Query(paths=[raiz], name_patterns=["achado.txt"],
                 include_hidden=True, skip_snapshots=False)
    ok(len(busca(q5)) == 4, "--snapshots devolve tudo (4 arquivos)")
finally:
    shutil.rmtree(raiz, ignore_errors=True)

print(f"\n{'FALHOU: ' + '; '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
