#!/usr/bin/env python3
"""Testes de regressão da auditoria Fable 5 (LinuxFileSearch_Auditoria_Debug.md).

Cobre os consertos B1–B14 no que dá para exercitar sem GUI (o núcleo é sem-Qt).
Rode:  python3 tests/test_audit.py      (ou via pytest)

Cada teste constrói sua própria árvore sintética em tempdir — não toca no acervo.
"""
from __future__ import annotations
import os, sys, time, subprocess, tempfile, shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lfs"))
import engine, boolean
from engine import Query


def _tree():
    """Árvore de teste: nomes com caixa mista + conteúdos p/ booleano/glob."""
    d = tempfile.mkdtemp(prefix="lfs_test_")
    files = {
        "N1.TXT":    "laudo do paciente\nassinatura",
        "n2.txt":    "laudo sem assinatura\npaciente ausente",
        "doc42.log": "paciente laudo rascunho",
        "misto.txt": "nada aqui",
        "ambos.log": "paciente e laudo juntos",
    }
    for name, body in files.items():
        with open(os.path.join(d, name), "w") as f:
            f.write(body)
    return d


# ------------------------------------------------------------------ §5 parse_size
def test_parse_size():
    assert engine.parse_size("10M") == 10 * (1 << 20)
    assert engine.parse_size("1G") == 1 << 30
    assert engine.parse_size("2TB") == 2 * (1 << 40)
    assert engine.parse_size("512") == 512
    assert engine.parse_size("") is None
    assert engine.parse_size("xxx") is None
    print("ok  parse_size (fonte única engine.parse_size)")


# ------------------------------------------------------------------ B1 _reap
def test_reap_kills_process():
    p = subprocess.Popen(["sleep", "30"])
    assert p.poll() is None
    engine._reap(p)
    assert p.poll() is not None            # morto
    engine._reap(p)                        # idempotente, não lança
    print("ok  B1  _reap mata e é idempotente")


def test_no_orphan_on_cancel():
    """B1: cancelar/abandonar a busca não deixa rg varrendo em background."""
    if not engine.RG or not os.path.isdir("/usr"):
        print("--  B1  (pulado: sem rg ou /usr)"); return
    q = Query(paths=["/usr"], content="configure", name_patterns=[], max_results=2)
    cancel = {"v": False}
    n = 0
    def on_result(m):
        nonlocal n
        n += 1
        if n >= 2:
            cancel["v"] = True             # simula abandono cedo
    engine.search(q, on_result, lambda: cancel["v"], lambda k: None)
    time.sleep(1.5)
    orphans = subprocess.run(["pgrep", "-x", "rg"], capture_output=True, text=True).stdout.split()
    assert not orphans, f"rg órfão vivo: {orphans}"
    print("ok  B1  sem rg órfão após cancelar busca em /usr")


# ------------------------------------------------------------------ B2 glob caixa
def test_glob_case_insensitive():
    """fd (só-nome) e rg (nome+conteúdo) devem concordar: *.txt insensível acha N1.TXT e n2.txt."""
    d = _tree()
    try:
        # só-nome (motor fd/python)
        got = set()
        engine.search(Query(paths=[d], name_patterns=["*.txt"], case_sensitive=False),
                      lambda m: got.add(os.path.basename(m.path)), lambda: False, lambda k: None)
        assert {"N1.TXT", "n2.txt"} <= got, f"só-nome achou {got}"
        # nome+conteúdo (motor rg) — antes do B2 achava só n2.txt
        got2 = set()
        engine.search(Query(paths=[d], name_patterns=["*.txt"], content="laudo",
                            case_sensitive=False),
                      lambda m: got2.add(os.path.basename(m.path)), lambda: False, lambda k: None)
        assert {"N1.TXT", "n2.txt"} <= got2, f"nome+conteúdo achou {got2}"
        print("ok  B2  glob *.txt insensível concorda entre fd e rg")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ B3 booleano + regex de nome
def test_boolean_name_regex():
    """Booleano deve respeitar o filtro de nome REGEX (^doc\\d+\\.)."""
    d = _tree()
    try:
        q = Query(paths=[d], name_patterns=[r"^doc\d+\."], name_is_regex=True,
                  case_sensitive=False)
        got = set()
        boolean.search_boolean(q, "laudo AND paciente",
                               lambda m: got.add(os.path.basename(m.path)), lambda: False)
        assert got == {"doc42.log"}, f"esperava só doc42.log, veio {got}"
        print("ok  B3  booleano respeita regex de nome (só doc42.log)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ B4 lotes no display
def test_display_lines_batched():
    """_display_lines em lotes não perde linhas mesmo com muitos caminhos."""
    d = tempfile.mkdtemp(prefix="lfs_batch_")
    try:
        paths = []
        for i in range(1000):
            p = os.path.join(d, f"f{i}.txt")
            with open(p, "w") as f:
                f.write("paciente laudo\n")
            paths.append(os.path.abspath(p))
        old = boolean._BATCH
        boolean._BATCH = 50                # força vários lotes
        try:
            res = boolean._display_lines(["laudo"], sorted(paths),
                                         Query(paths=[d]), lambda: False)
        finally:
            boolean._BATCH = old
        assert len(res) == 1000, f"esperava 1000 arquivos com linha, veio {len(res)}"
        print("ok  B4  _display_lines em lotes cobre todos os arquivos")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ B9 one_file_system fallback
def test_one_file_system_fallback():
    """Fallback Python com one_file_system=True não cruza mounts e não perde
    o que está no mesmo dispositivo."""
    d = _tree()
    try:
        q = Query(paths=[d], name_patterns=["*.txt"], one_file_system=True)
        got = {os.path.basename(m.path) for m in engine._iter_names_python(q)}
        assert {"N1.TXT", "n2.txt", "misto.txt"} <= got, f"fallback one_fs achou {got}"
        print("ok  B9  fallback Python respeita one_file_system sem perder o disco atual")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ §4 parser booleano
def test_boolean_parser():
    from boolean import parse, positive_terms, And, Or, Not, Term
    assert isinstance(parse("a AND b"), And)
    assert isinstance(parse("a OR b"), Or)
    assert isinstance(parse("a b").__class__, type)          # adjacência = AND
    assert positive_terms(parse("(nota OR laudo) AND paciente NOT rascunho")) == \
        ["nota", "laudo", "paciente"]
    # | & ! equivalem a OR AND NOT
    assert positive_terms(parse("a & b ! c")) == ["a", "b"]
    print("ok  §4  parser booleano (precedência, adjacência, | & !)")


# ------------------------------------------------------------------ N1 fd caixa-sensível
def test_fd_case_sensitive():
    """N1: com 'Aa' LIGADO, o fd não pode vazar por smart-case.
    glob *.txt sensível NÃO acha N1.TXT; regex de nome 'n1' sensível não casa N1.TXT."""
    if not engine.FD:
        print("--  N1  (pulado: sem fd)"); return
    d = _tree()
    try:
        got = set()
        engine.search(Query(paths=[d], name_patterns=["*.txt"], case_sensitive=True),
                      lambda m: got.add(os.path.basename(m.path)), lambda: False, lambda k: None)
        assert "N1.TXT" not in got, f"vazou N1.TXT com caixa ligada: {got}"
        assert "n2.txt" in got, f"perdeu n2.txt: {got}"
        got2 = set()
        engine.search(Query(paths=[d], name_patterns=["n1"], name_is_regex=True,
                            case_sensitive=True),
                      lambda m: got2.add(os.path.basename(m.path)), lambda: False, lambda k: None)
        assert "N1.TXT" not in got2, f"regex sensível vazou N1.TXT: {got2}"
        print("ok  N1  fd respeita caixa ligada (glob e regex de nome)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ opt#1 AND progressivo
def test_and_progressive_correctness():
    """Opt#1 não pode mudar resultados: AND/OR/NOT com restrição = interseção ingênua."""
    d = _tree()
    try:
        def run(expr):
            got = set()
            boolean.search_boolean(Query(paths=[d]), expr,
                                   lambda m: got.add(os.path.basename(m.path)), lambda: False)
            return got
        assert run("laudo AND paciente") == {"N1.TXT", "n2.txt", "doc42.log", "ambos.log"}
        assert run("laudo AND NOT rascunho") == {"N1.TXT", "n2.txt", "ambos.log"}
        assert run("(assinatura OR rascunho) AND paciente") == {"N1.TXT", "n2.txt", "doc42.log"}
        print("ok  opt#1  AND progressivo preserva os resultados (AND/OR/NOT)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_and_progressive_restricts():
    """Opt#1 de fato restringe: a 2ª parte do AND varre só o conjunto acumulado."""
    d = tempfile.mkdtemp(prefix="lfs_prog_")
    try:
        with open(os.path.join(d, "raro.txt"), "w") as f:
            f.write("raro comum\n")
        for i in range(50):
            with open(os.path.join(d, f"c{i}.txt"), "w") as f:
                f.write("comum\n")
        calls = []
        orig = boolean._files_with_term
        def spy(term, q, cancel, restrict=None):
            calls.append((term, None if restrict is None else len(restrict)))
            return orig(term, q, cancel, restrict)
        boolean._files_with_term = spy
        try:
            got = set()
            boolean.search_boolean(Query(paths=[d]), "raro AND comum",
                                   lambda m: got.add(os.path.basename(m.path)), lambda: False)
        finally:
            boolean._files_with_term = orig
        assert got == {"raro.txt"}, f"resultado errado: {got}"
        restricted = [c for c in calls if c[1] is not None]
        assert restricted, f"nenhuma varredura restrita ocorreu: {calls}"
        assert restricted[0][1] == 1, f"'comum' devia varrer só 1 arquivo (o de 'raro'): {calls}"
        print("ok  opt#1  2ª parte do AND varreu só o acumulado (1 arquivo, não 51)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    fns = [test_parse_size, test_reap_kills_process, test_no_orphan_on_cancel,
           test_glob_case_insensitive, test_boolean_name_regex,
           test_display_lines_batched, test_one_file_system_fallback,
           test_boolean_parser, test_fd_case_sensitive,
           test_and_progressive_correctness, test_and_progressive_restricts]
    fail = 0
    for fn in fns:
        try:
            fn()
        except AssertionError as e:
            fail += 1; print(f"FALHOU  {fn.__name__}: {e}")
        except Exception as e:
            fail += 1; print(f"ERRO    {fn.__name__}: {e!r}")
    print(f"\n{len(fns)-fail}/{len(fns)} testes passaram")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
