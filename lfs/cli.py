#!/usr/bin/env python3
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Sombrero File Search — CLI (same core as the GUI, for scripts/daemons)."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine, version
from engine import Query


# A GPL pede que o programa saiba declarar licença e ausência de garantia. Fica
# aqui, num --version que só aparece quando pedido: aviso que interrompe o uso
# (pop-up, lembrete recorrente) não é respeito à licença, é incômodo.
NOTICE = """Sombrero File Search {release}  {build}
Copyright (C) 2026 Rodrigo Toledo
License: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law."""


class _PrintNotice(argparse.Action):
    """O action="version" do argparse passa o texto pelo formatador de ajuda, que
    REFLUI o parágrafo e junta as linhas — o aviso de licença vira um bolo. Este
    imprime como está escrito."""

    def __call__(self, parser, ns, values, option_string=None):
        print(NOTICE.format(release=version.RELEASE, build=version.build_info() or ""))
        parser.exit()


def main():
    # A CLI fala INGLÊS em qualquer locale (decisão do Rodrigo, 21/09/2026: o
    # programa é de alcance mundial). Não é só estética: o `detail` do --json é
    # contrato de automação, e o BooleanError passa por i18n.t() — numa máquina
    # pt_BR o mesmo script recebia "aspas sem fechamento" onde outra recebia
    # "unclosed quote". A GUI segue o locale; a CLI, não.
    import i18n
    i18n.set_lang("en")
    ap = argparse.ArgumentParser(description="Broad file search (name + content) over ripgrep/fd.")
    ap.add_argument("path", nargs="+", help="folder(s) to search in")
    ap.add_argument("-V", "--version", action=_PrintNotice, nargs=0,
                    help="show version and license, then exit")
    ap.add_argument("-n", "--name", default="",
                    help="name CONTAINS the term ('rotina' finds 'exames de rotina.txt'); "
                         "globs with * or ? match the whole name as typed; brackets alone are "
                         "searched both ways ('[2019]' finds '[2019] Reports'); separate several with commas")
    ap.add_argument("-c", "--content", default="", help="text/regex the file must contain")
    ap.add_argument("-b", "--bool", dest="boolexpr", default="", metavar="EXPR",
                    help="BOOLEAN content search: '(A OR B) AND C NOT D' (| & ! and quotes)")
    ap.add_argument("-D", "--docs", action="store_true",
                    help="search INSIDE documents (PDF/docx/epub/zip…) via ripgrep-all (rga)")
    ap.add_argument("--name-regex", action="store_true")
    ap.add_argument("--content-regex", action="store_true")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="ignore case (the default; overrides -s)")
    ap.add_argument("-s", "--case-sensitive", action="store_true")
    ap.add_argument("-w", "--word", action="store_true", help="whole word")
    ap.add_argument("--hidden", action="store_true")
    ap.add_argument("--gitignore", action="store_true", help="respect .gitignore")
    ap.add_argument("--one-fs", action="store_true", help="do not cross mounts")
    ap.add_argument("--snapshots", action="store_true",
                    help="ALWAYS search system snapshot trees too (Timeshift, snapper, ZFS, "
                         "ostree deployments). By default they are searched only when the "
                         "live tree gives nothing for that path (they are copies of the OS "
                         "and can multiply the walk by 10x); results from them are marked")
    # 21/09/2026: tamanho inválido é ERRO (exit 2). Antes `--min-size 10X` virava
    # None no parse_size e a busca rodava SEM filtro, calada — o usuário concluía
    # que o filtro valera.
    def _tamanho(s):
        n = engine.parse_size(s)
        if n is None:
            raise argparse.ArgumentTypeError(f"invalid size {s!r} (e.g. 500K, 10M, 1.5G)")
        return n

    def _profundidade(s):
        try:
            n = int(s)
        except ValueError:
            n = 0
        if n < 1:
            raise argparse.ArgumentTypeError(f"invalid depth {s!r} (1 = only the folder given)")
        return n

    ap.add_argument("--min-size", type=_tamanho, default=None, metavar="SIZE",
                    help="at least this size, e.g. 10M, 1G")
    ap.add_argument("--max-size", type=_tamanho, default=None, metavar="SIZE",
                    help="at most this size, e.g. 500K, 2G")
    ap.add_argument("--depth", type=_profundidade, default=None, metavar="N",
                    help="descend at most N levels (1 = only the folder given, 2 = one "
                         "level of subfolders…)")
    ap.add_argument("--follow", action="store_true",
                    help="follow symbolic links into the folders they point to "
                         "(link loops are cut)")
    ap.add_argument("--days", type=int, default=0, help="modified within the last N days")
    ap.add_argument("-0", "--print0", action="store_true", help="separate paths with NUL (for xargs -0)")
    ap.add_argument("-l", "--files-only", action="store_true", help="path only (no match lines)")
    ap.add_argument("--json", action="store_true",
                    help="NDJSON: one object per match (path,size,mtime,nmatch,lines[],snapshot,"
                         "copies[]) plus warn events and {copy,of,snapshot} for a duplicate "
                         "absorbed after its owner was printed; exit code grep-style "
                         "(0=found, 1=none, 2=error). For automation.")
    ap.add_argument("--nice-io", action="store_true",
                    help="lower CPU + I/O priority (nice 19 + ionice idle) so cron/background "
                         "searches don't fight the server's foreground work")
    ap.add_argument("--index", action="store_true",
                    help="NAME search only: use the plocate index (fast; results as of the "
                         "index date). Refuses if any part of the path is pruned from the index "
                         "(would hide a subtree silently) — then use the live search.")
    args = ap.parse_args()
    if (args.min_size is not None and args.max_size is not None
            and args.min_size > args.max_size):
        ap.error("--min-size is larger than --max-size: nothing could match")

    if args.nice_io:                          # F9b §3.5: busca de fundo cede a vez
        try:
            os.nice(19)
        except OSError:
            pass
        ionice = shutil.which("ionice")       # ioprio idle: sem stdlib; ionice no self
        if ionice:                            # (os filhos rg/fd herdam a classe)
            try:
                subprocess.run([ionice, "-c", "3", "-p", str(os.getpid())],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass

    # plain text = "contains" (same semantics as the GUI); explicit globs are respected
    # as_name_globs: `[2019]` também é buscado como texto literal (22/09/2026)
    names = [g for p in args.name.replace(";", ",").split(",") if p.strip()
             for g in engine.as_name_globs(p)] if not args.name_regex else ([args.name] if args.name else [])
    q = Query(
        paths=args.path, name_patterns=names, name_is_regex=args.name_regex,
        content=args.content, content_is_regex=args.content_regex,
        # -i vence -s: é pedido explícito (22/09/2026 — antes -i era aceito e ignorado)
        case_sensitive=args.case_sensitive and not args.ignore_case, whole_word=args.word,
        include_hidden=args.hidden, respect_gitignore=args.gitignore,
        one_file_system=args.one_fs, skip_snapshots=not args.snapshots,
        min_size=args.min_size, max_size=args.max_size,       # já em bytes (_tamanho)
        max_depth=args.depth, follow_symlinks=args.follow,
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
    stats: dict = {}
    # Escrevemos BYTES, não texto. Nome de arquivo no Linux é uma sequência de
    # bytes que não precisa ser UTF-8 válido; o Python o carrega com
    # surrogateescape, e sys.stdout.write() morre com UnicodeEncodeError na
    # primeira foto de câmera com nome quebrado. os.fsencode devolve os bytes
    # originais — que é exatamente o que um pipe para xargs/rm precisa receber.
    wb = sys.stdout.buffer
    # Revisão Fable 21/09/2026 — `sfs … | head -1` despejava um traceback de
    # BrokenPipeError: o leitor fechou o pipe e nós seguíamos escrevendo. Quando
    # isso acontece a busca é CANCELADA (ninguém mais lê; seguir varrendo o disco
    # é desperdício — num SMR, minutos dele) e as escritas viram no-op.
    pipe = {"fechado": False}
    def _escreve(b):
        if pipe["fechado"]:
            return
        try:
            wb.write(b)
        except BrokenPipeError:
            pipe["fechado"] = True
    def _descarrega():
        if pipe["fechado"]:
            return
        try:
            wb.flush()
        except BrokenPipeError:
            pipe["fechado"] = True
    def parar():
        return pipe["fechado"]
    def emit(s):
        _escreve(os.fsencode(s))
    def emit_json(obj):
        # surrogatepass: nomes não-UTF-8 sobrevivem como WTF-8; o json escapa \n
        # DENTRO da string, então um nome com quebra de linha nunca racha o NDJSON.
        _escreve(json.dumps(obj, ensure_ascii=False).encode("utf-8", "surrogatepass") + b"\n")
    def out_json(m):
        n[0] += 1
        # 09/09/2026: `snapshot` = árvore podada de origem (null = árvore viva);
        # `copies` = caminhos que o dedup colapsou neste ATÉ AQUI. NDJSON é
        # streaming: cópia absorvida DEPOIS de o dono ter sido impresso sai
        # como {"copy": ..., "of": dono, "snapshot": ...} (ver on_copy).
        emit_json({"path": m.path, "size": m.size, "mtime": m.mtime,
                   "is_dir": m.is_dir, "nmatch": m.nmatch,
                   "lines": [[ln, txt] for ln, txt in m.lines],
                   "snapshot": m.snapshot, "copies": list(m.copies)})
    def on_copy(ev, info):
        if ev == "copy" and args.json:
            emit_json({"copy": info.get("path"), "of": info.get("of"),
                       "snapshot": info.get("snapshot")})
    def out_text(m):
        n[0] += 1
        if args.files_only or not m.lines:
            emit(m.path + sep)
        else:
            for ln, txt in m.lines:
                emit(f"{m.path}:{ln}:{txt}{sep}")
    out = out_json if args.json else out_text
    if args.index:
        # F9b §3.2: aceleração por índice, opt-in. Recusa se a cobertura estiver
        # furada (poda) — nunca degrada em silêncio. Sempre anuncia a data.
        import indexed
        if args.boolexpr or args.content:
            print("# error: --index speeds up NAME search only; for content/boolean use the live search",
                  file=sys.stderr)
            sys.exit(2)
        if args.follow:
            # o updatedb não atravessa symlink: o que só se alcança por link sumiria
            # do resultado em silêncio — a mentira que o --index existe para não contar
            print("# error: --index cannot follow symlinks (the index does not go through "
                  "them); drop --follow or use the live search", file=sys.stderr)
            sys.exit(2)
        idate = indexed.index_date()
        if not indexed.index_available():
            print("# error: --index requested but plocate (or its database) is not available — use the live search",
                  file=sys.stderr)
            sys.exit(2)
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(idate)) if idate else "?"
        print(f"# index: results as of the index built on {when} (NOT the disk as it is now)",
              file=sys.stderr)
        if args.json:
            emit_json({"warn": "index_used", "index_date": idate})
        t0 = time.time()
        try:
            for m in indexed.search_indexed(q):
                out(m)
                if parar():
                    break
        except indexed.IndexError_ as e:
            if args.json:
                emit_json({"error": "index_coverage", "detail": str(e)}); _descarrega()
            print(f"# error: {e}", file=sys.stderr)
            sys.exit(2)
        tot, dt = n[0], time.time() - t0
        _descarrega()
        print(f"\n# {tot} files · {dt:.2f}s (index of {when})", file=sys.stderr)
        sys.exit(0 if tot > 0 else 1)
    if args.boolexpr:
        import boolean
        try:
            tot, dt = boolean.search_boolean(q, args.boolexpr, out, cancel=parar,
                                             stats=stats, on_event=on_copy)
        except boolean.BooleanError as e:
            if args.json:
                emit_json({"error": "boolean_expression", "detail": str(e)}); _descarrega()
            print(f"boolean expression error: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        tot, dt = engine.search(q, out, cancel=parar, stats=stats, on_event=on_copy)
    # F9a §2.2 + F9b §3.4: avisos NO MESMO stream (json) e no stderr (texto) —
    # montagem de rede morta pulada e diretórios sem permissão. Parcial anunciado.
    skipped = stats.get("skipped_mounts") or []
    denied = stats.get("denied", 0)
    # F11b: o motor (fd/rg) pode ter SAÍDO COM ERRO — flag não suportada numa
    # versão antiga, por exemplo. Sem isto a busca devolvia zero resultados em
    # silêncio e o usuário concluía que o arquivo não existe.
    if args.json:
        for sk in skipped:
            emit_json({"warn": "mount_dead", "path": sk.get("path"),
                       "mount": sk.get("mount"), "fstype": sk.get("fstype"),
                       "reason": sk.get("reason")})   # 22/09: no_response × broken_mount
        if denied:
            emit_json({"warn": "denied", "count": denied})
        for e in (stats.get("incompleto") or []):
            emit_json({"warn" if not (e["motivo"] in engine.MOTIVOS_GRAVES or e.get("grave")) else "error":
                       "incomplete", "reason": e["motivo"], "where": e["onde"],
                       "detail": engine.texto_detalhe(e), "count": e["n"]})
    _descarrega()
    for sk in skipped:
        # 22/09/2026: "not responding" só quando é o caso; montagem que RESPONDEU
        # com erro de montagem morta (ESTALE, ENOTCONN…) é "broken"
        oque = "broken" if sk.get("reason") == "broken_mount" else "not responding"
        print(f"# warning: mount {oque} — skipped: {sk.get('mount')} "
              f"({sk.get('fstype')})", file=sys.stderr)
    if denied:
        print(f"# warning: {denied} directories without permission — partial results",
              file=sys.stderr)
    pruned = stats.get("pruned_mounts") or []
    if pruned:            # F12: nota, não perda — não há arquivo de usuário em /proc
        print(f"# note: {len(pruned)} kernel filesystem(s) not searched: "
              f"{', '.join(pruned[:6])}{'…' if len(pruned) > 6 else ''}", file=sys.stderr)
    # F11c: o aviso e o exit code DERIVAM do funil único (engine.anota_incompleto),
    # não de cada canal solto. Quem adiciona uma perda nova em qualquer módulo
    # aparece aqui de graça.
    grave, linhas = engine.resumo_incompleto(stats)
    for L in linhas:
        print(f"# incomplete: {L}", file=sys.stderr)
    if grave:
        print("#        results are INCOMPLETE — this is not 'nothing was found'",
              file=sys.stderr)
    print(f"\n# {tot} files · {dt:.2f}s", file=sys.stderr)
    # contrato de exit code estilo grep: 0=achou, 1=nada, 2=erro (F9b §3.1).
    # F11b: motor que falhou e devolveu zero NÃO é "nada encontrado" — é erro.
    # Sair 1 aqui faria um script chamador concluir que o arquivo não existe.
    # "grave" = o resultado pode estar ERRADO (motor falhou/ausente, disco caiu),
    # não apenas incompleto. Uma pasta do sistema negando leitura NÃO muda o
    # código de saída: um script que faz `sfs ... || echo "não achei"` não pode
    # passar a falhar por causa disso.
    if grave:
        sys.exit(2)
    sys.exit(0 if tot > 0 else 1)


def _main_protegido():
    """main() com as duas saídas que todo filtro Unix precisa ter limpas:
    Ctrl-C sai 130 sem traceback (os fd/rg filhos morrem no finally do motor, e
    o SIGINT do terminal já os alcança por estarem no mesmo grupo); e o stdout
    fechado pelo leitor não estoura no flush final do interpretador."""
    try:
        main()
    except KeyboardInterrupt:
        print("\n# interrupted", file=sys.stderr)
        code = 130
    except SystemExit as e:
        code = e.code
    else:
        code = 0
    try:
        sys.stdout.flush()
    except (BrokenPipeError, ValueError):
        pass
    # se o leitor fechou o pipe, o flush do atexit estouraria de novo: aponta o
    # stdout pro /dev/null (receita da documentação do Python, "SIGPIPE")
    try:
        if sys.stdout is not None:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass
    sys.exit(code)


if __name__ == "__main__":
    _main_protegido()
