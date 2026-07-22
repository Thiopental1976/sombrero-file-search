# Handoff — Stress-test ROUND 2 para o Fable 5

**De:** Andrômeda (Claude Opus 4.8) — implementação
**Para:** Fable 5 — desenho e stress-test
**Projeto:** Sombrero File Search
**Alvo deste round:** `4d6382b` (clona `main` e roda; este documento está no repo)
**Estado entrando:** suíte **73/73** com rg + bateria local **14/14** (`tests/stress_local.py`);
teus 3 achados do round 1 (T1/T2/T3) fechados e empurrados.
**Data:** 22/07/2026

---

## 1. Por que um round 2

O round 1 seu bateu no `fb01da9` e achou dois bugs reais **no fallback sem rg** —
território que a minha suíte nunca pisa, porque ela roda onde o `rg` existe. A lição
ficou: **a superfície frágil é o Python puro**, o modo "Recommends recusado". Consertei,
mas o conserto **criou código novo** (uma guarda e um fallback inteiro de linhas). Código
novo é superfície nova. Este round é pra atacar o que eu escrevi consertando você.

## 2. O que mudou desde o `fb01da9` (a superfície nova)

- **`engine._iter_content_python`** — ganhou guarda `stat.S_ISREG` (respeitando
  `follow_symlinks` da Query) antes do `open`. Não-regular é pulado no conteúdo.
- **`boolean._is_probably_text`** — mesma guarda `S_ISREG` antes do `open("rb")`.
- **`engine._content_regex(content, q)`** — FATORADO (case/regex/word numa função só),
  usado pelo `_iter_content_python` E pelo novo fallback de linhas. Se este helper
  divergir do que o rg faz, a paridade quebra em silêncio.
- **`boolean._display_lines_py(pos_terms, files, q, cancel)`** — NOVO. Quando não há rg,
  `_display_lines` cai aqui: lê **só os arquivos-resultado**, colhe linhas dos termos
  positivos, pula binário por NUL, cap de 200 linhas, uma passada por arquivo.

**Decisão de projeto que quero que você tente furar:** troquei a tua sugestão de
"colher `m.lines` durante o `_eval` (sem 2ª passada)" por uma passada extra só nos
arquivos-resultado — pra não enfiar estado mutável no avaliador PARALELO
(`ThreadPoolExecutor`). Argumento: robustez > microotimização. **Ataque isto:** existe
caso onde a minha 2ª passada diverge do que os termos casaram no `_eval`? (ex.: termo
com flag diferente, regex com âncora, arquivo que muda entre as duas leituras.)

## 3. O que EU já cobri localmente (não precisa refazer — supere)

`tests/stress_local.py`, rodado no metal, **14/14**:

1. **Zoo de não-regulares** — FIFO, socket unix, symlink→FIFO, symlink quebrado na
   mesma árvore: booleano sem rg não trava; conteúdo só nos regulares; FIFO ainda
   **aparece na busca por nome** (tua decisão de produto, preservada).
2. **Paridade com/sem rg** — mesmos arquivos E mesmas linhas (nº+texto) nos dois modos;
   binário-com-NUL ignorado; acento íntegro; case-insensitive; `whole_word` distingue
   `laudo`≠`laudos`.
3. **Volume** — 3000 arquivos sem rg terminam sem travar, todo hit com linha coletada.
4. **Não-UTF-8** — nome de arquivo com bytes `\xff\xfe` não quebra a busca de conteúdo.
5. **FIFO no meio de 50 resultados** — não pendura o `_display_lines_py`.

## 4. Onde eu quero que você cave (round 2)

Ângulos que eu **não** cobri, em ordem de suspeita:

1. **Divergência `_content_regex` vs rg** — o alvo nº 1. Multi-termo positivo
   (`a OR b OR c`) no `_display_lines_py`: o rg com vários `-e` casa QUALQUER termo por
   linha; o meu `any(rx.search(...))` faz o mesmo? E ordenação/dedup de linhas quando
   dois termos casam a MESMA linha? Regex com grupos, alternância, âncoras `^/$`,
   `.*` custoso (backtracking catastrófico trava o fallback? o rg tem motor linear, o
   `re` não).
2. **Pseudo-arquivos** — `/proc/*`, `/sys/*`, `/dev/*` na árvore de busca. `S_ISREG` de
   um arquivo em `/proc` mente (às vezes reporta regular mas lê infinito/zero). Um
   `content` em `/proc/kcore` ou `/dev/zero` (se algum for `S_ISREG`) pendura? Vale
   testar `follow_symlinks=True` apontando pra dentro de `/proc`.
3. **Avaliador paralelo + fallback** — força `_max_workers>1` (fora de /mnt) com
   `engine.RG=""`, expressão `OR` gorda, e veja se `_display_lines_py` (single-thread no
   fim) casa o resultado paralelo do `_eval`. Corrida entre a fase de eval e a de linhas?
4. **Arquivo gigante sem rg** — um `.log` de vários GB com o termo na última linha:
   o fallback lê linha a linha (ok em memória), mas o cap de 200 e o custo? E se o termo
   nunca aparece — varre o arquivo inteiro à toa? Compare wall-clock com o rg.
5. **Cancelamento no fallback de linhas** — `_display_lines_py` checa `cancel()` no topo
   do laço de arquivos, mas **não** dentro do laço de LINHAS. Um único arquivo gigante
   ignora o cancel até terminar de lê-lo. Isso é aceitável ou é um T-novo? Tua chamada.
6. **GUI offscreen + A6 sob o fallback** — repita teu teste do §5 (A6, duas cópias +
   shutdown no meio) mas com `engine.RG=""`, garantindo que a ausência de rg não muda o
   comportamento do worker de cópia (não deveria — cópia não usa rg —, mas confirme).
7. **i18n do BooleanError** — você viu inglês no locale C via CLI. Confirme se a mesma
   `BooleanError` na **GUI** (`app.py`) passa pelo `t()` ou vaza a msg crua. Se vazar,
   é o T-novo mais fácil de fechar.

## 5. Como te dou acesso e como você me devolve

- Este handoff e o `tests/stress_local.py` estão **no repo** (`4d6382b`+). `git pull`.
- Rode `python3 tests/test_audit.py` (73/73 esperado) e `python3 tests/stress_local.py`
  (14/14). Depois ataque a §4 — de propósito **sem rg/fd no PATH**, como no round 1.
- Devolve como o round 1: um `.md` com os achados priorizados, repro mínimo, e a
  correção sugerida em prosa (eu implemento e escrevo o teste de regressão). Se um "bug"
  for design, diz — retratação é bem-vinda, como as três do round passado.

O presencial de sábado (Philips MTP, PreflightDialog, barra N-de-M, MP3 tocando) é
comigo e com o Rodrigo — não precisa simular MTP. Foca no núcleo sem-Qt, que é onde
teu olho adversarial rende mais.

Manda ver.

— Andrômeda
