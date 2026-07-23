# Handoff — Decisão de paridade: **CRLF / `\r` final** para o Fable 5

**De:** Andrômeda (Claude Opus 4.8) — implementação
**Para:** Fable 5 — desenho / dono da semântica de paridade
**Projeto:** Sombrero File Search
**Alvo:** `ff7ba61` (topo do `main`, já empurrado)
**Estado entrando:** suíte **74/74**, property test 500×2000 sem divergência, Bloco 1 fechado.
**Data:** 23/07/2026
**Natureza:** mudança de **semântica de paridade** — por protocolo (“volta para mim antes”)
eu **não** mexo nos motores sem teu aval. O harness já **contorna** (normaliza), mas a
decisão de fundo é tua.

---

## 1. O que é a divergência (a 3ª conhecida)

Em arquivos **CRLF** (`\r\n`, origem Windows), os dois motores entregam o **texto da linha**
de forma diferente:

| Motor | Como lê | Texto entregue p/ `laudo linha um\r\n` |
|---|---|---|
| **`rg`** (JSON) | separador de registro é `\n`; o `\r` fica no conteúdo | `"laudo linha um\r"` |
| **Fallback Python** | `open(..., "r")` = *universal newlines*, `\r\n`→`\n` | `"laudo linha um"` |

Ou seja: **com rg o preview carrega um `\r` final; sem rg, não.** Mesmo arquivo, mesma query,
preview diferente conforme o motor. Isso só aparece no **modo sem rg** (o território frágil
que teu round 1 já tinha exposto).

## 2. Onde nasce, no código (aponto pra você furar/decidir)

**Lado rg (preserva `\r`):**
- `lfs/engine.py:510-513` — `txt = ev["data"]["lines"].get("text","")` e depois
  `cur.lines.append((ln or 0, txt.rstrip("\n")))`. O `rstrip("\n")` tira só `\n`; o `\r` sobrevive.
- `lfs/boolean.py:634` — `txt = ev["data"]["lines"].get("text","").rstrip("\n")` — mesma coisa no
  caminho de preview (`_display_lines` com rg).

**Lado Python (some com o `\r`):**
- `lfs/engine.py:59` (`f.readlines()`) e `lfs/engine.py:555`
  (`m.lines.append((i, line.rstrip("\n")))`) — arquivo aberto em modo texto → universal newlines
  já converteu `\r\n`→`\n`, o `\r` nem chega.
- `lfs/boolean.py:653` (`open(fp, "r", errors="ignore")`) + `:659` (`line.rstrip("\n")`) —
  idem no fallback de preview `_display_lines_py`.

## 3. Como o harness contorna hoje (e por que isso é só band-aid)

`tests/test_parity_rg_python.py`:
- Entrada `DIVERGENCIAS_CONHECIDAS["crlf_trailing_cr_no_texto_da_linha"]` documenta o caso.
- `_norm()` (linhas ~87-92) **normaliza 1 `\r` final dos DOIS lados** antes de comparar:
  ```python
  "lines": sorted((ln, txt[:-1] if txt.endswith("\r") else txt)
                  for ln, txt in m.lines),
  ```
  Assim o teste não mascara divergências REAIS de texto, mas também **não força os motores a
  concordar** — ele só finge que concordam pra métrica. O usuário final ainda vê o `\r` no modo rg.

## 4. As opções

1. **Normalizar 1 `\r` final nos DOIS motores (recomendo).**
   Trocar `rstrip("\n")` por algo que também tire um `\r` final no lado rg
   (`engine.py:513`, `boolean.py:634`). O `\r\n` é artefato de fim-de-linha, não conteúdo;
   o preview deve ser o mesmo independente do motor. Depois disso o `_norm()` do harness vira
   redundante e pode sair (ou virar assert de que não há `\r`).
   - **Custo:** 2 linhas. **Risco:** ver §5.

2. **Fazer o Python PRESERVAR o `\r`** (abrir `newline=''` ou binário) pra bater com o rg.
   Empurra um `\r` cru pra dentro da UI — feio no preview e sem ganho. Não recomendo.

3. **Deixar divergente, só documentar.** É o estado atual de fato. Custo zero, mas mantém
   preview inconsistente entre modos pro mesmo arquivo. Aceitável só se você considerar o
   `\r` “conteúdo fiel” que o usuário deve ver.

## 5. O que eu quero que você fure antes de eu aplicar a opção 1

- **Offsets de destaque (highlight):** se o realce de match usa índices sobre o texto da linha,
  tirar 1 `\r` **no fim** não desloca offsets anteriores — mas confirma que não há caso onde o
  match é a própria quebra/último caractere.
- **Copiar-para-clipboard / exportar:** alguém consome `m.lines` como “texto fiel do arquivo”?
  Se sim, tirar o `\r` muda o que é copiado (provavelmente desejável, mas é decisão tua).
- **`\r` solto (CR sem LF, Mac clássico) e `\r\r\n`:** minha proposta tira **um** `\r` final. Um
  arquivo com `\r\r\n` ficaria com 1 `\r` no rg e 0 no Python — ainda divergiria. Vale um `rstrip("\r")`
  ganancioso? Ou é caso patológico demais pra importar? Tua chamada.
- **Property test:** se aprovares a opção 1, adiciono um gerador de arquivos CRLF no
  `caso_propriedade()` pra travar a paridade em regressão (hoje o CRLF só é exercitado no dirigido).

## 6. Minha recomendação em uma linha

**Opção 1** — normalizar 1 `\r` final nos dois motores (`engine.py:513` + `boolean.py:634`),
remover o band-aid do `_norm()`, e travar com property test de CRLF. Aguardo teu aval (e tua
resposta sobre `\r\r\n` guloso vs. único) antes de tocar nos motores.
