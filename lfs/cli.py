#!/usr/bin/env python3
# Linux File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Linux File Search — CLI (same core as the GUI, for scripts/daemons)."""
from __future__ import annotations
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine, version
from engine import Query


# A GPL pede que o programa saiba declarar licença e ausência de garantia. Fica
# aqui, num --version que só aparece quando pedido: aviso que interrompe o uso
# (pop-up, lembrete recorrente) não é respeito à licença, é incômodo.
NOTICE = """Linux File Search {release}  {build}
Copyright (C) 2026 Rodrigo Toledo
Licença: GNU GPL versão 3 ou posterior <https://gnu.org/licenses/gpl.html>
Software livre: você pode alterá-lo e redistribuí-lo.
NÃO HÁ GARANTIA, na extensão permitida por lei."""


class _PrintNotice(argparse.Action):
    """O action="version" do argparse passa o texto pelo formatador de ajuda, que
    REFLUI o parágrafo e junta as linhas — o aviso de licença vira um bolo. Este
    imprime como está escrito."""

    def __call__(self, parser, ns, values, option_string=None):
        print(NOTICE.format(release=version.RELEASE, build=version.build_info() or ""))
        parser.exit()


def main():
    ap = argparse.ArgumentParser(description="Broad file search (name + content) over ripgrep/fd.")
    ap.add_argument("path", nargs="+", help="folder(s) to search in")
    ap.add_argument("-V", "--version", action=_PrintNotice, nargs=0,
                    help="show version and license, then exit")
    ap.add_argument("-n", "--name", default="",
                    help="name CONTAINS the term ('rotina' finds 'exames de rotina.txt'); "
                         "globs (* ? [) are used as typed; separate several with commas")
    ap.add_argument("-c", "--content", default="", help="text/regex the file must contain")
    ap.add_argument("-b", "--bool", dest="boolexpr", default="", metavar="EXPR",
                    help="BOOLEAN content search: '(A OR B) AND C NOT D' (| & ! and quotes)")
    ap.add_argument("-D", "--docs", action="store_true",
                    help="search INSIDE documents (PDF/docx/epub/zip…) via ripgrep-all (rga)")
    ap.add_argument("--name-regex", action="store_true")
    ap.add_argument("--content-regex", action="store_true")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="ignore case (default is already insensitive; use -s for sensitive)")
    ap.add_argument("-s", "--case-sensitive", action="store_true")
    ap.add_argument("-w", "--word", action="store_true", help="whole word")
    ap.add_argument("--hidden", action="store_true")
    ap.add_argument("--gitignore", action="store_true", help="respect .gitignore")
    ap.add_argument("--one-fs", action="store_true", help="do not cross mounts")
    ap.add_argument("--min-size", type=str, default=None, help="e.g. 10M, 1G")
    ap.add_argument("--days", type=int, default=0, help="modified within the last N days")
    ap.add_argument("-0", "--print0", action="store_true", help="separate paths with NUL (for xargs -0)")
    ap.add_argument("-l", "--files-only", action="store_true", help="path only (no match lines)")
    args = ap.parse_args()

    parse_size = engine.parse_size            # §5: single source (was duplicated)

    # plain text = "contains" (same semantics as the GUI); explicit globs are respected
    names = [engine.as_name_glob(p) for p in args.name.replace(";", ",").split(",")
             if p.strip()] if not args.name_regex else ([args.name] if args.name else [])
    q = Query(
        paths=args.path, name_patterns=names, name_is_regex=args.name_regex,
        content=args.content, content_is_regex=args.content_regex,
        case_sensitive=args.case_sensitive, whole_word=args.word,
        include_hidden=args.hidden, respect_gitignore=args.gitignore,
        one_file_system=args.one_fs, min_size=parse_size(args.min_size),
        modified_after=(time.time()-args.days*86400) if args.days > 0 else None,
        documents=args.docs,
    )
    info = engine.engine_info()
    print(f"# engine: rg={info['ripgrep']} fd={info['fd']} rga={info['rga']}", file=sys.stderr)
    if args.docs and not engine.RGA:
        print("# warning: --docs requested but 'rga' is missing; search will fall back to rg (no PDF/docx extraction)",
              file=sys.stderr)
    sep = "\0" if args.print0 else "\n"
    n = [0]
    # Escrevemos BYTES, não texto. Nome de arquivo no Linux é uma sequência de
    # bytes que não precisa ser UTF-8 válido; o Python o carrega com
    # surrogateescape, e sys.stdout.write() morre com UnicodeEncodeError na
    # primeira foto de câmera com nome quebrado. os.fsencode devolve os bytes
    # originais — que é exatamente o que um pipe para xargs/rm precisa receber.
    wb = sys.stdout.buffer
    def emit(s):
        wb.write(os.fsencode(s))
    def out(m):
        n[0] += 1
        if args.files_only or not m.lines:
            emit(m.path + sep)
        else:
            for ln, txt in m.lines:
                emit(f"{m.path}:{ln}:{txt}{sep}")
    if args.boolexpr:
        import boolean
        try:
            tot, dt = boolean.search_boolean(q, args.boolexpr, out)
        except boolean.BooleanError as e:
            print(f"boolean expression error: {e}", file=sys.stderr); sys.exit(2)
    else:
        tot, dt = engine.search(q, out)
    wb.flush()
    print(f"\n# {tot} files · {dt:.2f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
