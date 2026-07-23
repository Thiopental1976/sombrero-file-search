#!/usr/bin/env python3
"""Campanha 2 / Bloco 1 (Fable) — PARIDADE rg ↔ fallback Python.

Ninguém jamais afirmou que os dois motores devolvem O MESMO resultado, e o T2
provou que já divergiram (linhas). Este harness roda a MESMA Query duas vezes —
com os binários reais (rg/fd) e com `engine.RG=engine.FD=""` — e compara:
conjunto de caminhos, `nmatch` por arquivo, e as `lines` (número + texto).

Divergência SILENCIOSA = bug (falha o teste). Divergência CONHECIDA e
documentada = registrada em DIVERGENCIAS_CONHECIDAS abaixo, com o mesmo texto no
README. Ver Fable, Bloco 1: "Divergência conhecida vira comentário no código +
linha no README, nunca surpresa."

Precisa de rg E fd reais no PATH; sem eles, os casos de paridade são PULADOS
(não há dois mundos para comparar).

Rode:  python3 tests/test_parity_rg_python.py
"""
from __future__ import annotations
import os, sys, random, tempfile, shutil

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine
import boolean
from engine import Query

HAVE_RG = bool(engine.RG)
HAVE_FD = bool(engine.FD)

# --------------------------------------------------------------- divergências conhecidas
# Cada entrada: (id, quando_ocorre, decisão). Espelhado no README (seção Paridade).
DIVERGENCIAS_CONHECIDAS = {
    "content_nmatch_submatches_vs_linhas":
        "Na busca de CONTEÚDO simples, rg conta nmatch por OCORRÊNCIA (submatch) e "
        "o fallback Python conta por LINHA que casa. Só diverge quando uma linha tem "
        ">1 ocorrência do termo. As LINHAS (nº+texto) e o conjunto de arquivos batem. "
        "Decisão: aceito; nmatch é indicador de 'quão quente', não contrato exato.",
    "utf16_bom_fallback_nao_decodifica":
        "O rg detecta o BOM UTF-16/UTF-32 e decodifica o arquivo; o fallback Python "
        "abre em modo texto (locale/UTF-8) e NÃO acha o termo em arquivo UTF-16. Só "
        "afeta o modo SEM ripgrep, em arquivos UTF-16/32 com BOM (raros no Linux, "
        "origem Windows). Decisão: documentado; sem rg, texto UTF-16 fica invisível "
        "na busca de conteúdo. Instalar ripgrep (Recommends) resolve.",
    # CRLF puro (\r\n) foi RESOLVIDO (Fable, decisão CRLF 23/07): os dois motores
    # normalizam 1 \r final via engine._logical_line; não há mais divergência de
    # texto. A sentinela em _norm() trava o invariante. O que sobra, e é FAMÍLIA
    # ESTRUTURAL documentada, é CR fora do padrão CRLF:
    "cr_fora_de_crlf_segmentacao_de_linha":
        "Arquivos com CR FORA do padrão CRLF — lone CR (Mac clássico pré-OSX) ou "
        "\\r\\r\\n — divergem em SEGMENTAÇÃO e NUMERAÇÃO de linhas entre os motores, "
        "não em texto: o rg separa registros só por \\n (lone CR => 1 linha gigante; "
        "\\r\\r\\n => texto '...\\r' numa linha), enquanto o Python em modo texto "
        "trata o CR solto como quebra (universal newlines => N linhas). Nenhum "
        "rstrip, guloso ou não, conserta numeração — o strip guloso só maquiaria o "
        "texto (paridade de fachada, pior que divergência documentada). Decisão "
        "(Fable): strip ÚNICO nos dois motores resolve o CRLF puro; CR fora de CRLF "
        "é patológico/pré-OSX e NÃO é perseguido — documentado, com teste dirigido "
        "que PINA a divergência estrutural (rg=1 linha, Python=N) p/ virar regressão "
        "se alguém 'consertar' um lado sem perceber.",
}

PASS, FAIL, KNOWN = [], [], []
def _ok(name):   PASS.append(name);  print(f"ok    {name}")
def _known(name, div_id): KNOWN.append((name, div_id)); print(f"~know {name}  [{div_id}]")
def _bug(name, detail):   FAIL.append((name, detail)); print(f"XXXXX {name}\n        {detail}")


# --------------------------------------------------------------- motor: roda nos 2 mundos
def _run(q, use_rg):
    orig = (engine.RG, engine.RGA, engine.FD)
    if not use_rg:
        engine.RG = engine.RGA = engine.FD = ""
    try:
        got = []
        engine.search(q, lambda m: got.append(m))
        return got
    finally:
        engine.RG, engine.RGA, engine.FD = orig

def _run_bool(q, expr, use_rg):
    orig = (engine.RG, engine.RGA, engine.FD)
    if not use_rg:
        engine.RG = engine.RGA = engine.FD = ""
    try:
        got = []
        boolean.search_boolean(q, expr, lambda m: got.append(m))
        return got
    finally:
        engine.RG, engine.RGA, engine.FD = orig

def _norm(matches):
    d = {}
    for m in matches:
        for _ln, txt in m.lines:
            # SENTINELA (Fable, decisão CRLF 23/07): antes o harness normalizava 1
            # \r final dos dois lados (band-aid). Agora os DOIS motores normalizam
            # via engine._logical_line, então NENHUM texto de linha pode terminar
            # em \r. Se um caminho futuro reintroduzir CR (parser novo, modo novo
            # do rg), a suíte acusa AQUI na hora, em vez de a normalização
            # silenciosa engolir a regressão.
            assert not txt.endswith("\r"), \
                f"CR final vazou em {m.path!r}: {txt!r} — _logical_line falhou?"
        d[os.path.abspath(m.path)] = {
            "nmatch": m.nmatch,
            "lines": sorted((ln, txt) for ln, txt in m.lines),
        }
    return d

def _rel(paths, root):
    return sorted(os.path.relpath(p, root) for p in paths)


def compare(name, q, root, *, is_bool=False, expr=None,
            allow_nmatch_divergence=False, compare_lines=True,
            known_encoding=frozenset()):
    """Roda os 2 mundos e classifica. `known_encoding` = basenames que podem
    divergir SÓ por codificação (rg decodifica UTF-16/BOM, Python não) — são
    registrados como conhecidos e removidos antes das demais comparações, para
    não mascarar divergências reais. Retorna True se paridade OK/conhecida."""
    if not (HAVE_RG and HAVE_FD):
        return None  # pulado
    a = _norm(_run_bool(q, expr, True) if is_bool else _run(q, True))    # rg
    b = _norm(_run_bool(q, expr, False) if is_bool else _run(q, False))  # python
    # 1) conjunto de caminhos — descontando divergências de codificação conhecidas
    diff = set(a) ^ set(b)
    enc_diff = {p for p in diff if os.path.basename(p) in known_encoding}
    real_diff = diff - enc_diff
    if enc_diff:
        _known(name + " [enc]", "utf16_bom_fallback_nao_decodifica")
        for p in enc_diff:          # remove dos dois lados p/ seguir comparando o resto
            a.pop(p, None); b.pop(p, None)
    if real_diff:
        so, sp = _rel(set(a) - set(b), root), _rel(set(b) - set(a), root)
        _bug(name, f"conjuntos divergem — só_rg={so}  só_py={sp}")
        return False
    # 2) linhas (nº + texto)
    if compare_lines:
        for p in a:
            if a[p]["lines"] != b[p]["lines"]:
                _bug(name, f"linhas divergem em {os.path.relpath(p, root)}\n"
                           f"        rg={a[p]['lines'][:4]}\n"
                           f"        py={b[p]['lines'][:4]}")
                return False
    # 3) nmatch
    nmatch_div = [p for p in a if a[p]["nmatch"] != b[p]["nmatch"]]
    if nmatch_div:
        if allow_nmatch_divergence:
            _known(name, "content_nmatch_submatches_vs_linhas")
            return True
        p = nmatch_div[0]
        _bug(name, f"nmatch diverge em {os.path.relpath(p, root)}: "
                   f"rg={a[p]['nmatch']} py={b[p]['nmatch']} (linhas iguais)")
        return False
    _ok(name)
    return True


# =============================================================== 1.2 CASOS DIRIGIDOS
def caso_dirigidos():
    d = tempfile.mkdtemp(prefix="par_dir_")
    try:
        W = lambda rel, data, mode="w", **kw: _w(d, rel, data, mode, **kw)
        # arquivos variados
        W("plain.txt", "Paciente com laudo\nlinha sem nada\nlaudo laudo laudo aqui\n")
        W("case.txt", "LAUDO Laudo laudo\n")
        W("word.txt", "laudo\nlaudos\nprelaudo\nlaudo!\n")
        W("anchor.txt", "laudo no comeco\nno fim laudo\nmeio laudo meio\n")
        W("acento.txt", "LAUDO com ÁGUA\nlaudo com água\n")
        W("nonl.txt", "laudo sem newline final", )      # sem \n no fim
        W("crlf.txt", "laudo linha um\r\nlaudo linha dois\r\n", mode="wb",
          enc=lambda s: s.encode())
        W("hidden/.oculto.txt", "laudo escondido\n")
        W("d1/d2/deep.txt", "laudo fundo\n")
        # linha de 2 MB com o termo no fim
        W("bigline.txt", ("x" * (2*1024*1024)) + " laudo\n")
        # UTF-16 com BOM
        W("utf16.txt", "laudo em utf16\noutra linha\n", mode="wb",
          enc=lambda s: s.encode("utf-16"))

        base = dict(paths=[d], content="laudo")
        ENC = {"utf16.txt"}     # divergência de codificação conhecida (rg decodifica, py não)
        # case-insensitive (default) — linha com 3 ocorrências => nmatch diverge (conhecido)
        compare("1.2a case-insensitive (default)", Query(**base), d,
                allow_nmatch_divergence=True, known_encoding=ENC)
        # case-sensitive
        compare("1.2b case-sensitive", Query(**base, case_sensitive=True), d,
                allow_nmatch_divergence=True, known_encoding=ENC)
        # whole_word: laudo != laudos/prelaudo, mas casa 'laudo!' (fronteira)
        compare("1.2c whole_word", Query(**base, whole_word=True), d,
                allow_nmatch_divergence=True, known_encoding=ENC)
        # regex de conteúdo com âncoras
        compare("1.2d regex ^laudo", Query(paths=[d], content=r"^laudo",
                content_is_regex=True), d, allow_nmatch_divergence=True, known_encoding=ENC)
        compare("1.2e regex laudo$", Query(paths=[d], content=r"laudo$",
                content_is_regex=True), d, allow_nmatch_divergence=True, known_encoding=ENC)
        compare("1.2f regex classe [Ll]audo", Query(paths=[d], content=r"[Ll]audo",
                content_is_regex=True), d, allow_nmatch_divergence=True, known_encoding=ENC)
        # max_depth 0/1/2 (só nome, sem conteúdo, p/ isolar profundidade)
        for md in (0, 1, 2):
            compare(f"1.2g max_depth={md} (nome *.txt)",
                    Query(paths=[d], name_patterns=["*.txt"], max_depth=md), d,
                    compare_lines=False)
        # include_hidden
        compare("1.2h include_hidden (nome)", Query(paths=[d],
                name_patterns=["*.txt"], include_hidden=True), d, compare_lines=False)
        compare("1.2i sem hidden (nome)", Query(paths=[d],
                name_patterns=["*.txt"]), d, compare_lines=False)
        # nome-regex vs glob
        compare("1.2j nome-regex", Query(paths=[d], name_patterns=[r"^c.*\.txt$"],
                name_is_regex=True), d, compare_lines=False)
        # acento casefold (Á vs á) — busca 'água' minúsculo, case-insensitive
        compare("1.2k acento casefold (água)", Query(paths=[d], content="água"), d,
                allow_nmatch_divergence=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _w(d, rel, data, mode="w", enc=None):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(rel) else None
    if "b" in mode:
        with open(p, "wb") as f: f.write(enc(data) if enc else data)
    else:
        with open(p, "w") as f: f.write(data)


# ============================================ 1.2-CR DIVERGÊNCIA ESTRUTURAL (pinada)
def caso_cr_estrutural():
    """PINA a divergência conhecida cr_fora_de_crlf_segmentacao_de_linha (Fable,
    decisão CRLF 23/07). Um arquivo com CR FORA de CRLF (lone CR do Mac clássico)
    NÃO tem \\n: o rg separa registros só por \\n → vê o arquivo como UMA linha
    gigante; o Python em modo texto (universal newlines) trata o CR como quebra →
    vê N linhas. É divergência de SEGMENTAÇÃO, não de texto, e nenhum rstrip
    conserta numeração. Este teste trava esse conhecimento: se alguém 'consertar'
    um dos lados daqui a um ano, a divergência estrutural muda e a suíte ACUSA,
    em vez de nascer uma divergência nova em silêncio. Requer rg (senão os dois
    lados seriam Python e não haveria os 2 mundos)."""
    name = "1.2-CR lone-CR segmentação (pinado)"
    if not HAVE_RG:
        print(f"~skip {name} (sem rg)"); return
    d = tempfile.mkdtemp(prefix="par_cr_")
    try:
        # lone CR, SEM nenhum \n: 3 segmentos, cada um com o termo.
        with open(os.path.join(d, "maccr.txt"), "wb") as f:
            f.write("linha um\rlinha dois\rlinha tres\r".encode())
        q = Query(paths=[d], content="linha")
        p = os.path.abspath(os.path.join(d, "maccr.txt"))
        rg_n = len(_norm(_run(q, use_rg=True)).get(p, {}).get("lines", []))
        py_n = len(_norm(_run(q, use_rg=False)).get(p, {}).get("lines", []))
        if rg_n == 1 and py_n == 3:
            _known(name, "cr_fora_de_crlf_segmentacao_de_linha")
        elif rg_n == py_n:
            _bug(name, f"divergência ESTRUTURAL documentada SUMIU: rg e py agora "
                       f"dão {rg_n} linhas. Alguém 'consertou' um lado? Revise a "
                       f"decisão CRLF e DIVERGENCIAS_CONHECIDAS antes de seguir.")
        else:
            _bug(name, f"segmentação inesperada em lone-CR: rg={rg_n}, py={py_n} "
                       f"(documentado: rg=1, py=3)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# =============================================================== 1.3 PROPRIEDADE (booleano)
VOCAB = ["laudo", "nota", "exame", "paciente", "rascunho", "urgente"]

def _rand_expr(rng, depth=0):
    """Gera expressão booleana válida com AND/OR/NOT e parênteses."""
    if depth >= 3 or (depth > 0 and rng.random() < 0.5):
        return rng.choice(VOCAB)
    op = rng.choice(["AND", "OR", "NOT", "AND", "OR"])   # NOT menos frequente
    if op == "NOT":
        return f"{_rand_expr(rng, depth+1)} NOT {rng.choice(VOCAB)}"
    left = _rand_expr(rng, depth+1)
    right = _rand_expr(rng, depth+1)
    inner = f"{left} {op} {right}"
    return f"({inner})" if rng.random() < 0.5 else inner

def caso_propriedade(n_expr=500, n_files=2000, seed=20260722):
    if not (HAVE_RG and HAVE_FD):
        print("~skip 1.3 propriedade (sem rg/fd)"); return
    rng = random.Random(seed)
    d = tempfile.mkdtemp(prefix="par_prop_")
    try:
        # árvore sintética: cada arquivo recebe um subconjunto aleatório do vocab
        for i in range(n_files):
            words = [w for w in VOCAB if rng.random() < 0.4]
            sub = os.path.join(d, f"s{i % 20:02d}")
            os.makedirs(sub, exist_ok=True)
            body = "\n".join(words) + "\n" if words else "vazio\n"
            fp = os.path.join(sub, f"f{i:05d}.txt")
            # ~1/4 dos arquivos em CRLF (Fable, decisão CRLF 23/07): trava a
            # paridade nova sob busca booleana. O rg preserva o \r e o Python
            # (universal newlines) não; após engine._logical_line o conjunto de
            # arquivos que casa QUALQUER termo deve ser idêntico independe do EOL.
            if i % 4 == 0:
                with open(fp, "wb") as f:
                    f.write(body.replace("\n", "\r\n").encode())
            else:
                with open(fp, "w") as f:
                    f.write(body)
        divergentes = 0
        exemplos = []
        for k in range(n_expr):
            expr = _rand_expr(rng)
            try:
                a = {os.path.abspath(m.path) for m in _run_bool(Query(paths=[d]), expr, True)}
                b = {os.path.abspath(m.path) for m in _run_bool(Query(paths=[d]), expr, False)}
            except Exception as e:
                _bug(f"1.3 expr#{k} exceção", f"{expr!r} -> {e}")
                divergentes += 1; continue
            if a != b:
                divergentes += 1
                if len(exemplos) < 5:
                    exemplos.append((expr, len(a - b), len(b - a)))
        if divergentes == 0:
            _ok(f"1.3 propriedade: {n_expr} expr × {n_files} arq — zero divergências")
        else:
            _bug("1.3 propriedade",
                 f"{divergentes}/{n_expr} expressões divergem. Ex: {exemplos}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# =============================================================== 2. BLOCO 2 — FUZZ DE NOMES
# Fuzz da busca POR NOME (fd ↔ Python). O valor central: estressar o caminho de
# FUSÃO de globs (opt#3: >3 globs viram UMA regex via _merge_globs/_glob_to_regex)
# — é onde uma tradução glob→regex errada vazaria em silêncio. Nomes ASCII de
# propósito: o case-fold ASCII do Python (.lower) e o --ignore-case do fd são
# idênticos, então qualquer divergência aqui é bug de LÓGICA, não de Unicode.
_GLOB_ATOMS = ["*", "?", "a", "b", "e", "g", "l", "o", "t", "x", "0", "1",
               "[ab]", "[a-z]", "[0-9]", "[!x]", "[!0-9]", "_", "-", "."]
_NAME_EXTS = ["txt", "log", "md", "py", "dat"]

def _rand_glob(rng):
    """Glob de basename no subconjunto SEGURO (sem '{}' de chave, sem '/'): os
    mesmos operadores em que fnmatch e o globset do fd concordam byte-a-byte."""
    body = "".join(rng.choice(_GLOB_ATOMS) for _ in range(rng.randint(1, 4)))
    if rng.random() < 0.5:
        body += "*." + rng.choice(_NAME_EXTS)
    return body or "*"

def _rand_name_regex(rng):
    """Regex de basename no subconjunto comum a Rust-regex e `re` (sem backref/lookaround)."""
    return rng.choice([
        r"^" + rng.choice("abeglotx"),
        r"\." + rng.choice(_NAME_EXTS) + r"$",
        r"[0-9]+",
        rng.choice("abeg") + r".*" + rng.choice("lotx"),
        r"(" + rng.choice(_NAME_EXTS) + r"|" + rng.choice(_NAME_EXTS) + r")$",
        r"^[a-z]{1,3}",
        r"[._-]",
    ])

def caso_fuzz_nomes(n_queries=300, n_files=600, seed=20260723):
    """Campanha 2 / BLOCO 2 (Fable): fuzz de busca POR NOME comparando o mundo fd
    contra o fallback Python (os.walk + fnmatch/re). Varia padrões (glob 1..6 —
    às vezes ≥4, disparando a fusão — e regex), caixa, ocultos, profundidade e
    recursão; exige conjuntos de caminhos IDÊNTICOS. Divergência = bug (falha)."""
    if not (HAVE_RG and HAVE_FD):
        print("~skip Bloco2 fuzz de nomes (sem fd)"); return
    rng = random.Random(seed)
    d = tempfile.mkdtemp(prefix="par_nome_")
    try:
        alpha = "abeglotx0123_-. +"
        for i in range(n_files):
            sub = d
            for _ in range(rng.randint(0, 3)):
                sub = os.path.join(sub, f"d{rng.randint(0, 4)}")
            os.makedirs(sub, exist_ok=True)
            stem = ("".join(rng.choice(alpha) for _ in range(rng.randint(1, 8)))).strip() or "f"
            ext = rng.choice(_NAME_EXTS + [e.upper() for e in _NAME_EXTS])
            hidden = "." if rng.random() < 0.15 else ""
            try:
                with open(os.path.join(sub, f"{hidden}{stem}.{ext}"), "w") as f:
                    f.write("x")
            except OSError:
                pass
        divergentes, exemplos = 0, []
        for k in range(n_queries):
            common = dict(paths=[d],
                          case_sensitive=rng.random() < 0.5,
                          include_hidden=rng.random() < 0.5,
                          max_depth=rng.choice([None, 1, 2, 3]),
                          recursive=rng.random() < 0.9)
            if rng.random() < 0.25:
                q = Query(name_patterns=[_rand_name_regex(rng)], name_is_regex=True, **common)
            else:
                q = Query(name_patterns=[_rand_glob(rng) for _ in range(rng.randint(1, 6))],
                          **common)
            try:
                a = {os.path.abspath(m.path) for m in _run(q, True)}    # fd
                b = {os.path.abspath(m.path) for m in _run(q, False)}   # python
            except Exception as e:
                _bug(f"2.fuzz#{k} exceção", f"{q.name_patterns!r} -> {e}")
                divergentes += 1; continue
            if a != b:
                divergentes += 1
                if len(exemplos) < 6:
                    exemplos.append((q.name_patterns, q.name_is_regex,
                                     sorted(os.path.relpath(p, d) for p in (a - b))[:3],
                                     sorted(os.path.relpath(p, d) for p in (b - a))[:3]))
        if divergentes == 0:
            _ok(f"2.fuzz nomes: {n_queries} queries × {n_files} arq — fd≡Python")
        else:
            _bug("2.fuzz nomes", f"{divergentes}/{n_queries} divergem. Ex: {exemplos}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def caso_multitermo_dirigido():
    """Dirigido mínimo do multi-termo (Fable §0): dois termos POSITIVOS numa busca
    booleana. (a) mesma LINHA → a linha aparece UMA vez (dedup, não uma por termo);
    (b) linhas DISTINTAS → as duas aparecem, ORDENADAS por nº de linha. max_results
    apertado. Vale nos dois mundos (rg e Python)."""
    if not (HAVE_RG and HAVE_FD):
        print("~skip 2.multitermo (sem rg/fd)"); return
    d = tempfile.mkdtemp(prefix="par_mt_")
    try:
        with open(os.path.join(d, "same.txt"), "w") as f:       # termos na MESMA linha
            f.write("alfa e beta juntos\nlinha neutra\n")
        with open(os.path.join(d, "diff.txt"), "w") as f:       # linhas DISTINTAS (beta antes)
            f.write("comeco beta\nmeio nada\nfim alfa\n")
        q = Query(paths=[d], max_results=50)
        ok = True
        for use in (True, False):
            by = {os.path.basename(m.path): m for m in _run_bool(q, "alfa AND beta", use)}
            if set(by) != {"same.txt", "diff.txt"}:
                _bug("2.multitermo", f"arquivos {set(by)} (rg={use})"); ok = False; break
            l1 = [t for (n, t) in by["same.txt"].lines if n == 1]
            if len(l1) != 1:            # (a) dedup mesma-linha
                _bug("2.multitermo", f"dedup mesma-linha falhou: {by['same.txt'].lines} (rg={use})")
                ok = False; break
            nums = [n for (n, _t) in by["diff.txt"].lines]
            if nums != sorted(nums) or 1 not in nums or 3 not in nums:   # (b) ordenação
                _bug("2.multitermo", f"ordenação/linhas erradas: {by['diff.txt'].lines} (rg={use})")
                ok = False; break
        if ok:
            _ok("2.multitermo dirigido: dedup mesma-linha + ordenação linhas-distintas")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# =============================================================== 1.1 harness p/ suíte
def test_parity_directed_and_property():
    """Ponto de entrada p/ o test_audit: roda os casos dirigidos + uma amostra
    da propriedade (menor, p/ caber no tempo da suíte). Sem rg/fd, é no-op."""
    if not (HAVE_RG and HAVE_FD):
        print("ok  Bloco1 paridade: PULADO (sem rg/fd — não há 2 mundos)"); return
    caso_dirigidos()
    caso_cr_estrutural()                                # pina divergência lone-CR
    caso_multitermo_dirigido()                          # Bloco 2: dedup + ordenação
    caso_fuzz_nomes(n_queries=120, n_files=300, seed=2) # Bloco 2: fuzz de nomes (amostra)
    caso_propriedade(n_expr=120, n_files=400, seed=1)   # amostra rápida
    assert not FAIL, f"divergências SILENCIOSAS: {FAIL}"
    print(f"ok  Bloco1 paridade: {len(PASS)} casos OK, {len(KNOWN)} divergências conhecidas")


def main():
    print(f"rg={'sim' if HAVE_RG else 'NÃO'}  fd={'sim' if HAVE_FD else 'NÃO'}")
    if not (HAVE_RG and HAVE_FD):
        print("Sem rg/fd reais — nada a comparar. Instale ripgrep+fd."); return 0
    caso_dirigidos()
    caso_cr_estrutural()        # pina divergência estrutural lone-CR
    caso_multitermo_dirigido()  # Bloco 2: dedup mesma-linha + ordenação
    caso_fuzz_nomes()           # Bloco 2: fuzz de nomes 300 × 600, o completo
    caso_propriedade()          # 500 × 2000, o completo
    print("\n" + "=" * 64)
    print(f"PARIDADE: {len(PASS)} OK · {len(KNOWN)} conhecidas · {len(FAIL)} BUGS")
    for nm, did in KNOWN:
        print(f"  ~ {nm}: {DIVERGENCIAS_CONHECIDAS.get(did, did)[:70]}…")
    if FAIL:
        print("\nBUGS (divergência silenciosa):")
        for nm, det in FAIL:
            print(f"  XX {nm}: {det}")
        return 1
    print("Zero divergências silenciosas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
