#!/usr/bin/env python3
"""Busca por NOME com nome de arquivo em codificação LEGADA (22/09/2026).

Medido antes, dois defeitos:
  1. `-n médico` não achava "laudo_m\\xe9dico.txt" (nome gravado em cp1252): o fd
     compara os BYTES do nome com os bytes UTF-8 do termo;
  2. com 4+ globs (fundidos numa regex só, opt#3), `*.txt` achava 1 de 4 — o `.`
     Unicode do Rust não atravessa byte inválido, e o nome não-UTF-8 sumia CALADO.
Mesma técnica da busca de conteúdo (test_legado_mundo): o glob também casa os
bytes em cada codificação legada, e o critério contra acerto falso vale por
TRECHO LITERAL (o `*` não ancora nada: `-n é` casava nome chinês em UTF-8).
Rode:  python3 tests/test_nome_legado_2026_09_22.py
"""
from __future__ import annotations
import os, shutil, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine                                                 # noqa: E402
from engine import Query                                      # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

NOMES = {                                   # rótulo -> bytes do nome no disco
    "laudo_cp1252":   "laudo_médico.txt".encode("cp1252"),
    "relat_cp1252":   "relatório_ÇÃO.txt".encode("cp1252"),
    "MEDICO_cp1252":  "EXAME_MÉDICO.txt".encode("cp1252"),
    "analise_cp1251": "Анализ_крови.txt".encode("cp1251"),
    "analise_koi8":   "АНАЛИЗ_2019.txt".encode("koi8_r"),
    "toquio_sjis":    "東京_報告.txt".encode("shift_jis"),
    "normal_utf8":    "normal_médico.txt".encode(),
    "chines_utf8":    "马鹿.txt".encode(),          # E9 A9 AC…: o alvo do acerto falso
    "japones_utf8":   "京都_メモ.txt".encode(),
    "emoji_utf8":     "foto_😀.txt".encode(),
    "espaco_utf8":    b"exames de rotina.txt",
}

T = tempfile.mkdtemp(prefix="sfs_nomeleg_")
try:
    tb = os.fsencode(T)
    por_nome = {}
    for rot, b in NOMES.items():
        open(os.path.join(tb, b), "w").close()
        por_nome[os.fsdecode(b)] = rot

    def busca(globs, python=False, **kw):
        salvos = (engine.RG, engine.RGA, engine.FD)
        if python:
            engine.RG = engine.RGA = engine.FD = ""
        try:
            r = []
            engine.search(Query(paths=[T], name_patterns=list(globs), **kw), r.append)
            return {por_nome.get(os.path.basename(m.path), "?") for m in r}
        finally:
            engine.RG, engine.RGA, engine.FD = salvos

    g = engine.as_name_glob
    casos = [
        ([g("médico")],  {"laudo_cp1252", "MEDICO_cp1252", "normal_utf8"}, "médico acha cp1252 + UTF-8"),
        ([g("MÉDICO")],  {"laudo_cp1252", "MEDICO_cp1252", "normal_utf8"}, "caixa: MÉDICO acha médico"),
        ([g("ção")],     {"relat_cp1252"},                                 "ção acha relatório_ÇÃO (outro byte cru antes)"),
        ([g("анализ")],  {"analise_cp1251", "analise_koi8"},               "анализ acha cp1251 E KOI8-R"),
        ([g("東京")],    {"toquio_sjis"},                                  "東京 acha nome Shift-JIS"),
        ([g("é")],       {"normal_utf8"},                                  "'é' sozinho: só UTF-8 (sem acerto falso em 马鹿)"),
        (["*.txt", "*.a", "*.b", "*.c"], set(NOMES),                       "4+ globs fundidos acham TODOS (antes: 1 de 4)"),
        (["exames?de*", "*.a", "*.b", "*.c"], {"espaco_utf8"},             "4+ globs: '?' e espaço seguem certos"),
        (["*médico*", "*.a", "*.b", "*.c"],
         {"laudo_cp1252", "MEDICO_cp1252", "normal_utf8"},                 "4+ globs com acento: variantes na fusão"),
    ]
    for globs, esperado, oque in casos:
        a, b = busca(globs), busca(globs, python=True)
        ok(a == esperado, f"[fd    ] {oque} ({sorted(a)})")
        ok(b == esperado, f"[python] {oque} ({sorted(b)})")
    ok(busca([g("médico")], case_sensitive=True) == {"laudo_cp1252", "normal_utf8"},
       "caixa sensível: médico não casa MÉDICO")

    # o dialeto Python do _glob_to_regex não mudou (test_glob_to_regex o usa)
    ok(engine._glob_to_regex("*.py") == r"^.*\.py$", "dialeto Python intacto")
    ok(engine._encs_do_glob("*é*") == [], "critério por trecho: '*é*' sem variante")
    ok("cp1252" in engine._encs_do_glob("*médico*"), "critério por trecho: '*médico*' tem cp1252")
finally:
    shutil.rmtree(T, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
