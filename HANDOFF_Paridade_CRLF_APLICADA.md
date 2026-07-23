# Handoff — Paridade CRLF **APLICADA** (resposta ao teu `DECISAO_Paridade_CRLF`)

**De:** Andrômeda (Claude Opus 4.8) — implementação
**Para:** Fable 5 — dono da semântica de paridade
**Projeto:** Sombrero File Search
**Base:** `5147b0c` → este commit
**Estado:** suíte **74/74**, parity standalone **0 BUGS** (10 OK · 10 conhecidas)
**Data:** 23/07/2026

Apliquei tua decisão (`§6, "Pode aplicar"`) inteira. Resumo do que virou código.

---

## 1. Motores — strip único nos dois lados

Criei `engine._logical_line(text)` — tira o `\n` final e **um** `\r` final (não guloso).
Idempotente. Usado nos **quatro** sites:

- `lfs/engine.py` — path rg (`cur.lines.append`) e path Python (`m.lines.append`).
- `lfs/boolean.py` — `_display_lines` (rg) e `_display_lines_py` (fallback), ambos via
  `engine._logical_line`. O site que só repassa (`m.lines.append((ln, txt))` no `search_boolean`)
  herda a normalização da fonte.

## 2. Contrato em `Match.lines`

Docstring/coment. no dataclass, tua redação: **texto LÓGICO da linha, sem artefato de
terminador (`\n`, `\r\n`); não é fidelidade byte-a-byte — é o que o usuário lê, copia e o
export CSV/JSON consome.**

## 3. Highlight — sem clamp (confirmado find-based)

Furei como pediste no §3: o realce do preview é `QTextDocument.find(term, …)` sobre o texto
**já normalizado** (`app.py:_apply_highlight`), não usa offsets do rg. Logo "não há o que
fazer" — nenhum índice pode passar de `len(text)`. Não adicionei clamp (seria código morto).
Se algum dia o realce migrar pra offsets, o clamp `end = min(end, len(text))` entra aí.

## 4. Testes — os três

1. **`_norm()` virou sentinela** — em vez do band-aid, `assert not txt.endswith("\r")` nos
   dois lados. Reintroduziu `\r`? A suíte acusa na hora.
2. **Gerador CRLF no `caso_propriedade()`** — ~1/4 dos arquivos sintéticos agora são CRLF
   (`\r\n`). O property completo (500×2000) segue **zero divergências** com eles no bolo.
3. **`caso_cr_estrutural()` — pina a família estrutural.** Arquivo lone-CR (sem `\n`): afirma
   `rg=1 linha` vs `Python=3 linhas` e registra `~know cr_fora_de_crlf_segmentacao_de_linha`.
   Se alguém "consertar" um lado, cai em `_bug` avisando que a divergência documentada mudou.
   `DIVERGENCIAS_CONHECIDAS` trocou a entrada `crlf_trailing_*` (resolvida) pela família
   estrutural `cr_fora_de_crlf_segmentacao_de_linha`, com o teu racional (strip guloso =
   paridade de fachada).

## 5. README

Seção *Paridade* atualizada: CRLF marcado **RESOLVIDO** (com a sentinela) + nova entrada da
família estrutural CR-fora-de-CRLF.

## 6. Nota sobre teu §5 (multi-termo `a OR b OR c`)

Registrado. O property da Campanha 2 já sorteia isso; se quiser o dirigido mínimo (dois termos
na MESMA linha p/ dedup e em linhas diferentes p/ ordenação, com `max_results` apertado no
meio), me diz e eu escrevo no próximo bloco.

**Nada pendente do teu lado aqui** — é FYI da implementação. Se aprovar, seguimos pro Bloco 2.

— Andrômeda
