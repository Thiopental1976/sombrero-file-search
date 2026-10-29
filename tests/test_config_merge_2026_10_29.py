#!/usr/bin/env python3
"""save_cfg faz merge de 3 vias com o disco (29/10/2026: a janela aberta apagou a
`flash_ativa` que outro processo tinha gravado no config).
Contratos: chave nova de fora sobrevive; valor mudado por fora e intocado na janela
fica o de fora; o que a janela mudou vale; o que a janela apagou some; apagado por
fora e intocado aqui some; gravação atômica (sem .tmp sobrando)."""
import json, os, sys, tempfile
TMP = tempfile.mkdtemp(prefix="cfg_merge_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lfs"))
falhas = []
def ok(c, m):
    print(("ok  " if c else "FALHOU: ") + "  " + m)
    if not c: falhas.append(m)
import app as A
p = os.path.expanduser(A.CONFIG)
os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump({"tema": "dark", "flash": True, "larg": [1, 2], "velha": 1, "some_fora": 7}, open(p, "w"))
cfg = A.load_cfg()
# outro processo grava por fora
fora = json.load(open(p)); fora["flash_ativa"] = {"ativa": True}; fora["tema"] = "light"; del fora["some_fora"]
json.dump(fora, open(p, "w"))
# a janela muda o que é dela
cfg["larg"].append(3); cfg["window_geometry"] = "abc"; del cfg["velha"]
A.save_cfg(cfg)
d = json.load(open(p))
ok(d.get("flash_ativa") == {"ativa": True}, "chave nova de fora sobrevive")
ok(d.get("tema") == "light", "mudada por fora e intocada na janela: vale a de fora")
ok(d.get("larg") == [1, 2, 3] and d.get("window_geometry") == "abc", "o que a janela mudou/criou vale")
ok("velha" not in d, "o que a janela apagou some")
ok("some_fora" not in d, "apagada por fora e intocada aqui some")
ok(cfg.get("flash_ativa") == {"ativa": True}, "a janela passa a enxergar a chave de fora")
ok(not os.path.exists(p + ".tmp"), "gravação atômica, sem .tmp sobrando")
# segunda gravação: base atualizada, nada volta
cfg["flash"] = False; A.save_cfg(cfg)
d = json.load(open(p))
ok(d.get("flash") is False and d.get("tema") == "light" and d.get("flash_ativa"), "2ª gravação mantém tudo")
import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
