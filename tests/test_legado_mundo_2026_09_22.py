#!/usr/bin/env python3
"""Busca de conteúdo em arquivo de codificação LEGADA — qualquer idioma (22/09/2026).

Medido antes: `sfs -c avaliação` não achava o .txt "ANSI" do Windows (cp1252) —
o rg compara os bytes UTF-8 do termo com os bytes cp1252 do arquivo. Decisão do
Rodrigo: sempre ligado, e para o MUNDO ("o programa é de alcance mundial"), não
só para o português. Custo medido: +1% a +6% (a segunda passada com --encoding
custava 2,7×).

Prova aqui: (1) cada idioma acha o arquivo gravado na codificação antiga dele e
exibe a linha legível; (2) ZERO acerto falso num UTF-8 multilíngue que não
contém os termos; (3) rg e fallback Python dão o MESMO resultado; (4) booleano,
-w e caixa; (5) regex do usuário segue como veio; (6) região pelo locale.
Rode:  python3 tests/test_legado_mundo_2026_09_22.py
"""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, boolean                                        # noqa: E402
from engine import Query                                      # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

# (arquivo, codificação, texto, termo digitado, linha que tem de aparecer)
CASOS = [
    ("pt_ansi.txt",   "cp1252",    "Avaliação do paciente\n", "avaliação", "Avaliação do paciente"),
    ("pt_dos.txt",    "cp850",     "CONCLUSÃO: normal\n",     "conclusão", "CONCLUSÃO: normal"),
    ("ru_1251.txt",   "cp1251",    "Анализ крови\n",          "анализ",    "Анализ крови"),
    ("ru_koi8.txt",   "koi8_r",    "АНАЛИЗ КРОВИ\n",          "анализ",    "АНАЛИЗ КРОВИ"),
    ("pl_1250.txt",   "cp1250",    "Łódź szpital\n",          "łódź",      "Łódź szpital"),
    ("el_1253.txt",   "cp1253",    "Ελλάδα νοσοκομείο\n",     "ελλάδα",    "Ελλάδα νοσοκομείο"),
    ("tr_1254.txt",   "cp1254",    "Şehir hastanesi\n",       "şehir",     "Şehir hastanesi"),
    ("he_1255.txt",   "cp1255",    "שלום עולם\n",             "שלום",      "שלום עולם"),
    ("ar_1256.txt",   "cp1256",    "تحليل الدم\n",            "تحليل",     "تحليل الدم"),
    ("ja_sjis.txt",   "shift_jis", "東京都の検査\n",          "東京",      "東京都の検査"),
    ("zh_gbk.txt",    "gbk",       "北京医院\n",              "北京",      "北京医院"),
    ("zh_big5.txt",   "big5",      "臺北醫院\n",              "臺北",      "臺北醫院"),
    ("ko_euckr.txt",  "euc_kr",    "서울 병원\n",             "서울",      "서울 병원"),
]
# UTF-8 multilíngue SEM nenhum dos termos — o alvo do acerto falso
PALHEIRO = ("Relatório médico: exame sem alterações, você e a avó estão bem. "
            "Анкета врача. Łąka zielona. Ελληνικά γράμματα. Şeker pancarı. "
            "שנה טובה. تقرير طبي. 马鹿野郎 東の空 京都 부산역 근처 ☺😀🙂 "
            "대한민국 병원 검사 결과 정상입니다 한국어 문장 😀서 🙂울 "
            "café crème à la carte, niño, straße, Ærø, Øresund, İstanbul, Sài Gòn cũ.\n") * 50

T = tempfile.mkdtemp(prefix="sfs_legado_")
try:
    for nome, enc, texto, _t, _l in CASOS:
        with open(os.path.join(T, nome), "w", encoding=enc) as f:
            f.write(texto)
    vi = engine._forma_cp1258("Thủ đô Hà Nội\n").encode("cp1258")
    open(os.path.join(T, "vi_1258.txt"), "wb").write(vi)
    CASOS.append(("vi_1258.txt", "cp1258", None, "hà nội", "Thủ đô Hà Nội"))
    with open(os.path.join(T, "palheiro_utf8.txt"), "w", encoding="utf-8") as f:
        f.write(PALHEIRO)

    def busca(termo, python=False, **kw):
        salvos = (engine.RG, engine.RGA, engine.FD)
        if python:
            engine.RG = engine.RGA = engine.FD = ""
        try:
            achados = []
            engine.search(Query(paths=[T], content=termo, **kw), achados.append)
            return {os.path.basename(m.path): m for m in achados}
        finally:
            engine.RG, engine.RGA, engine.FD = salvos

    # (1) cada idioma acha o seu, e a linha sai legível — nos dois motores
    for nome, enc, _x, termo, linha in CASOS:
        for motor, py in (("rg", False), ("python", True)):
            r = busca(termo, python=py)
            txt = r[nome].lines[0][1] if nome in r else None
            ok(nome in r and txt == linha,
               f"[{motor:6}] {termo!r} acha {nome} ({enc}) e mostra {txt!r}")
            # (2) zero acerto falso no UTF-8 multilíngue
            ok("palheiro_utf8.txt" not in r,
               f"[{motor:6}] {termo!r}: nenhum acerto falso no UTF-8 multilíngue")

    # (3) paridade de conjunto, termo a termo
    for _n, _e, _x, termo, _l in CASOS:
        a, b = set(busca(termo)), set(busca(termo, python=True))
        ok(a == b, f"paridade rg == python para {termo!r} ({sorted(a ^ b) or 'igual'})")

    # (4) booleano, palavra inteira e caixa
    r = {}
    boolean.search_boolean(Query(paths=[T]), "анализ AND крови",
                           lambda m: r.setdefault(os.path.basename(m.path), m))
    ok(set(r) == {"ru_1251.txt", "ru_koi8.txt"}, f"booleano em russo acha cp1251 E KOI8-R ({sorted(r)})")
    with open(os.path.join(T, "avo.txt"), "w", encoding="cp1252") as f:
        f.write("minha avó chegou\navós e netos\n")
    r = busca("avó", whole_word=True)
    ok("avo.txt" in r and len(r["avo.txt"].lines) == 1, "-w 'avó' acha 'avó' e não 'avós'")
    r = busca("avaliação", case_sensitive=True)
    ok("pt_ansi.txt" not in r, "caixa sensível: 'avaliação' não casa 'Avaliação' em cp1252")
    r = busca("Avaliação", case_sensitive=True)
    ok("pt_ansi.txt" in r, "caixa sensível: 'Avaliação' casa 'Avaliação' em cp1252")

    # (4b) NFD (macOS): mesma palavra composta e decomposta no mesmo arquivo
    import unicodedata
    with open(os.path.join(T, "mac_nfd.txt"), "w", encoding="utf-8") as f:
        f.write("Avaliação composta\n" + unicodedata.normalize("NFD", "Avaliação decomposta") + "\n")
    for motor, py in (("rg", False), ("python", True)):
        r = busca("avaliação", python=py)
        n = len(r["mac_nfd.txt"].lines) if "mac_nfd.txt" in r else 0
        ok(n == 2, f"[{motor:6}] NFD do Mac: acha as 2 linhas, composta e decomposta ({n})")

    # (5) regex do usuário: como veio (sem variante)
    ok(engine.rg_padroes(["avalia..o"], Query(paths=[T], content_is_regex=True))
       == ["-e", "avalia..o"], "regex do usuário segue como veio")
    ok(engine.rg_padroes(["laudo"], Query(paths=[T])) == ["--fixed-strings", "-e", "laudo"],
       "termo ASCII: --fixed-strings, como sempre (custo zero)")
    ok(engine.legado_variantes("é") == (), "'é' sozinho não gera variante (E9 começa ideograma)")

    # (6) região pelo locale + override
    for loc, esp in (("pt_BR.UTF-8", "cp1252"), ("ru_RU.UTF-8", "cp1251"), ("ja_JP.UTF-8", "shift_jis"),
                     ("zh_TW.UTF-8", "big5"), ("zh_CN.UTF-8", "gbk"), ("pl_PL.UTF-8", "cp1250"),
                     ("C", "cp1252")):
        ok(engine.codificacao_legada({"LANG": loc}) == esp, f"locale {loc} -> {esp}")
    ok(engine.codificacao_legada({"LANG": "pt_BR.UTF-8", "SFS_LEGACY_ENCODING": "koi8-r"}) == "koi8_r",
       "SFS_LEGACY_ENCODING força a codificação")
    ok(engine.codificacao_legada({"SFS_LEGACY_ENCODING": "nao-existe", "LANG": "ru_RU"}) == "cp1251",
       "SFS_LEGACY_ENCODING inválida é ignorada")

    # CLI de ponta a ponta (a linha legível chega ao usuário)
    p = subprocess.run([sys.executable, os.path.join(RAIZ, "lfs", "cli.py"), T, "-c", "анализ"],
                       capture_output=True, text=True, timeout=60)
    ok("ru_koi8.txt:1:АНАЛИЗ КРОВИ" in p.stdout, "CLI mostra a linha KOI8-R legível")
finally:
    shutil.rmtree(T, ignore_errors=True)

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
