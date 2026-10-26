#!/usr/bin/env python3
"""Arquivo como raiz: a linha do painel dizia "pasta não encontrada" (26/10/2026).

O motor recusa um ARQUIVO como raiz de propósito (H3b: rg aceita, fd recusa
calado, os.walk ignora — recusar nos cinco é a única resposta igual). Mas o
evento `root_skipped` saía com o MESMO `reason` da raiz inexistente,
`invalid_root`, e a GUI traduzia isso por "folder not found". O arquivo
existe; a linha mentia sobre o porquê, e o usuário lia "0 resultados" com o
caminho errado como explicação.

Contratos presos aqui:
  1. arquivo como raiz -> `root_skipped` com reason `not_a_folder`, frase que
     diz que é um arquivo (nunca "not found"), traduzida em português;
  2. raiz inexistente continua `invalid_root` / "folder not found";
  3. o motivo do FUNIL continua `invalid_root` nos dois casos (contrato do
     --json para scripts, documentado no README), grave, exit 2;
  4. a CLI diz que é um arquivo.

Rode:
    python3 tests/test_raiz_arquivo_2026_10_26.py
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, i18n

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

tmp = tempfile.mkdtemp(prefix="sfs_raiz_arquivo_")
arq = os.path.join(tmp, "a.txt")
with open(arq, "w") as f:
    f.write("linha um\nagulha aqui\n")
sumida = os.path.join(tmp, "nao_existe")

def gate(root):
    evs, stats = [], {}
    vivo = engine._raiz_existe(root, stats, lambda ev, info: evs.append((ev, info)))
    reasons = [i.get("reason") for e, i in evs if e == "root_skipped"]
    motivos = [e["motivo"] for e in (stats.get("incompleto") or [])]
    return vivo, reasons, motivos

# 1. arquivo
vivo, reasons, motivos = gate(arq)
ok(not vivo, "arquivo como raiz é recusado (H3b mantido)")
ok(reasons == ["not_a_folder"], f"root_skipped do arquivo = not_a_folder ({reasons})")
frase = engine.REASON_TEXTO.get("not_a_folder", "")
ok(frase and "not found" not in frase and "file" in frase,
   f"frase do painel diz que é arquivo ({frase!r})")
ok(motivos == ["invalid_root"], f"motivo do funil segue invalid_root ({motivos})")
salva = i18n.current_lang()
try:
    i18n.set_lang("pt")
    pt = i18n.t(frase) if frase else ""
    ok(pt and pt != frase and "arquivo" in pt, f"frase traduzida em português ({pt!r})")
finally:
    i18n.set_lang(salva)

# 2. inexistente
vivo, reasons, motivos = gate(sumida)
ok(not vivo and reasons == ["invalid_root"], f"raiz inexistente segue invalid_root ({reasons})")
ok(engine.REASON_TEXTO["invalid_root"] == "folder not found", "inexistente segue 'folder not found'")

# 3 e 4. CLI ponta a ponta
cli = [sys.executable, os.path.join(RAIZ, "lfs", "cli.py")]
env = dict(os.environ, LANG="C.UTF-8")
p = subprocess.run(cli + ["-c", "agulha", arq], capture_output=True, text=True, env=env, timeout=120)
ok(p.returncode == 2, f"CLI com arquivo como raiz sai 2 ({p.returncode})")
ok("is a file" in p.stderr, "CLI diz que é um arquivo")
p = subprocess.run(cli + ["-c", "agulha", "--json", arq], capture_output=True, text=True, env=env, timeout=120)
inc = [json.loads(L) for L in p.stdout.splitlines() if L.strip().startswith("{")]
inc = [o for o in inc if "incomplete" in (o.get("warn"), o.get("error"))]
ok([o.get("reason") for o in inc] == ["invalid_root"],
   f"--json: reason segue invalid_root ({[o.get('reason') for o in inc]})")

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]; sys.exit(1)
print("\ntodos os testes passaram")
