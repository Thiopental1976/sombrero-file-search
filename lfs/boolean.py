#!/usr/bin/env python3
"""Linux File Search — busca BOOLEANA de conteúdo (recurso-assinatura, F3).

Sintaxe:  (A OR B) AND C NOT D     [também: | & !, e adjacência = AND implícito]
  - termos entre "aspas" preservam espaços; termo cru vai até o próximo operador/parêntese
  - precedência:  NOT (unário) > AND > OR ;  parênteses agrupam
  - "AND NOT X" e "X NOT Y" funcionam (NOT binário vira A AND (NOT B))

Estratégia (casada com o desenho do Fable):
  1. parser -> AST
  2. cada TERMO -> conjunto de arquivos que o contêm, via `rg -l` (rápido) ou fallback Python
  3. AND=interseção, OR=união, NOT=universo−conjunto (universo só é calculado se preciso)
  4. passada final de exibição: pega as linhas dos termos POSITIVOS nos arquivos do resultado

Sem Qt aqui. O motor devolve Matches iguais aos de engine.py (a GUI/CLI reaproveitam).
"""
from __future__ import annotations
import os, re, json, subprocess
from dataclasses import dataclass
from typing import Optional

try:                       # funciona como pacote (-m lfs.boolean / GUI) e flat (cli.py)
    from . import engine    # RG, Query, Match, _passes_meta, _iter_content_python
except ImportError:
    import engine


# ------------------------------------------------------------------ AST
@dataclass
class Term:  text: str
@dataclass
class Not:   node: object
@dataclass
class And:   a: object; b: object
@dataclass
class Or:    a: object; b: object


class BooleanError(ValueError):
    pass


# ------------------------------------------------------------------ tokenizer
_OPS = {"and": "AND", "or": "OR", "not": "NOT",
        "&": "AND", "&&": "AND", "|": "OR", "||": "OR", "!": "NOT"}

def tokenize(s: str):
    toks = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1; continue
        if c in "()":
            toks.append((c, c)); i += 1; continue
        if c == '"':                      # termo com aspas
            j = i + 1
            while j < n and s[j] != '"':
                j += 1
            toks.append(("TERM", s[i+1:j])); i = j + 1; continue
        if c in "&|":                     # & && | ||
            if i+1 < n and s[i+1] == c:
                toks.append((_OPS[c*2], c*2)); i += 2
            else:
                toks.append((_OPS[c], c)); i += 1
            continue
        if c == "!":
            toks.append(("NOT", "!")); i += 1; continue
        # palavra crua até espaço/operador/parêntese
        j = i
        while j < n and not s[j].isspace() and s[j] not in '()&|!"':
            j += 1
        word = s[i:j]
        low = word.lower()
        if low in _OPS:
            toks.append((_OPS[low], word))
        else:
            toks.append(("TERM", word))
        i = j
    return toks


# ------------------------------------------------------------------ parser (recursive descent)
class _P:
    def __init__(self, toks):
        self.t = toks; self.i = 0
    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)
    def eat(self):
        tok = self.peek(); self.i += 1; return tok

    def parse(self):
        if not self.t:
            raise BooleanError("expressão vazia")
        node = self.parse_or()
        if self.i != len(self.t):
            raise BooleanError(f"token inesperado: {self.peek()[1]!r}")
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.peek()[0] == "OR":
            self.eat(); node = Or(node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_not()
        while True:
            k = self.peek()[0]
            if k == "AND":
                self.eat(); node = And(node, self.parse_not())
            elif k == "NOT":                       # "A NOT B" = A AND (NOT B)
                self.eat(); node = And(node, Not(self.parse_not()))
            elif k in ("TERM", "("):               # adjacência = AND implícito
                node = And(node, self.parse_not())
            else:
                break
        return node

    def parse_not(self):
        if self.peek()[0] == "NOT":
            self.eat(); return Not(self.parse_not())
        return self.parse_atom()

    def parse_atom(self):
        k, v = self.peek()
        if k == "(":
            self.eat(); node = self.parse_or()
            if self.peek()[0] != ")":
                raise BooleanError("parêntese ')' faltando")
            self.eat(); return node
        if k == "TERM":
            self.eat(); return Term(v)
        raise BooleanError(f"esperava termo, veio {v!r}")


def parse(expr: str):
    return _P(tokenize(expr)).parse()


def positive_terms(node) -> list[str]:
    """Termos NÃO negados (p/ a passada de exibição das linhas)."""
    out = []
    def walk(n, neg):
        if isinstance(n, Term):
            if not neg: out.append(n.text)
        elif isinstance(n, Not):    walk(n.node, not neg)
        elif isinstance(n, (And, Or)):
            walk(n.a, neg); walk(n.b, neg)
    walk(node, False)
    # únicos preservando ordem
    seen = set(); uniq = []
    for t in out:
        if t not in seen: seen.add(t); uniq.append(t)
    return uniq


# ------------------------------------------------------------------ conjuntos de arquivos por termo
def _rg_base(q: engine.Query):
    cmd = [engine.RG]
    if not q.respect_gitignore: cmd.append("--no-ignore")
    if q.include_hidden:        cmd.append("--hidden")
    if q.follow_symlinks:       cmd.append("--follow")
    if q.one_file_system:       cmd.append("--one-file-system")
    if not q.case_sensitive:    cmd.append("--ignore-case")
    if q.whole_word:            cmd.append("--word-regexp")
    if not q.recursive:         cmd += ["--max-depth", "1"]
    elif q.max_depth is not None: cmd += ["--max-depth", str(q.max_depth)]
    if q.name_patterns and not q.name_is_regex:
        if not q.case_sensitive:                 # B2: glob insensível
            cmd.append("--glob-case-insensitive")
        for p in q.name_patterns: cmd += ["--glob", p]
    return cmd


def _files_with_term(term: str, q: engine.Query, cancel) -> set[str]:
    """Arquivos que CONTÊM o termo (rg -l). Fallback Python se rg ausente."""
    if engine.RG:
        cmd = _rg_base(q) + ["-l"]
        if not q.content_is_regex: cmd.append("--fixed-strings")
        cmd += ["-e", term, "--"] + q.paths
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, errors="replace")
        except OSError:
            return _files_with_term_py(term, q, cancel)
        out = set()
        try:
            for line in proc.stdout:
                if cancel(): break
                fp = line.rstrip("\n")
                if fp: out.add(os.path.abspath(fp))
        finally:
            engine._reap(proc)                    # B1: nunca deixar rg órfão
        return out
    return _files_with_term_py(term, q, cancel)


def _files_with_term_py(term: str, q: engine.Query, cancel) -> set[str]:
    sub = engine.Query(**{**q.__dict__, "content": term})
    return {os.path.abspath(m.path) for m in engine._iter_content_python(sub, cancel)}


def _universe(q: engine.Query, cancel) -> set[str]:
    """Todos os arquivos candidatos (p/ resolver NOT). rg --files ou fd/os.walk."""
    if engine.RG:
        cmd = _rg_base(q) + ["--files", "--"] + q.paths
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, errors="replace")
        except OSError:
            proc = None
        if proc:
            out = set()
            try:
                for line in proc.stdout:
                    if cancel(): break
                    fp = line.rstrip("\n")
                    if fp: out.add(os.path.abspath(fp))
            finally:
                engine._reap(proc)                # B1
            return out
    return {os.path.abspath(m.path) for m in engine._iter_names_python(q)}


# ------------------------------------------------------------------ avaliação do AST
def _eval(node, q, cancel, cache, universe_box):
    if isinstance(node, Term):
        if node.text not in cache:
            cache[node.text] = _files_with_term(node.text, q, cancel)
        return cache[node.text]
    if isinstance(node, And):
        return _eval(node.a, q, cancel, cache, universe_box) & _eval(node.b, q, cancel, cache, universe_box)
    if isinstance(node, Or):
        return _eval(node.a, q, cancel, cache, universe_box) | _eval(node.b, q, cancel, cache, universe_box)
    if isinstance(node, Not):
        if universe_box[0] is None:
            universe_box[0] = _universe(q, cancel)
        return universe_box[0] - _eval(node.node, q, cancel, cache, universe_box)
    raise BooleanError("nó desconhecido")


# ------------------------------------------------------------------ API pública
def search_boolean(q: engine.Query, expr: str, on_result, cancel=lambda: False,
                   on_progress=lambda n: None):
    """Resolve a expressão booleana -> arquivos, então emite Matches com linhas
    dos termos positivos. Retorna (total, segundos)."""
    import time
    t0 = time.time()
    ast = parse(expr)
    cache: dict = {}
    universe_box = [None]
    files = _eval(ast, q, cancel, cache, universe_box)
    # B3: filtro de nome por REGEX (o glob já vai pro rg; regex é pós-filtro no basename)
    if q.name_is_regex and q.name_patterns:
        nrx = re.compile(q.name_patterns[0], 0 if q.case_sensitive else re.IGNORECASE)
        files = {f for f in files if nrx.search(os.path.basename(f))}
    pos = positive_terms(ast)

    # passada de exibição: linhas dos termos positivos, só nos arquivos do resultado
    n = 0
    files_sorted = sorted(files)
    lines_by_file = _display_lines(pos, files_sorted, q, cancel) if pos else {}
    for fp in files_sorted:
        if cancel(): break
        try:
            st = os.stat(fp)
        except OSError:
            continue
        if not engine._passes_meta(q, st):
            continue
        m = engine.Match(fp, st.st_size, st.st_mtime)
        for ln, txt in lines_by_file.get(fp, []):
            m.lines.append((ln, txt)); m.nmatch += 1
        on_result(m)
        n += 1
        if n % 25 == 0: on_progress(n)
        if n >= q.max_results: break
    return n, time.time() - t0


_BATCH = 400   # B4: caminhos por invocação do rg (evita estourar ARG_MAX)

def _display_lines(pos_terms, files, q: engine.Query, cancel) -> dict:
    """Para os arquivos-resultado, extrai linhas que casam QUALQUER termo positivo.
    B4: processa em lotes p/ não estourar o argv (60k caminhos matariam o exec)."""
    if not files or not engine.RG:
        return {}
    base = _rg_base(q) + ["--json"]
    if not q.content_is_regex: base.append("--fixed-strings")
    for t in pos_terms: base += ["-e", t]
    res: dict = {}
    for i in range(0, len(files), _BATCH):
        if cancel(): break
        cmd = base + ["--"] + files[i:i + _BATCH]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, errors="replace")
        except OSError:
            continue
        try:
            for line in proc.stdout:
                if cancel(): break
                try: ev = json.loads(line)
                except ValueError: continue
                if ev.get("type") == "match":
                    path = ev["data"]["path"].get("text")
                    if path is None: continue
                    path = os.path.abspath(path)
                    lst = res.setdefault(path, [])
                    if len(lst) < 200:
                        ln = ev["data"].get("line_number") or 0
                        txt = ev["data"]["lines"].get("text", "").rstrip("\n")
                        lst.append((ln, txt))
        finally:
            engine._reap(proc)                    # B1: nunca deixar rg órfão
    return res


if __name__ == "__main__":
    import sys
    expr = sys.argv[2] if len(sys.argv) > 2 else '(def OR class) AND import NOT test'
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    q = engine.Query(paths=[root], name_patterns=["*.py"])
    print("AST:", parse(expr))
    print("positivos:", positive_terms(parse(expr)))
    tot, dt = search_boolean(q, expr,
        lambda m: print(f"{m.nmatch:>3} linhas  {m.path}"))
    print(f"\n{tot} arquivos em {dt:.3f}s")
