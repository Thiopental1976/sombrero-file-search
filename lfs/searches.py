#!/usr/bin/env python3
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Sombrero File Search — buscas salvas, histórico e exportação (F5).

Sem Qt, como engine.py e fileops.py: o que dá para testar sem abrir uma tela
mora fora da GUI. Aqui estão as três coisas do F5 que são *dados*, não widgets:

1. **Snapshot do formulário** — uma busca salva é o formulário inteiro, não só
   o termo. Reabrir uma busca salva tem que reproduzir o resultado, e isso
   inclui os toggles (caixa, palavra inteira, ocultos, gitignore…) e as pastas.
2. **Histórico** — as últimas buscas, sem repetição e sem crescer para sempre.
3. **Exportar** — CSV e JSON a partir dos resultados.

Uma decisão que atravessa o módulo: **o snapshot é um dicionário de tipos
JSON simples**, e ler um snapshot velho nunca pode quebrar. O config do usuário
sobrevive a versões do app; um campo novo que não existia no snapshot antigo
assume o padrão, e um campo que o app não conhece mais é ignorado em silêncio.
Por isso `apply` percorre as CHAVES CONHECIDAS, e não as chaves do arquivo.
"""
from __future__ import annotations
import csv, json, os, time

# Campos do formulário que definem uma busca. A ordem não importa para a
# semântica, mas importa para o humano que vai abrir o config.json na mão.
DEFAULTS = {
    "name": "",             # padrão de nome / glob
    "content": "",          # texto ou expressão de conteúdo
    "paths": "",            # pastas separadas por ';' (como no campo "In")
    "name_regex": False,
    "content_regex": False,
    "boolean": False,
    "documents": False,
    "case": False,
    "word": False,
    "recursive": True,
    "hidden": False,
    "gitignore": True,
    "one_fs": False,
    "min_size": "",
    "days": 0,
}

HISTORY_CAP = 30            # o suficiente para "aquela busca de ontem"


def normalize(form: dict) -> dict:
    """Completa com os padrões e descarta chave desconhecida. É o que torna
    seguro ler config de uma versão anterior (ou posterior) do app."""
    out = {}
    for k, padrao in DEFAULTS.items():
        v = form.get(k, padrao)
        if isinstance(padrao, bool):
            v = bool(v)
        elif isinstance(padrao, int) and not isinstance(padrao, bool):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = padrao
        else:
            v = "" if v is None else str(v)
        out[k] = v
    return out


def is_empty(form: dict) -> bool:
    """Busca sem nome, sem conteúdo e sem filtro de tamanho/data não merece ir
    para o histórico — seria "tudo em ~", que o usuário não vai querer repetir."""
    f = normalize(form)
    return not (f["name"] or f["content"] or f["min_size"] or f["days"])


def same(a: dict, b: dict) -> bool:
    return normalize(a) == normalize(b)


def add_history(cfg: dict, form: dict, cap: int = HISTORY_CAP) -> list:
    """Insere no topo, sem duplicar. Repetir a mesma busca REORDENA (sobe para o
    topo) em vez de criar uma segunda entrada — histórico com a mesma linha três
    vezes é ruído, não memória."""
    hist = [normalize(h) for h in cfg.get("history", []) if isinstance(h, dict)]
    f = normalize(form)
    if is_empty(f):
        return hist
    hist = [h for h in hist if h != f]
    hist.insert(0, f)
    del hist[cap:]
    cfg["history"] = hist
    return hist


def saved_list(cfg: dict) -> list:
    """[(nome, form)] na ordem em que o usuário salvou."""
    out = []
    for it in cfg.get("saved", []):
        if isinstance(it, dict) and it.get("name"):
            out.append((str(it["name"]), normalize(it.get("form", {}))))
    return out


def save_search(cfg: dict, nome: str, form: dict) -> list:
    """Salvar com um nome que já existe SOBRESCREVE (e mantém a posição) — é o
    que o usuário espera de "salvar como" com o mesmo nome, e evita duas
    entradas idênticas no menu."""
    nome = (nome or "").strip()
    if not nome:
        return saved_list(cfg)
    itens = [{"name": n, "form": f} for n, f in saved_list(cfg)]
    novo = {"name": nome, "form": normalize(form)}
    for i, it in enumerate(itens):
        if it["name"] == nome:
            itens[i] = novo
            break
    else:
        itens.append(novo)
    cfg["saved"] = itens
    return saved_list(cfg)


def delete_search(cfg: dict, nome: str) -> list:
    cfg["saved"] = [{"name": n, "form": f} for n, f in saved_list(cfg) if n != nome]
    return saved_list(cfg)


def title_for(form: dict, maxlen: int = 22) -> str:
    """Rótulo curto da aba. Prioriza o que o usuário DIGITOU (nome, depois
    conteúdo); sem nenhum dos dois, cai na última pasta — "Documents" diz mais
    que "/home/rodrigo/Documents" numa aba de 22 caracteres."""
    f = normalize(form)
    txt = f["name"] or f["content"]
    if not txt:
        p = [x.strip() for x in f["paths"].split(";") if x.strip()]
        txt = os.path.basename(p[0].rstrip("/")) if p else ""
    txt = " ".join(txt.split())
    if not txt:
        return "•"
    return txt if len(txt) <= maxlen else txt[:maxlen - 1] + "…"


# ------------------------------------------------------------------- exportação
def _rows_of(m):
    """Um Match vira UMA linha por trecho casado (o que o usuário vê na tabela e
    no preview), ou uma única linha quando a busca foi só por nome."""
    base = {
        "path": m.path,
        "folder": os.path.dirname(m.path),
        "name": os.path.basename(m.path),
        "size": 0 if getattr(m, "is_dir", False) else m.size,
        "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m.mtime)) if m.mtime else "",
        "matches": m.nmatch,
    }
    linhas = getattr(m, "lines", None) or []
    if not linhas:
        return [dict(base, line="", text="")]
    return [dict(base, line=n, text=txt.rstrip("\n")) for n, txt in linhas]


def export_csv(matches, fp) -> int:
    """CSV com cabeçalho, separador ';' e aspas quando preciso (é o que o
    LibreOffice pt-BR abre com dois cliques). Devolve o número de linhas."""
    campos = ["path", "folder", "name", "size", "modified", "matches", "line", "text"]
    w = csv.DictWriter(fp, fieldnames=campos, delimiter=";",
                       quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writeheader()
    n = 0
    for m in matches:
        for r in _rows_of(m):
            w.writerow(r)
            n += 1
    return n


def export_json(matches, fp) -> int:
    """Um objeto por ARQUIVO (com a lista de trechos dentro), não por linha: é a
    forma que um script consome bem, e `jq -r '.[].path'` continua trivial."""
    dados = []
    for m in matches:
        dados.append({
            "path": m.path,
            "size": 0 if getattr(m, "is_dir", False) else m.size,
            "mtime": m.mtime,
            "modified": (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(m.mtime))
                         if m.mtime else ""),
            "is_dir": bool(getattr(m, "is_dir", False)),
            "matches": m.nmatch,
            "lines": [{"line": n, "text": txt.rstrip("\n")}
                      for n, txt in (getattr(m, "lines", None) or [])],
        })
    json.dump(dados, fp, ensure_ascii=False, indent=2)
    fp.write("\n")
    return len(dados)


def export(matches, path: str) -> int:
    """Escolhe o formato pela extensão. `.json` → JSON; qualquer outra → CSV."""
    ext = os.path.splitext(path)[1].lower()
    # newline="" é exigência do módulo csv (senão o Windows/Excel vê linha em branco)
    with open(path, "w", newline="", encoding="utf-8") as f:
        return export_json(matches, f) if ext == ".json" else export_csv(matches, f)
