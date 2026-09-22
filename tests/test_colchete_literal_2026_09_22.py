#!/usr/bin/env python3
"""Busca por NOME com colchetes: `[2019]` acha "[2019] Laudos" (22/09/2026).

Nota 1 do parecer de revisão 2 do Fable: glob com metacaractere vale "como
digitado", então `-n '[2019]'` virava classe de UM caractere (2, 0, 1 ou 9) e o
usuário que digitava o nome da pasta recebia zero sem explicação. Agora, termo
com colchetes e SEM `*`/`?` é procurado das duas formas — glob como digitado E
texto literal "contém" — e os resultados se somam: nada que existia some.
Rode:  python3 tests/test_colchete_literal_2026_09_22.py
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine                                                 # noqa: E402
from engine import Query                                      # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

ok(engine.as_name_globs("laudo") == ["*laudo*"], "texto puro: um glob 'contém', como sempre")
ok(engine.as_name_globs("*.pdf") == ["*.pdf"], "glob com * : só como digitado")
ok(engine.as_name_globs("[0-9]?.txt") == ["[0-9]?.txt"], "colchete + ? : só como digitado")
gs = engine.as_name_globs("[2019]")
ok(gs[0] == "[2019]" and len(gs) == 2, f"só colchetes: glob como digitado + literal ({gs})")

T = tempfile.mkdtemp(prefix="sfs_colch_")
try:
    NOMES = ["[2019] Laudos", "laudo [cópia].txt", "2.txt", "9", "relatorio_2019.txt", "x]y.txt", "a[b.txt"]
    for n in NOMES:
        p = os.path.join(T, n)
        if "Laudos" in n:
            os.makedirs(p)
        else:
            open(p, "w").close()

    def busca(termo, python=False):
        salvos = (engine.RG, engine.RGA, engine.FD)
        if python:
            engine.RG = engine.RGA = engine.FD = ""
        try:
            r = []
            engine.search(Query(paths=[T], name_patterns=engine.as_name_globs(termo), recursive=False), r.append)
            return sorted(os.path.basename(m.path) for m in r)
        finally:
            engine.RG, engine.RGA, engine.FD = salvos

    casos = [("[2019]", ["9", "[2019] Laudos"], "[2019] acha a pasta (literal) e segue achando o '9' (glob)"),
             ("[cópia]", ["laudo [cópia].txt"], "literal com acento dentro dos colchetes"),
             ("x]y", ["x]y.txt"], "']' solto: texto puro (não é glob)"),
             ("a[b", ["a[b.txt"], "'[' sem fechar: literal"),
             ("[0-9]", ["9"], "classe de faixa segue glob (nome inteiro de 1 caractere)")]
    for termo, esp, oque in casos:
        a, b = busca(termo), busca(termo, python=True)
        ok(a == sorted(esp), f"[fd    ] {oque}: {a}")
        ok(b == sorted(esp), f"[python] {oque}: {b}")

    r = subprocess.run([sys.executable, os.path.join(RAIZ, "lfs", "cli.py"), T, "-n", "[2019]", "-l"],
                       capture_output=True, text=True, timeout=60)
    ok("[2019] Laudos" in r.stdout, "CLI: sfs -n '[2019]' acha a pasta")
finally:
    shutil.rmtree(T, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
