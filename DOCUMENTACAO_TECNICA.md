# Sombrero File Search — Documentação Técnica

> Documento de referência para **avaliação e depuração** do projeto. Descreve arquitetura,
> cada módulo, o fluxo de dados, o modelo de concorrência, a gramática da busca booleana,
> o modo documentos, o player de mídia, o sistema de temas e a matriz de dependências por distro.
>
> **Versão do documento:** 2026-09-22 (atualizada de 2026-07-14) · **Autor:** Rodrigo Toledo (com Andrômeda/Claude)
>
> **Mapa da atualização de 22/09/2026:** §1–§14 são o documento de julho, corrigidos
> onde ficaram errados (§1, §2, §3.2, §5, §10, §11). As fases posteriores estão em
> **§15–§18 (F9)**, **§19 (F10)**, **§20 (F11)**, **§21 (F12)**, **§22 (revisão de
> 21–22/09)** e **§23 (handoff × código, pendências)**. Onde um trecho antigo e um
> novo discordarem, vale o novo.
> **Licença:** GNU GPL v3 ou posterior (`SPDX-License-Identifier: GPL-3.0-or-later`)

---

## 1. Visão geral

**Sombrero File Search** é um buscador de arquivos **nativo para Linux**, sem índice obrigatório
(há `--index` opt-in via plocate, §16), com resultados **ao vivo**, no espírito do *Agent Ransack / FileLocator Pro* do Windows. Ele busca
por **nome** (glob/regex), por **conteúdo** (texto/regex), com **expressões booleanas**
(`(A OR B) AND C NOT D`) e **dentro de documentos** (PDF/docx/epub/odt/zip). Tem GUI em
**PySide6** e uma **CLI** equivalente que reaproveita o mesmo núcleo.

O motor de busca são binários externos maduros — **ripgrep** (`rg`) para conteúdo e **fd**
para nome — com **fallback em Python puro** quando eles não existem, garantindo execução em
qualquer distro. O modo documentos usa **ripgrep-all** (`rga`).

### 1.1 Por que existe

- Buscadores do Windows (FileLocator, Everything, UltraSearch) leem a MFT/USN do NTFS, que
  **não existe no Linux**; sob Wine só enxergam o prefixo. São inúteis aqui.
- Origem prática: o menu do Cinnamon estava lento porque um override do applet
  `menu@cinnamon.org` fazia busca de arquivos **síncrona** em `/home` e `/mnt` a cada tecla.
  A função foi reimplementada aqui de forma **assíncrona** (thread), sem travar a interface.

### 1.2 Princípios de projeto

1. **Núcleo sem Qt** (`engine.py`, `boolean.py`) — testável e reutilizável pela GUI e pela CLI.
2. **Motores externos, nunca reimplementados** — portáveis e mantidos por terceiros.
3. **Degradação graciosa** — sem `rg`/`fd`, cai para Python; sem `rga`, sem modo documentos;
   sem `QtMultimedia`, sem player (imagens ainda funcionam).
4. **Streaming** — resultados aparecem durante a busca; nunca bloquear a UI thread.
5. **"Buscar tudo" por padrão** — `--no-ignore` e ocultos togglável, como o Agent Ransack.
6. **Honestidade > completude** — o que ficou de fora é DITO, com motivo, num funil único
   (§20.3); "0 resultados" só quando é verdade.
7. **Lê e exporta, nunca altera** — cópia não destrutiva por construção (§17), duplicatas
   sem API de remoção (§19.6).
8. **CLI em inglês (contrato de automação), GUI no idioma do usuário**; alcance mundial —
   nomes e conteúdos em codificações legadas de qualquer região são achados (§22.2).

---

## 2. Estrutura de arquivos

```
sombrero-file-search/
├── lfs/                     # código (15 módulos; só app.py importa Qt)
├── tests/                   # scripts standalone + 2 matrizes de instalação em shell
├── packaging/               # build_deb.sh, build_appimage.sh
├── assets/                  # icon.svg, icon{,_48,_64,_128,_256}.png, demo.gif, social_preview.png…
├── docs/campo/              # evidência bruta de testes de campo (ex.: NAS TrueNAS, 22/09/2026)
├── install.sh               # instalador universal
├── README.md / README.pt-BR.md, MANUAL.md / MANUAL.pt-BR.md
├── DOCUMENTACAO_TECNICA.md (este), INSTALACAO_BAZZITE_DIFICULDADES.md, BRIEFING_COMPLETO_…md
├── HANDOFF_*.md, REVISAO_PEDIDO_*.md, VEREDITO_*.md   # histórico de revisões
├── VERSION ($Format:%h (%cs)$, preenchido pelo git archive), requirements.txt (PySide6>=6.5)
└── LICENSE (GPL-3.0-or-later), .gitattributes, .gitignore
```

O lançador não mora mais na raiz: o `install.sh` gera `sombrero-file-search` (GUI) e
`sfs` (CLI, alias `lfs`) em `~/.local/bin`.

### 2.1 `lfs/`

| Módulo | Papel |
|---|---|
| `engine.py` | Núcleo sem Qt: `Query`/`Match`, detecção rg/fd/rga (`_which`), iteradores fd/rg/Python, plano e gate de raízes (F12 `planejar_raizes`, F9a `_live_roots`), partição por disco (F11), snapshots + dedup (`_Entrega`/`_Colapso`), funil de incompletude, codificações legadas e NFC/NFD, classificação de montagens de usuário (`classifica_montagens`, `user_mounts`, `network_mounts`), `search()` |
| `boolean.py` | Busca booleana: `tokenize` → `parse` (AST `Term/Not/And/Or`) → conjuntos com `rg -l` (AND progressivo, OR paralelo com trava por disco, `_Phase`), `_display_lines`, `search_boolean()`; mesmo gate F9a/F12 |
| `disks.py` | Topologia de disco, só stdlib: montagem por caminho, `rotational`, `path_needs_serial`, `search_profile` → `IOProfile`, sonda `mount_status`/`mount_alive` em processo filho, `mounts_under`, `list_search_targets`, capacidades do destino (`dest_caps`), removível/LUKS/ejetar, velocidade do link |
| `cli.py` | CLI `sfs` (argparse, sempre em inglês): texto, NDJSON (`--json`), exit estilo grep, `--index`, `--nice-io` |
| `app.py` | GUI PySide6: `MainWindow`, abas (`SearchTab`), `SearchWorker`, `ResultModel`/`ResultFilterProxy`, preview texto/mídia, cópia (`CopyWorker`, `PreflightDialog`, `ConflictDialog`), `PropertiesDialog`, `DuplicatesPanel`/`DupWorker`, temas, menu "Discos ▾" (`preenche_menu_discos`) |
| `fileops.py` | Motor de cópia, **não destrutivo por construção**: `preflight`, `probe_write`, `decide_strategy`, `copy_to` (§17) |
| `copyjobs.py` | Fila de cópia persistente no `config.json` (sobrevive ao fechamento e ao `kill -9`) |
| `dupes.py` | Caçador de duplicatas (F10c): acha, mostra e exporta, **nunca apaga** (§19.6) |
| `searches.py` | Buscas salvas, histórico, exportação CSV/JSON (`celula_csv` anti-fórmula) |
| `resultfilter.py` | Filtro nos resultados: mini-linguagem compilada em predicado puro (`compile_filter`) |
| `indexed.py` | `--index` via plocate, opt-in, que **recusa** se houver poda (§16) |
| `humane.py` | `human_error()`: errno/exceção → frase humana traduzida (§18) |
| `i18n.py` | `t()`, `set_lang`, `current_lang`; inglês é a língua-fonte; override por `SFS_LANG` (`LFS_LANG` legado) |
| `xdg.py` | Integração freedesktop: mime, "Abrir com" (`apps_for`, `launch`), gerenciador de arquivos / `ShowItems` |
| `version.py` | Build instalado (`build_info`, `deb_version`, `title_suffix` no título da janela) |

### 2.2 `tests/`

Todos **standalone**: `python3 tests/<arquivo>.py` a partir da raiz (os que importam
`app.py` pedem o Python do venv, com PySide6). **Não use `pytest`.** Cada script sai ≠ 0
em falha; tudo roda em tempdir, sem tocar o acervo.

| Arquivo | Cobre |
|---|---|
| `test_audit.py` | Suíte principal: B1–B14, N1–N3, opt#1–#4, F7–F12 etc. (128 testes, runner próprio) |
| `test_cli_flags_2026_09_21.py` | `--max-size`, `--depth`, `--follow`; valores inválidos → exit 2; `--index --follow`; laço de symlink |
| `test_correcoes_2026_09_10.py` | Achados de 10/09 (reais e refutados), identidade preview × motor, lacuna do mesmo FS |
| `test_funil_incompleto.py` | `stats['incompleto']` como canal único de perda de completude |
| `test_honestidade.py` | Tabela motor × perda de completude (negação, raiz inválida, truncamento, cancelamento) |
| `test_legado_mundo_2026_09_22.py` | Conteúdo em codificação legada (14 idiomas/codificações), zero acerto falso, NFD, paridade |
| `test_leva_motor_2026_09_09.py` | Disco físico como conjunto de pratos (LVM/RAID/LUKS) |
| `test_montagens_opcao_b_2026_09_22.py` | Opção B, seção Rede, sonda com `statvfs`, raiz de rede sem `stat` |
| `test_motor_falhou.py` | Motor que sai com erro não vira "nada encontrado" |
| `test_nome_legado_2026_09_22.py` | Nome em codificação legada; 4+ globs sem perder nome não-UTF-8; NFD |
| `test_nome_nao_utf8_2026_09_21.py` | GUI: nome não-UTF-8 legível; Abrir/Copiar caminho chegam no arquivo certo |
| `test_paralelo_por_disco.py` | Partição por disco, streaming, encerramento; bind do ostree |
| `test_parity_rg_python.py` | Paridade rg/fd × fallback Python (lento, ~3 min) |
| `test_revisao_fable_2026_09_21.py` | Regressões da revisão do Fable (45 verificações) |
| `test_snapshots.py` / `test_snapshots_fallback.py` | Poda de snapshots nos três motores; "vivo primeiro" + dedup |
| `test_topologias.py` | Classificação de disco em topologias sintéticas |
| `soak_local.py`, `stress_local.py` | Soak de memória (GUI offscreen) e stress no metal — fora da suíte rápida |
| `dummy_nas.py` | Ferramenta: NAS falso em FUSE com latência/travamento controlados |
| `test_install_matrix.sh`, `test_install_matrix_containers.sh` | `install.sh` em imutáveis simulados e em contêineres (apt/dnf/pacman/zypper) |

### 2.3 Empacotamento e instalação

| Arquivo | Papel |
|---|---|
| `install.sh` | Sem root: rg/fd/rga/pandoc estáticos em espaço de usuário primeiro (gerenciador como alternativa; nunca `sudo` em ostree), PySide6 do sistema ou venv, copia `lfs/` + `assets/`, gera lançadores, ícones e `.desktop`; migra do nome antigo |
| `packaging/build_deb.sh` | `.deb` magro (`Depends: python3`, rg/fd como Recommends) |
| `packaging/build_appimage.sh` | AppImage autocontido (python-build-standalone + PySide6 + rg/fd estáticos) |

---

## 3. Núcleo — `lfs/engine.py`

Módulo sem dependência de Qt. Define os tipos de dados, detecta binários e implementa quatro
iteradores de busca (dois por nome, dois por conteúdo) mais a API pública `search()`.

### 3.1 Detecção de binários

```python
_APP_BIN = ~/.local/share/sombrero-file-search/bin   # binários empacotados (rga/pandoc)
_which(*names)   # shutil.which + fallback no _APP_BIN (os.access X_OK)
RG  = _which("rg")                    # ripgrep
FD  = _which("fd", "fdfind")          # fd (Debian/Mint renomeiam para fdfind!)
RGA = _which("rga", "ripgrep-all")    # ripgrep-all
engine_info() -> {"ripgrep":…, "fd":…, "rga":…}   # texto "(ausente …)" se faltar
```

O `_which` procura **primeiro no PATH** e depois no diretório de binários empacotados, para que
o instalador possa fornecer `rga`/`pandoc` estáticos sem root.

### 3.2 Tipos de dados

**`Query`** (dataclass) — todos os parâmetros da busca:

| Campo | Tipo | Significado |
|---|---|---|
| `paths` | `list[str]` | pastas onde buscar |
| `name_patterns` | `list[str]` | globs (lista) OU 1 regex |
| `name_is_regex` | `bool` | interpreta `name_patterns[0]` como regex |
| `content` | `str` | texto/regex a conter (vazio ⇒ busca só por nome) |
| `content_is_regex` | `bool` | conteúdo é regex (senão `--fixed-strings`) |
| `documents` | `bool` | busca dentro de documentos via `rga` (F4) |
| `case_sensitive` | `bool` | sensível a caixa (padrão insensível) |
| `whole_word` | `bool` | palavra inteira (`--word-regexp`) |
| `recursive` | `bool` | entra em subpastas |
| `max_depth` | `int?` | profundidade máxima |
| `include_hidden` | `bool` | inclui ocultos |
| `follow_symlinks` | `bool` | segue links |
| `respect_gitignore` | `bool` | `False` = busca tudo (`--no-ignore`) |
| `one_file_system` | `bool` | não cruza mounts (`--one-file-system`) |
| `min_size`/`max_size` | `int?` | bytes |
| `modified_after`/`modified_before` | `float?` | epoch |
| `max_results` | `int` | teto (default 100000) |
| `skip_snapshots` | `bool` | poda árvores de snapshot (F11, padrão `True`; §20.1) |
| `excluded_paths` | `tuple` | montagens mortas sob as raízes, que nenhum motor toca (F12b, §21.5) |
| `rg_threads` | `int?` | pool dentro do rg (booleano por grupo de disco, §20.2) |

**`Match`** (dataclass) — um resultado: `path`, `size`, `mtime`, `is_dir`, `lines:
list[(lineno, texto)]` (até 200; texto **lógico**, sem `\r\n` — contrato CRLF de 23/07),
`nmatch` (nº de casamentos), `ident` (`(st_dev, st_ino)` do lstat), `snapshot` (árvore de
origem, ou `None` = árvore viva) e `copies` (cópias idênticas absorvidas pelo dedup, §20.1).

### 3.3 Filtros comuns

- `_name_matcher(q)` → devolve `função(basename)->bool` (regex ou lista de globs;
  case-insensitive por padrão, à la Agent Ransack).
- `_passes_meta(q, st)` → aplica min/max size e modified_after/before sobre um `os.stat_result`.

### 3.4 Busca por NOME

- **`_iter_names_fd(q, cancel)`** — usa `fd`/`fdfind`. Um processo `fd` **por glob** (multi-glob),
  com `--absolute-path --type f`, flags de gitignore/hidden/symlink/one-fs/depth. Deduplica via
  `seen`. `stat` + `_passes_meta` por arquivo. Cancelamento via `proc.terminate()`.
- **`_iter_names_python(q)`** — fallback universal: `os.walk` com controle de profundidade,
  ocultos, symlinks e metadados. Poda `dns[:]` para não descer onde não deve.

### 3.5 Busca por CONTEÚDO

- **`_iter_content_rg(q, cancel)`** — o caminho principal. Monta `rg --json` (ou `rga --json`
  em modo documentos) e faz **parsing de eventos em streaming**:
  - `begin` → resolve o path, aplica filtro de nome-regex (o glob já vai como `--glob` no rg),
    `stat` + `_passes_meta`; guarda `cur = Match(...)`. **Em modo documentos**, se o path é
    interno a um container (ex.: `pacote.zip/interno.pdf`) e não tem `stat` no FS, emite
    `Match(path, 0, 0)` para **não perder o hit**.
  - `match` → acumula `nmatch += len(submatches)` e guarda até 200 linhas `(line_number, texto)`.
    `line_number` pode vir **`null`** (adaptadores de texto do rga) → tratado como `0`.
  - `end` → `yield cur`.
  - Em modo documentos **não** passa `--encoding auto` (o rga já entrega UTF-8).
  - Se o `Popen` falha (`OSError`), cai para o fallback Python.
- **`_iter_content_python(q, cancel)`** — varre nomes (via `_iter_names_python`) e faz "grep"
  em Python: lê linha a linha, aborta arquivo se achar `\x00` (binário), acumula linhas/nmatch.

### 3.6 API pública

```python
search(q, on_result, cancel=lambda:False, on_progress=lambda n:None) -> (total, segundos)
```

Escolhe o iterador: se há `content`, usa `rg` (ou `rga` p/ documentos) senão Python; se busca só
por nome, usa `fd` senão Python. Chama `on_result(Match)` em streaming, `on_progress(n)` a cada
25, respeita `cancel()` e `max_results`.

---

## 4. Busca booleana — `lfs/boolean.py` (recurso-assinatura, F3)

Implementa `(A OR B) AND C NOT D` resolvendo por **conjuntos de arquivos**.

### 4.1 Gramática e semântica

- **Termos**: palavra crua (até espaço/operador/parêntese) ou `"entre aspas"` (preserva espaços).
- **Operadores**: `AND OR NOT` (palavras, case-insensitive) e símbolos `& && | || !`.
- **Adjacência** = AND implícito (`foo bar` ≡ `foo AND bar`).
- **Precedência**: `NOT` (unário) > `AND` > `OR`. Parênteses agrupam.
- **NOT binário**: `A NOT B` ≡ `A AND (NOT B)`.

### 4.2 Pipeline

```
expr ──tokenize──▶ tokens ──_P.parse (descida recursiva)──▶ AST
AST ──_eval (conjuntos)──▶ arquivos-resultado
arquivos + termos positivos ──_display_lines (rg --json)──▶ linhas p/ preview
```

**AST**: `Term(text)`, `Not(node)`, `And(a,b)`, `Or(a,b)`. Erros ⇒ `BooleanError(ValueError)`.

**Parser** (`_P`), gramática de descida recursiva:
```
parse_or   := parse_and ( OR parse_and )*
parse_and  := parse_not ( (AND parse_not) | (NOT parse_not→Not) | (TERM|'(' →adjacência) )*
parse_not  := NOT parse_not | parse_atom
parse_atom := '(' parse_or ')' | TERM
```

### 4.3 Avaliação por conjuntos

- **`_files_with_term(term, q, cancel)`** → `set` de arquivos que contêm o termo, via `rg -l`
  (rápido); fallback `_files_with_term_py` (reusa `_iter_content_python`).
- **`_universe(q, cancel)`** → todos os candidatos, via `rg --files` (ou `_iter_names_python`).
  **Só é calculado se houver um `NOT`** (lazy, via `universe_box`).
- **`_eval`**: `And` = interseção `&`, `Or` = união `|`, `Not` = `universo − conjunto`.
  Cache por termo evita reconsultar o mesmo texto.
- **`_display_lines(pos_terms, files, q, cancel)`** — passada final: roda um único `rg --json`
  com todos os termos **positivos** (`positive_terms`, que ignora os negados) apenas sobre os
  arquivos-resultado, para preencher `Match.lines` do preview.

`search_boolean(q, expr, on_result, cancel, on_progress) -> (total, segundos)` orquestra tudo,
aplicando `_passes_meta` no fim (tamanho/data) e respeitando `max_results`/`cancel`.

---

## 5. CLI — `lfs/cli.py`

Comando **`sfs`** (alias `lfs`). Saída **sempre em inglês** (`i18n.set_lang("en")`: o
`detail` do `--json` é contrato de automação). 1ª linha do stderr:
`# engine: rg=… fd=… rga=…`.

| Flag | Efeito (→ campo da `Query`) |
|---|---|
| `path…` (1+) | pastas → `paths` |
| `-V`, `--version` | versão + aviso GPL, sai |
| `-n`, `--name TEXT` | nome **contém** o termo (`as_name_glob`); globs `* ? [` como digitados; vários por `,` ou `;` → `name_patterns` |
| `--name-regex` / `--content-regex` | tratar como regex |
| `-c`, `--content TEXT` | texto/regex a conter → `content` |
| `-b`, `--bool EXPR` | busca booleana |
| `-D`, `--docs` | dentro de documentos via `rga` (sem rga: `# warning` e cai no rg) |
| `-i`, `--ignore-case` | aceito, **sem efeito** (o padrão já é insensível — §23.2) |
| `-s`, `--case-sensitive` | → `case_sensitive` |
| `-w`, `--word` | palavra inteira → `whole_word` |
| `--hidden`, `--gitignore` | ocultos / respeitar `.gitignore` |
| `--one-fs` | não cruza montagens (e desliga a expansão F12) |
| `--snapshots` | sempre busca também nas árvores de snapshot → `skip_snapshots=False` |
| `--min-size SIZE`, `--max-size SIZE` | tamanho (`500K`, `10M`, `1.5G`); inválido ou mínimo > máximo → exit 2 |
| `--depth N` | profundidade máxima (1 = só a pasta dada); N < 1 → exit 2 |
| `--follow` | segue symlinks (laço é cortado, sem alarme) |
| `--days N` | modificado nos últimos N dias → `modified_after` |
| `-0`, `--print0` / `-l`, `--files-only` | separador NUL / só caminhos |
| `--json` | NDJSON: `{path,size,mtime,is_dir,nmatch,lines,snapshot,copies}`, `{copy,of,snapshot}` e `warn`/`error` (`mount_dead`, `denied`, `incomplete`, `index_used`, `index_coverage`, `boolean_expression`) |
| `--nice-io` | `nice 19` + `ionice -c 3` (os filhos herdam) |
| `--index` | nome via plocate; recusa (exit 2) com `-c`/`-b`, `--follow`, sem índice ou com cobertura podada |

**Saída.** Bytes do nome crus (`os.fsencode`, seguro para não-UTF-8); `--json` com
`surrogatepass`. **Exit codes:** 0 achou; 1 nada; 2 erro de uso ou perda **grave**
(`resumo_incompleto`, §20.3); 130 Ctrl-C. **Pipe fechado** (`| head`) cancela a busca,
sem traceback. **Avisos no stderr:** `# warning: mount not responding`,
`# warning: N directories without permission`, `# note: N kernel filesystem(s) not searched`,
`# incomplete: …` e a linha final `# N files · Xs`.

Exemplos:
```bash
sfs ~/projetos -n '*.py' -c "def main"
sfs ~/docs -c laudo --docs
sfs ~/notas -b '(nota OR laudo) AND paciente NOT rascunho'
sfs /dados -c erro -l --print0 | xargs -0 du -h
sfs /var/mnt/Toledo -n '*' --depth 2 --max-size 1M --json
```

---

## 6. GUI — `lfs/app.py` (PySide6)

### 6.1 Estrutura

- **`SearchWorker(QThread)`** — roda a busca fora da UI thread. Sinais: `batch(list[Match])`,
  `progress(int)`, `done(int, float)`, `error(str)`. Faz **throttle** dos resultados: emite
  lote a cada 100 ms **ou** a cada 200 itens (`_flush`). Ramo booleano vs. engine; `BooleanError`
  vira `error.emit` sem quebrar a thread. Cancelamento por flag `_cancel`.
- **`ResultModel(QAbstractTableModel)`** — colunas Arquivo/Pasta/Matches/Tamanho/Modificado.
  `append(matches)` usa `beginInsertRows` (crescimento incremental). Papéis: Display, alinhamento
  à direita (nº/tamanho), ToolTip (caminho completo), UserRole (o `Match`).
- **`MainWindow(QMainWindow)`** — monta a UI em `_build()`:
  - **Header** (`QFrame#header`): logo (icon_64), título/subtítulo, **badges de motor** (bolinha
    verde/cinza por rg/fd/rga) e o **botão de tema**.
  - **Barra de busca**: campo de conteúdo (grande) + `Buscar`/`Cancelar`.
  - **Nome + pasta**: glob de nome, pasta(s) separadas por `;`, botão `Procurar…`.
  - **Chips de opção** (`QCheckBox` estilizados como pílulas): Aa, palavra, booleano, documentos,
    regex conteúdo, regex nome, subpastas, ocultos, .gitignore, 1 disco, `Tam ≥`, `Últimos N d`.
  - **Splitter vertical**: tabela de resultados em cima, **preview** embaixo.
  - **Status bar** (QLabel).

### 6.2 Concorrência (fluxo)

```
start_search → _build_query → SearchWorker(q, boolexpr).start()
   worker.batch    → ResultModel.append   (tabela cresce ao vivo)
   worker.progress → status "N encontrados · Xs"
   worker.error    → status "expressão inválida: …"
   worker.done     → status "✔ N resultados · Xs"
Esc → cancela busca / limpa filtro ; Ctrl+L foca pastas ; Ctrl+F foca filtro ;
F3/Shift+F3 navegam matches no preview ; ↑/↓ histórico ; Ctrl+R repete ; Ctrl+T tema
```

A UI thread nunca faz I/O de busca. O `_cancel` é lido pelo iterador entre itens; processos
externos recebem `terminate()`.

### 6.3 Sistema de temas

- `THEMES = {"dark": {...}, "light": {...}}` — paletas com ~15 chaves (bg0..bg3, alt, border,
  txt, muted, accent, on_accent, green/amber/red…).
- `_STYLE_TMPL` — folha de estilo Qt com placeholders `{chave}`; `build_style(pal)` faz
  `.format(**pal)`.
- `apply_theme(name)` aplica o stylesheet, ajusta status e botão, e chama `_refresh_badges`.
- `toggle_theme()` inverte e **persiste** em `~/.config/sombrero-file-search/config.json`
  (`load_cfg`/`save_cfg`). Preferência é lida no `__init__`.
- **Nota de depuração:** os badges são reconstruídos em `_refresh_badges`; ao limpar o layout,
  usa-se `w.setParent(None)` **antes** de `deleteLater()` (senão, num `grab()` headless, os
  widgets antigos ainda aparecem sobrepostos ao novo conjunto).

### 6.4 Preview texto ↔ mídia (com player)

`_build_preview()` devolve um **`QStackedWidget`** com duas páginas:

- **Página 0 — texto** (`QPlainTextEdit` monospaçado): mostra as linhas casadas (`Match.lines`,
  com nº de linha) ou, se não houver, um "peek" das primeiras 80 linhas do arquivo (aborta em
  binário).
- **Página 1 — mídia**: um `QFrame#mediastage` com um `QStackedWidget` interno de 3 telas
  (imagem `QLabel` / áudio `♪` / vídeo `QVideoWidget`) + uma **barra de transporte**
  (`QFrame#mediabar`): `⏮` `▶/⏸` `⏭`, nome do arquivo, **slider de posição** e tempo `m:ss / m:ss`.

Detecção por extensão em `media_kind(path)` → `"image" | "video" | "audio" | None`
(`_IMG_EXT`, `_VID_EXT`, `_AUD_EXT`). Roteamento em `on_select`:

- **imagem** (sempre, é só `QtGui`): `QPixmap` escalado com `KeepAspectRatio`; reescala em
  `resizeEvent`; transporte desabilitado (rótulo "imagem").
- **vídeo/áudio** (só se `HAS_MEDIA`): `QMediaPlayer` + `QAudioOutput` (+ `QVideoWidget` p/ vídeo),
  `setSource` + `play()`. Sinais: `playbackStateChanged` (ícone ▶/⏸), `positionChanged`
  (slider+tempo, respeitando scrub), `durationChanged` (range), `mediaStatusChanged` (auto-avança
  no `EndOfMedia`).
- **prev/next** (`_nav_media(±1)`): navega entre as **linhas de mídia** dos resultados
  (`_media_rows()`), com **wrap**; `selectRow` dispara `on_select`.

**Portabilidade**: se `from PySide6.QtMultimedia import …` falhar, `HAS_MEDIA=False` — imagens
continuam funcionando e áudio/vídeo caem no preview de texto.

### 6.5 Ações de contexto

Menu de contexto e duplo-clique: **abrir arquivo**, **abrir pasta** (`QDesktopServices`),
**copiar caminho(s)** (clipboard). Multi-seleção suportada (até 10 no "abrir").

---

## 7. Modo documentos (F4) — ripgrep-all

`rga` expõe a **mesma CLI do rg** e, para PDF/docx/epub/odt/zip/tar, **extrai o texto** e
repassa em `--json` idêntico. Por isso o `engine._iter_content_rg` só troca o binário
(`rg`→`rga`) e o resto do parsing é reaproveitado. Adaptadores:

| Formato | Adaptador |
|---|---|
| PDF | poppler (`pdftotext`) |
| docx, epub, odt, html, ipynb | **pandoc** |
| zip, tar, gz | embutido no rga |

`line_number` pode vir `null` (adaptadores de texto) → tratado como 0. Caminho interno a
container não tem `stat` → `Match(path, 0, 0)` para não perder o hit.

---

## 8. Dependências e matriz por distro

| Dependência | Papel | Obrigatória? |
|---|---|---|
| Python ≥ 3.9 | runtime | sim |
| **PySide6** | GUI (traz QtMultimedia p/ o player) | sim (p/ GUI) |
| **ripgrep** (`rg`) | busca de conteúdo | recomendada (senão fallback Python) |
| **fd** (`fd`/`fdfind`) | busca por nome | recomendada (senão fallback Python) |
| **ripgrep-all** (`rga`) | modo documentos | opcional |
| **pandoc** | docx/epub/odt no rga | opcional |
| **poppler** (`pdftotext`) | texto de PDF no rga | opcional |

**Nome do pacote por gerenciador:**

| Lógico | apt (Debian/Ubuntu/Mint) | dnf (Fedora/RHEL) | pacman (Arch) | zypper (openSUSE) |
|---|---|---|---|---|
| ripgrep | `ripgrep` | `ripgrep` | `ripgrep` | `ripgrep` |
| fd | `fd-find` (bin `fdfind`) | `fd-find` | `fd` | `fd` |
| poppler | `poppler-utils` | `poppler-utils` | `poppler` | `poppler-tools` |
| ripgrep-all | `ripgrep-all`¹ | `ripgrep-all`¹ | `ripgrep-all` (AUR) | `ripgrep-all`¹ |
| pandoc | `pandoc` | `pandoc` | `pandoc` | `pandoc` |
| PySide6 | `python3-pyside6`² | `python3-pyside6`² | `pyside6` | `python3-PySide6` |

¹ Nem todo repositório traz `ripgrep-all`; o instalador então baixa o **binário estático** (musl,
x86_64) do GitHub. ² Se o PySide6 do sistema faltar, o instalador cria um **venv** e roda
`pip install PySide6`.

---

## 9. Instalação

### 9.1 Instalador universal (recomendado)

```bash
./install.sh
```

Fluxo (5 passos): detecta o gerenciador; **lista todas as dependências e pede confirmação**;
instala pacotes de sistema (com `sudo`, só se autorizado); baixa `rga`+`pandoc` estáticos se
faltarem; prepara PySide6 (sistema ou venv em `$PREFIX/venv`); copia o app para
`~/.local/share/sombrero-file-search/`, cria lançadores `sombrero-file-search` (GUI) e `lfs` (CLI),
ícones hicolor e atalho `.desktop`. Não precisa de root para o app (tudo em `~/.local`).

### 9.2 Manual

```bash
sudo apt install ripgrep fd-find poppler-utils   # exemplo Debian
pip install PySide6
python3 lfs/app.py     # GUI    |    python3 lfs/cli.py --help    # CLI
```

---

## 10. Testes e depuração

- **Suíte:** 17 scripts standalone em `tests/` (lista e cobertura no §2.2). Rode cada um com
  o Python do venv (`~/.local/share/sombrero-file-search/venv/bin/python tests/<arquivo>.py`)
  — **não** com `pytest` (vários fazem `sys.exit()` e o pytest dá INTERNALERROR). Os que
  importam `app.py` precisam de PySide6. `test_parity_rg_python.py` é o lento (~3 min).
- **Evidência de campo** (NAS real, `--json` + log do kernel): `docs/campo/`.
- **Auto-teste de módulo**: `python3 lfs/engine.py <pasta> <termo>` e
  `python3 lfs/boolean.py <pasta> '<expr>'` imprimem AST/resultados.
- **GUI headless** (sem display): `QT_QPA_PLATFORM=offscreen` + `MainWindow().grab().save(png)`
  para capturar telas; popular `model.append([...])` com `Match` fabricados evita depender de I/O.
- **Casos-limite booleanos já validados**: NOT líder, aspas, símbolos `| & !`, erro de sintaxe.
- **Player validado headless**: roteamento imagem/vídeo/áudio, habilitação do transporte,
  navegação prev/next com wrap, volta ao preview de texto.
- **Pegadinhas conhecidas**:
  - `fd` vira `fdfind` no Debian/Mint — resolvido em `_which`.
  - `rg` do Claude Code é **função de shell**, não binário — `shutil.which` não o vê; instale o
    `ripgrep` de verdade.
  - `line_number` `null` no rga; caminho interno a container sem `stat`.
  - badges: `setParent(None)` antes de `deleteLater()` (ver §6.3).

---

## 11. Limitações e backlog

- **F5 (abas, buscas salvas, histórico, export) e F6 (`.deb`, AppImage) estão implementados**
  (§19.4, §2.3) — saíram do backlog. Flatpak segue descartado (a sandbox brigaria com ler o
  filesystem inteiro; justificativa em `packaging/build_appimage.sh`).
- `rga` pré-compilado só para `x86_64`; em outras arquiteturas, instalar pelo gerenciador.
- Realce de preview e destaque só valem para termos **literais**; regex de conteúdo não é realçado.
- Ordenação por coluna é habilitada ao fim da busca (durante a busca, ordem de chegada).
- Regex de conteúdo do usuário não ganha variantes de codificação legada nem NFD (§22.2).
- Pendências pequenas levantadas em 22/09: §23.2.

---

## 12. Referência rápida de símbolos

| Módulo | Símbolos-chave |
|---|---|
| `engine.py` | `Query`, `Match`, `search`, `engine_info`, `_which`, `_iter_content_rg`, `_iter_names_fd`, `_iter_content_python`, `_iter_names_python`, `_passes_meta`, `_name_matcher`, `_glob_to_regex`, `_merge_globs`, `_reap`, `_walk_onerror` |
| `boolean.py` | `parse`, `tokenize`, `search_boolean`, `positive_terms`, `_eval`, `_files_with_term`, `_universe`, `_display_lines`, `_term_set`, `_or_operands`, `_max_workers`, `_under_mount`, `_Phase`, `_all_terms`, `_reap_stats`, `_merge_denied`, `BooleanError`, `Term/Not/And/Or` |
| `cli.py` | `main` (argparse) |
| `app.py` | `MainWindow`, `SearchWorker`, `ResultModel`, `THEMES`, `build_style`, `media_kind`, `_build_preview`, `_show_media`, `_nav_media`, `apply_theme` |

---

## 13. Auditoria Fable 5 — consertos aplicados

Auditoria de debug (`LinuxFileSearch_Auditoria_Debug.md`, 14/07/2026) achou 14
bugs provados/por-revisão + otimizações. Todos os consertos abaixo estão
implementados e cobertos por `tests/test_audit.py` (o que não é GUI) e por smoke
headless (GUI).

| # | Problema | Conserto | Onde |
|---|---|---|---|
| **B1** | rg/fd órfão ao cortar/abandonar a busca (varre `/mnt` em background) | `try/finally` + `engine._reap()` (terminate→wait→kill, idempotente) | `engine._iter_content_rg`/`_iter_names_fd`; `boolean._files_with_term`/`_universe`/`_display_lines` |
| **B2** | glob de nome caixa-sensível no rg (contrato é insensível) | `--glob-case-insensitive` quando `not case_sensitive` | `engine._iter_content_rg`, `boolean._rg_base` |
| **B3** | booleano ignorava filtro de nome REGEX | pós-filtro `re.search` no basename | `boolean.search_boolean` |
| **B4** | perda silenciosa de linhas por ARG_MAX (60k caminhos → `{}`) | lotes de ~400 caminhos por invocação do rg, mesclando dicts | `boolean._display_lines` (`_BATCH`) |
| **B5** | crash ao fechar a janela com busca viva (`QThread destroyed`) | `closeEvent`: `cancel()` → `wait(3000)` → `_stop_media()` | `app.MainWindow.closeEvent` |
| **B6** | booleano + documentos não combinam (ilusão de buscar em PDF) | ~~exclusão mútua na GUI~~ **revogado**: o booleano hoje busca dentro de documentos via rga (termos, universo do NOT e linhas) — ver comentário em `app._on_bool_toggled` | `app._on_bool_toggled` |
| **B7** | preview sem destaque do termo (recurso-assinatura) | `QTextEdit.ExtraSelection` âmbar sobre termos positivos literais | `app._apply_highlight` |
| **B8** | sem heartbeat/contadores (busca longa parece travada) | `QTimer` 0,5 s + contagem de "inacessíveis" via `stderr` (`stats["denied"]`) | `app._heartbeat`; `engine._reap(..., stats)` |
| **B9** | `one_file_system` ignorado no fallback Python (cruza mounts) | compara `st_dev` do root e poda `dns` | `engine._iter_names_python` |
| **B10** | higiene de argv no fd (falta `--`) | `--` antes do padrão e dos paths | `engine._iter_names_fd` |
| **B11** | nova busca não parava a mídia | `_stop_media()` + preview p/ página 0 | `app.start_search` |
| **B12** | imagem gigante decodificada síncrona congela a UI | `QImageReader.setScaledSize` (decodifica já reduzido) + teto 64 MB | `app._load_image` |
| **B13** | autoplay de vídeo COM ÁUDIO ao selecionar (constrangimento) | começa **mudo** por padrão; botão 🔇/🔊 persistido no config | `app._toggle_mute`, `cfg["muted"]` |
| **B14** | colunas sem ordenação | `QSortFilterProxyModel` + `SORT_ROLE` numérico, ligado ao fim da busca | `app.ResultModel.SORT_ROLE`, `app.proxy` |

**Otimização §5 aplicada**: `parse_size` unificado em `engine.parse_size`
(era duplicado em `app.py` e `cli.py`); `seen` do fd só quando há múltiplos
padrões.

### 13.1 Verificação v2 (`LinuxFileSearch_v2_Verificacao.md`)

A re-auditoria por execução confirmou as 14 correções e achou dois pontos reais,
já corrigidos:

| # | Problema | Conserto | Onde |
|---|---|---|---|
| **N1** | fd usa *smart-case*: com "Aa" LIGADO, padrão minúsculo ainda casava `N1.TXT` (rg era sensível → os motores divergiam de novo) | força `--case-sensitive` quando `case_sensitive` | `engine._iter_names_fd` |
| **N2** | contador de inacessíveis ausente no modo booleano (`stderr=DEVNULL`) e no fallback Python (`os.walk` engolia erros) | captura stderr + `_reap_stats` thread-safe; `os.walk(onerror=…)` e `PermissionError` de arquivo | §13.6 |
| **N3** | teto de imagem só valia quando as dimensões não vinham do cabeçalho; PNG/TIFF grande com header decodificava o raster inteiro na UI | teto de 64 MB **incondicional** → placeholder "abrir externo" | `app._load_image` |

Pendência restante (não urgente): N4 (miudezas de revisão) — ver §11.

### 13.2 Otimização #1 — AND com restrição progressiva (implementada)

A maior otimização da §3 da auditoria. Antes, cada termo de um `AND` varria a
**árvore inteira** com `rg -l`; agora o resultado parcial do lado esquerdo vira o
`restrict` do lado direito, que passa a varrer **só aqueles arquivos** (em lotes de
`_BATCH`, reusando o mecanismo do B4). O termo mais à esquerda é a única varredura
cheia; os seguintes leem apenas o conjunto acumulado.

- **Onde**: `boolean._eval` (propaga `restrict` por AND/OR/NOT), `boolean._term_set`
  (cache do conjunto cheio × varredura restrita), `boolean._files_with_term(..., restrict=)`.
- **Correção**: preservada porque a interseção distribui — `(X∘Y)∩R = (X∩R)∘(Y∩R)` —
  e um `AND` com lado esquerdo vazio faz **curto-circuito** (não varre o direito).
  O cache guarda só conjuntos CHEIOS; resultados restritos nunca o poluem.
- **Ganho**: em `raro AND comum` numa árvore grande, a 2ª varredura cai de
  *toda a árvore* para *só os arquivos de `raro`* — de minutos para milissegundos,
  e **muito menos I/O de disco** (crucial nos SMR — ver §14).
- **Testes**: `test_and_progressive_correctness` (mesmos resultados em AND/OR/NOT) e
  `test_and_progressive_restricts` (prova que a 2ª parte varreu 1 arquivo, não 51).

### 13.3 Otimização #2 — termos independentes em paralelo, com trava SMR (implementada)

Os operandos de um `OR` são varreduras **independentes** (nenhum depende do outro),
então rodam em paralelo num `ThreadPoolExecutor` — mas **só quando o disco aguenta**.

- **Onde**: `boolean._eval` ganhou o parâmetro `pool`; o ramo `Or` achata a cadeia
  (`_or_operands`) e faz `pool.submit` de cada operando. `search_boolean` cria o pool
  só quando `_max_workers(q) > 1`.
- **Trava SMR** (`_max_workers` + `_path_needs_serial`): se **qualquer** path da busca
  estiver sob `/mnt`, `/media` ou `/run/media` **sobre um disco rotacional ou
  desconhecido**, retorna **1 worker** (serial) — as cabeças do mesmo disco brigariam
  por *seek*. Fora dali (`~`, `/tmp`, SSD), usa `_WORKERS` (3 por padrão, afinável por
  `LFS_WORKERS`). O casamento é por **componente inteiro** de caminho, então `/mntx` não
  conta como `/mnt`.
- **Refinamento v3 — `rotational`** (parecer final Fable 5): serializar TODO `/mnt`
  penalizava um SSD/NVMe montado ali sem necessidade. Agora `_path_needs_serial` resolve
  o path → nó de dispositivo (mount de prefixo mais longo em `/proc/mounts`, via
  `_dev_for_path`) → disco inteiro → lê `/sys/block/<disco>/queue/rotational` (`_rotational`,
  sobe da partição p/ o disco). **`0` (SSD) libera o paralelismo mesmo sob `/mnt`**; `1`
  (rotacional) ou desconhecido (`None`) **serializa** — padrão seguro, pois SMR
  *drive-managed* (os Seagate USB) se reportam como disco comum e não há detecção honesta
  de SMR pelo sysfs. Validado nos discos reais: `/mnt/optane`, `/mnt/SSD128Gb` (rot=0) →
  paralelo; `/mnt/HDInternoBaixo`, `/mnt/DiscoQ` (rot=1) → serial.
- **Sem deadlock de pool aninhado**: as subtarefas submetidas recebem `pool=None`, então
  só o nível de `OR` alcançado pela thread principal paraleliza; um `OR` aninhado dentro
  de outro não tenta pegar mais workers (o que poderia travar o pool com todos os
  workers esperando por workers).
- **Thread-safe**: cache e universo são protegidos por `_cache_lock`; o I/O pesado
  (`_files_with_term`/`_universe`) roda **fora** do lock e a escrita usa `setdefault`
  (no pior caso de corrida, recalcula idêntico — idempotente).
- **Correção preservada**: cada `_files_with_term` paralelo ainda dá `_reap` no seu
  processo (B1), e a opt#1 (restrição do AND) segue intacta — o pool só distribui os
  irmãos de `OR`.
- **Testes**: `test_mnt_serializes` (mocka sysfs: rotacional/desconhecido em
  `/mnt|/media|/run/media` serializa, **SSD sob `/mnt` paraleliza**, `/mntx` não conta,
  misto com rotacional arrasta tudo p/ serial mas misto só-SSD não) e
  `test_or_parallel_correctness` (OR paralelo == OR serial, inclusive OR dentro de AND/NOT).

### 13.4 Otimização #3 — fd multi-glob → uma regex alternada (implementada)

No modo **só-nome**, o `fd` era chamado **uma vez por glob** (loop em `name_patterns`),
com dedup por `seen`. Com N globs, isso varria a árvore **N vezes** — N× o I/O, ruim
inclusive no SMR. Agora, quando há **>3 globs** (`_MERGE_GLOBS_MIN = 4`), eles são
fundidos numa **única regex alternada** e roda **um só `fd`**.

- **Onde**: `engine._glob_to_regex` (glob de basename → regex ancorada `^…$`,
  equivalente ao `fnmatch`: `*`→`.*`, `?`→`.`, classes `[...]` com `!`→`^`),
  `engine._merge_globs` (junta com `(?:a|b|…)`) e `engine._iter_names_fd` (decide
  fundir e troca `--glob` por regex).
- **Correção**: a regex é ancorada nos dois lados, então casa o **basename inteiro**
  como o glob. `test_glob_to_regex` compara caso a caso com `fnmatch.fnmatchcase`.
- **Guardas de segurança**: só funde globs **de basename** (sem `/` — glob de caminho
  fica no modo multi-fd, onde o `fd` casa a path toda); e a regex fundida é
  **validada com `re.compile`** antes — se falhar, cai no caminho antigo (um fd por
  glob). Nunca degrada silenciosamente para "nada encontrado".
- **`rg` não precisava**: no modo nome+conteúdo, o `rg` já recebe todos os `--glob`
  num **único processo** (uma passada); o problema das N varreduras era só do `fd`.
- **Ganho**: buscar `*.jpg *.png *.gif *.webp *.heic` num acervo passa de **5
  varreduras** para **1** — 5× menos I/O de diretório (ver §14).
- **Testes**: `test_glob_to_regex` (equivalência a fnmatch + recusa de glob com `/`) e
  `test_fd_merge_single_pass` (5 globs → **1 só** processo `fd`, união correta).

### 13.5 Otimização #4 — callback `on_phase` no booleano (implementada)

Uma busca booleana pesada (`(nota OR laudo) AND paciente NOT rascunho`) faz várias
varreduras `rg -l` — antes, a UI só dizia "Buscando…". Agora
`search_boolean(..., on_phase=cb)` relata a etapa: **"passo 2/4: termo 'paciente'"**
e, no fim, **"passo 4/4: extraindo linhas"**.

- **Onde**: `boolean._Phase` (contador de passos **thread-safe**), `boolean._all_terms`
  (conta os termos distintos do AST, positivos e negados), `_eval`/`_term_set`/
  `_universe_cached` recebem o `phase` e anunciam **só quando vão varrer o disco**
  (cache hit é instantâneo, não vira passo). Na GUI: sinal `SearchWorker.phase` →
  `MainWindow.on_phase` → texto no status (mostrado pelo heartbeat B8).
- **Total de passos**: termos distintos + 1 (a extração de linhas dos positivos).
  Cada termo é anunciado **uma vez** (dedup por nome), mesmo que a opt#1 o varra
  restrito depois.
- **Compatível com opt#2**: o contador é serializado por um `Lock` próprio, então a
  numeração sai coerente mesmo com os `OR` avaliados em paralelo (o I/O é que corre
  concorrente, não a contagem).
- **Retrocompatível**: `on_phase` é opcional (default `None`); a CLI, que chama
  `search_boolean(q, expr, out)`, continua igual.
- **Testes**: `test_on_phase_reports` (passos 1..total, total correto, último passo é
  "extraindo linhas", cada termo uma vez) e `test_on_phase_optional` (sem o callback,
  a busca funciona igual).

### 13.6 N2 — contagem de inacessíveis no modo booleano e nos fallbacks (implementado)

O contador de "N inacessível(is)" (B8) só funcionava na busca simples: o modo
**booleano** passava `stderr=DEVNULL` e o fallback Python engolia os erros do
`os.walk`. Agora o `stats['denied']` é preenchido em todos os caminhos.

- **Modo booleano**: `_files_with_term`, `_universe` e `_display_lines` passaram a
  **capturar o stderr** (tempfile) e contar via `_reap_stats`. `search_boolean` ganhou
  o parâmetro `stats` e o propaga por `_eval`/`_term_set`/`_universe_cached`. A GUI já
  passa `SearchWorker.stats`.
- **Thread-safe (opt#2)**: `_reap_stats` conta num dict **local** por processo e mescla
  no `stats` compartilhado sob `_cache_lock` (`_merge_denied`) — sem corrida mesmo com
  `OR` em paralelo. Os fallbacks Python usam o mesmo padrão (local → merge sob lock).
- **Fallback Python**: `engine._iter_names_python` agora passa `onerror=_walk_onerror(stats)`
  ao `os.walk` (conta `PermissionError` de diretório), e `_iter_content_python` conta
  também o `PermissionError` ao abrir arquivo. `engine.search` repassa `stats` a esses
  fallbacks (antes só o caminho `rg`/`fd` recebia).
- **Retrocompatível**: `stats` é opcional (default `None`); quem não passa (CLI) não conta.
- **Testes**: `test_walk_onerror_counts_denied` (diretório `chmod 000` no fallback conta
  ≥1) e `test_boolean_stats_denied` (booleano sobre a mesma árvore preenche `denied`,
  antes ficava 0). Ambos pulados como root (que ignora permissões).

---

## 14. Cuidado com discos SMR (e a diferença para CMR)

O Sombrero File Search é feito para rodar sobre acervos grandes espalhados em muitos
HDs — inclusive discos **SMR** e USB externos. Isso guia várias decisões do motor.

### 14.1 O que são SMR e CMR

- **CMR** (*Conventional Magnetic Recording*, também PMR): as trilhas **não se
  sobrepõem**. Cada setor pode ser reescrito no lugar. Escrita aleatória é
  previsível e rápida. É o disco "normal".
- **SMR** (*Shingled Magnetic Recording*): as trilhas são gravadas **sobrepostas
  como telhas** (daí *shingled*), o que aumenta a densidade/capacidade por um preço:
  reescrever um setor obriga a reescrever a faixa (*zone*) inteira ao redor. O disco
  usa uma zona de cache (CMR) e faz *garbage collection* depois. Consequências
  práticas:
  - **Leitura sequencial**: parecida com CMR (boa).
  - **Escrita/reescrita aleatória**: pode despencar para poucos MB/s quando o
    cache satura, com **travadas** enquanto o disco reorganiza as telhas.
  - **Seek concorrente** (vários leitores ao mesmo tempo, ou ler enquanto escreve)
    é especialmente ruim: as cabeças passam a saltar e o *throughput* real cai muito.
  - Drives **SMR device-managed** escondem tudo isso do SO — não dá para "ver" a
    zona; só dá para **evitar o padrão de acesso ruim**.

Muitos HDs de alta capacidade "de prateleira" (e vários USB externos) são SMR sem
avisar na caixa. No acervo do ServidorCedro, os discos mecânicos grandes tendem a
SMR; o CMR de referência é o WD Purple (DiscoL).

### 14.2 Como o programa trata isso

O princípio é simples: **ler o mínimo, uma vez, sem concorrência desnecessária, e
nunca deixar I/O pendurado**. Na prática:

- **Nada de rg/fd órfão** (B1): uma busca cortada ou uma janela fechada no meio
  **matam o processo** (`engine._reap`). Sem isso, um `rg` abandonado continuaria
  varrendo o disco inteiro em background — exatamente o *seek* concorrente que
  mata o SMR e ainda competiria com os daemons do acervo.
- **AND com restrição progressiva** (opt#1, §13.2): o segundo termo de um `AND`
  lê **só os arquivos que o primeiro já selecionou**, não a árvore toda. Menos
  arquivos abertos = menos I/O = menos castigo no SMR.
- **Multi-glob fundido** (opt#3, §13.4): buscar por vários tipos de arquivo
  (`*.jpg *.png *.gif …`) faz **uma única varredura** do `fd`, não uma por padrão —
  N× menos I/O de diretório num disco que odeia *seek*.
- **`--one-file-system` / chip "1 disco"**: evita que a varredura **cruze para
  outro ponto de montagem** sem querer (respeitado inclusive no fallback Python — B9).
  Útil para manter a busca dentro de um único USB e não acordar todos os discos.
- **Imagem grande não decodifica síncrona** (B12/N3): teto de 64 MB → placeholder.
  Um TIFF de 200 MB num SMR levaria segundos de leitura e **congelaria a UI**.
- **Streaming, não slurp**: o motor consome a saída do rg/fd linha a linha e emite
  resultados ao vivo; não acumula o disco inteiro em memória antes de mostrar nada.
- **Metadados por `os.stat`** só nos candidatos que já passaram no filtro de nome —
  não se faz `stat` de tudo.

### 14.3 Paralelismo consciente (opt#2, implementada)

A otimização **#2 (termos independentes em paralelo)** já está no código (§13.3) e é
ligada **quando os paths NÃO estão sob `/mnt` / `/media` / `/run/media` num disco
rotacional/desconhecido**: em CMR/SSD, 2–3 `rg` concorrentes aproveitam a CPU do i7; em
SMR/USB rotacional, o *seek* concorrente faria mais mal que bem, então lá a busca continua
**serializada** de propósito (`_max_workers` devolve 1). O **refinamento v3** olha o
`rotational` do sysfs, então um SSD/NVMe montado sob `/mnt` (ex.: `/mnt/optane`) **não** é
serializado à toa — só o rotacional (ou o desconhecido, por segurança) é. Essa é a regra de
ouro do projeto: **paralelizar onde o disco aguenta, serializar onde ele sofre**. O grau de
paralelismo é afinável por `LFS_WORKERS` (default 3; `1` serializa tudo).

---

## 15. F9a — Montagens de rede: classificação e gate de descida

Objetivo: **uma montagem de rede morta nunca congela a busca nem a deixa muda.**
Classificar sem tocar na rede, sondar num processo descartável, pular com aviso.

### 15.1 Classificação de leitura — `disks.search_profile(path, mounts=None) -> IOProfile`

Pura: fstype da montagem de prefixo mais longo + `rotational` do dispositivo; não
sonda a rede. `mounts` injetável para os testes.

| `klass` | Quando | `is_network` | `max_workers` | `enumerate_default` |
|---|---|---|---|---|
| `network` | fstype em `_NET_FSTYPES` (nfs/nfs4/cifs/smb3/smbfs/smb, sshfs, davfs/webdav, 9p, virtiofs, ncpfs, afs, gluster, lustre, ceph, beegfs) | sim | `NET_WORKERS_PER_MOUNT` = 4 | sim |
| `gvfs` | `fuse.gvfsd-fuse`; **e também MTP** (`_MTP_FSTYPES`: jmtpfs, simple-mtpfs, mtpfs) | sim | 4 | **não** |
| `autofs` | `autofs` (o placeholder acordaria todos os automounts) | sim | 4 | **não** |
| `rotational` | `rotational=1` em qualquer prefixo; ou desconhecido sob `/mnt`, `/media`, `/run/media`, `/var/mnt` | não | pool global | sim |
| `ssd` / `unknown` | `rotational=0`; ou sem nó `/dev/*` (FUSE de app, tmpfs, ZFS) | não | pool global | sim |

`serialize` segue preso ao prefixo de acervo (`_under_mount`) de propósito
(comentário de 08/09/2026).

### 15.2 Sonda de vida — `disks.mount_status(mp, timeout=3.0, _stat, _statvfs)`

Devolve `'alive' | 'no_response' | 'broken_mount'`; `mount_alive()` é o wrapper
booleano (só `alive` = `True`).

- **Processo, não thread (achado F1).** `stat` num NFS/FUSE morto fica em D-state
  ininterruptível; uma thread presa impede o `exit_group` e a CLI vira zumbi
  pendurado. O pai faz `os.fork()`; o filho fecha **todas** as fds herdadas menos a
  ponta de escrita do pipe (achado R1: o filho preso segurava o stdout do pai e
  quem lia o `--json` por pipe nunca recebia EOF), faz `_stat(mp)` + `_statvfs(mp)`,
  escreve 1 byte (`A`/`D`) e `os._exit(0)`. O pai espera com `select` até o prazo e
  **abandona** o filho que não respondeu.
- **Reap oportunista.** `_reap_abandoned()` faz `waitpid(WNOHANG)` só nos PIDs que a
  própria função forkou (`_abandoned_pids`), a cada nova sonda.
- **22/09/2026: `stat` + `statvfs`.** O `stat` do ponto de montagem era respondido
  pelo **cache de atributos** do cliente NFS/SMB (medido, NFS real com o servidor
  desligado: "OK" em 0,0 s). `statvfs` vai ao servidor a cada chamada (FSSTAT no
  NFS, QUERY_FS_INFO no SMB, statfs no daemon FUSE): EIO em 9,1 s no *soft*, trava
  no *hard* — o prazo pega os dois.

| Resultado do filho | Veredito |
|---|---|
| `stat` e `statvfs` OK | `alive` |
| `stat` → `_DEAD_MOUNT_ERRNOS` = {ENOTCONN, ESTALE, EHOSTDOWN, ENODEV} | `broken_mount` |
| `stat` → outro errno (EACCES, EPERM, ENOENT, **EIO**) | `alive` (respondeu) |
| `statvfs` → `_DEAD_STATVFS_ERRNOS` = os 4 acima + {**EIO**, ETIMEDOUT, EHOSTUNREACH, ENETUNREACH, ECONNREFUSED, ECONNRESET, ECONNABORTED} | `broken_mount` |
| sem byte no prazo, ou pipe fechado vazio | `no_response` |

### 15.3 Onde a sonda roda

1. **`engine.planejar_raizes`** (F12, §21): cada montagem sob uma raiz vira raiz
   própria; `stat` só em disco local de bloco — rede e FUSE são da sonda. Desde
   22/09 vale também para a raiz digitada (NAS TrueNAS congelado como raiz
   pendurava 150 s). Com `--one-fs` não há expansão, mas cada montagem sob a raiz é
   sondada e as mortas condenadas.
2. **`engine._live_roots(paths, stats, probe_timeout=3.0, …)`** — o gate. Sonda a
   raiz se `prof.is_network` **ou** se ela veio da expansão (qualquer classe: FUSE de
   portal preso em D trava igual). O teste de existência (`_raiz_existe`, H3) só roda
   **depois** da sonda. Preenche `classes` (raiz → `IOProfile`, usado por
   `_jobs_para_classe`) e emite `root_scanning`.
3. **`engine._condena_montagem`** registra a morta em três canais —
   `stats['skipped_mounts']` (`{path, mount, fstype, reason}`), o funil
   (`dead_mount`) e o evento `root_skipped` — e a acrescenta a `mortas`, que vira
   `Query.excluded_paths` (`_query_planejada`): nenhum motor toca nela, nem com `stat`.
4. Os dois motores passam pelo gate: `engine.search` e `boolean.search_boolean`.

### 15.4 Visibilidade

- **CLI texto:** `# warning: mount not responding — skipped: <mount> (<fstype>)`,
  `# note: N kernel filesystem(s) not searched` e, do funil, `# incomplete: …`.
- **CLI `--json`:** `{"warn":"mount_dead","path","mount","fstype"}` e
  `{"warn":"incomplete",…}` no mesmo stream.
- **Exit code:** de `engine.resumo_incompleto` (§20.3).
- **`disks.list_search_targets(paths, probe_timeout=3.0, …)`** (puro, roda em worker):
  quais montagens a busca vai tocar, com classe e vida (só para rede); mesma
  deduplicação de bind por `(st_dev, st_ino)`, só em disco local.
- **Menu "Discos ▾"** (22/09/2026): locais pela Opção B e Rede numa seção à parte —
  ver §22.3.

## 16. F9b — `--index` (plocate) e `--nice-io`

### 16.1 A regra (decisão A do Fable, `lfs/indexed.py`)

**Opt-in explícito; poda = erro claro; nunca automático.**

1. Gatilho só `--index`, e só para busca por nome.
2. Cobertura checada **antes** de buscar; buraco → recusa com `IndexError_`.
3. Zero candidatos com cobertura íntegra: confia no zero, com a data do índice visível.
4. Staleness: todo candidato passa por `lstat` e só sai se ainda existir.

### 16.2 Cobertura — `index_coverage(root, conf, mounts, include_hidden)`

`parse_updatedb_conf` lê `/etc/updatedb.conf` (aspas do shell agrupam: tira as
aspas e divide o conteúdo — `shlex.split` daria um token só; bug corrigido).

| Fonte de buraco | `reason` |
|---|---|
| raiz sob um PRUNEPATH | `prunepath` |
| fstype da montagem da raiz em PRUNEFS | `prunefs:<fs>` |
| PRUNEPATH dentro da raiz | `prunepath` |
| montagem-filha (`disks.mounts_under`) com fstype em PRUNEFS | `prunefs:<fs>` |
| PRUNENAMES (R3), salvo se **todos** começam com `.` e a busca não inclui ocultos | `prunename` |

A cobertura roda sobre o `realpath` da raiz (R4: o plocate devolve caminhos
resolvidos); os resultados voltam traduzidos para o prefixo digitado.

### 16.3 `search_indexed(q, …)`

- Recusa `q.content`.
- `plocate -0 -- <padrão>`; `_padrao_plocate` escapa `\ * ? [ ]` e pede `<raiz>/*`
  quando a raiz tem metacaractere (21/09: `/acervo/[2019] Laudos` virava classe de
  caracteres → zero falso).
- Mesmos filtros da busca viva: subtree (`_under`), componente oculto abaixo da raiz
  (21/09), `engine._name_matcher` (inclui as variantes legadas e NFD, §22.2),
  profundidade no sentido do fd, `lstat`, `engine._passes_meta`.
- `_run`, `_lstat`, `mounts` e `_conf_text` injetáveis.

### 16.4 Fluxo na CLI

| Situação | Saída |
|---|---|
| `--index` com conteúdo ou booleano | `# error: …`, exit 2 |
| `--index --follow` (o updatedb não atravessa symlink) | exit 2 |
| plocate ou `/var/lib/plocate/plocate.db` ausente | exit 2 |
| OK | `# index: results as of the index built on <data>`; `{"warn":"index_used","index_date"}` no json |
| buraco de cobertura | `{"error":"index_coverage"}` / `# error:`, exit 2 |
| fim | exit 0 achou, 1 não achou |

### 16.5 `--nice-io` (F9b §3.5)

`os.nice(19)` + `ionice -c 3 -p <pid>` (binário `ionice`, se existir — a stdlib não
tem ioprio). Os filhos `rg`/`fd` herdam as duas prioridades; falhas são engolidas.

## 17. F9c — Motor de cópia (`lfs/fileops.py`, `lfs/copyjobs.py`)

### 17.1 Princípio

Não destrutivo por construção: origem aberta só com `"rb"`; o módulo não tem
delete/move/rename/chmod da origem. A única remoção é `_rm_partial` (o parcial que
o próprio processo criou no destino). Por padrão nada é sobrescrito.

### 17.2 Capacidades do destino — `disks.dest_caps(path) -> DestCaps`

`_caps_for(fstype, path, mountpoint)` é pura. Em gvfs o perfil vem do **esquema** do
primeiro componente (`mtp:host=…` → `mtp`), nunca do fstype — o mesmo
`fuse.gvfsd-fuse` serve mtp, sftp, smb e dav.

| Perfil | fstypes / esquemas | Limite | symlink | perms | times | charset proibido | `net` |
|---|---|---|---|---|---|---|---|
| FAT32 | vfat, fat, msdos | 4 GiB−1 | não | não | sim | `"*:<>?\|` + reservados DOS | – |
| exFAT | exfat, fuse.exfat | – | não | não | sim | idem, sem reservados | – |
| NTFS | ntfs, ntfs3, fuseblk, fuse.ntfs-3g | – | não | não | sim | idem + reservados | – |
| MTP | jmtpfs, simple-mtpfs, go-mtpfs, mtpfs; gvfs `mtp`/`gphoto2`/`afc` | – | não | não | **não** | idem | – |
| NFS | nfs, nfs4, 9p, virtiofs | – | sim | sim | sim | – | sim |
| SMB | cifs, smb3, smbfs, smb; gvfs `smb-share` | – | não | não | sim | DOS | sim |
| SFTP | fuse.sshfs, sshfs; gvfs `sftp`/`ssh` | – | sim | sim | sim | – | sim |
| WebDAV | gvfs `dav`/`davs` | – | não | não | não | – | sim |
| rede (conservador) | esquema gvfs desconhecido | – | não | não | não | – | sim |
| ISO9660 | iso9660 | – | sim | não | não | – | só-leitura |
| POSIX (padrão) | ext4, xfs, btrfs… | – | sim | sim | sim | – | – |

FAT/exFAT/NTFS/MTP levam `maxchars=255` (unidades UTF-16; o `f_namemax` do vfat diz
1530 — medido em FAT32 real: 254 caracteres passam, 259 não) e `utf8_only` (nome
não-UTF-8 dá EINVAL no pendrive real). `dest_caps` acrescenta `namemax` e
`ST_RDONLY` do `statvfs`, `removable` (`is_removable`: flag `removable` ou
barramento USB, em qualquer disco de um VG/RAID) e `link_mbits` (menor velocidade
USB negociada). `DestCaps.name_problem` devolve uma chave estável (`charset`,
`encoding`, `length`, `reserved`, `trailing`); `DestCaps.sanitize` só com "adaptar
nomes" marcado.

### 17.3 Preflight — `fileops.preflight(sources, dest_dir)`

Não escreve nada no acervo (a única escrita é a sonda):

- `disks.mount_ok`: sob `/mnt`, `/media`, `/run/media`, `/var/mnt`, exige montagem
  real (pasta vazia encheria o NVMe). Desde 21/09 aceita NFS/SMB/ZFS — antes exigia
  fonte `/dev/*` e barrava a cópia para NAS antes da F9c.
- `dest_caps`, `free_bytes`.
- `probe_write`: cria, escreve 16 bytes, fsync e apaga `.sombrero-probe-<pid>-<hex>`
  — só se a montagem existe e não é só-leitura.
- A estratégia (§17.4).

A varredura (`_walk_entries`) corta ciclo por `(st_dev, st_ino)`, não desce no
próprio destino (`SKIP_LOOP`) e enumera `too_big`, `bad_names` (componente a
componente), `links_degraded`, `links_broken`. `fits` exige
`free ≥ copy_bytes × 1,02` (sem os `too_big`). `blocked` = montagem ausente,
só-leitura ou `STRAT_BLOCKED`.

### 17.4 Estratégias — `decide_strategy(caps, probe, has_gio)` (pura)

| Estratégia | Condição | Como grava |
|---|---|---|
| `ATOMIC` | sonda OK, perfil com replace | `<nome>.sombrero-part` → fsync → `os.replace` |
| `GUARDED` | sonda OK, `label=="MTP"` sem gvfs (jmtpfs) | part → fsync → `unlink(dst)` → `rename` |
| `GIO` | sonda falhou, `via_gvfs` (gvfs-MTP) e `gio` presente | `gio copy -- src mtp://HOST/…` por arquivo |
| `BLOCKED` | todo o resto | barra antes do primeiro byte |

`_part_path` encurta o radical quando `.sombrero-part` estouraria `namemax`/`maxchars`.
Se a promoção falhar o part **não** é apagado: o erro cita o nome dele, que tem o
conteúdo novo íntegro.

### 17.5 Ritmo de escrita (pacing)

`BLOCK` = 4 MiB. Com `caps.removable` **ou** `caps.net` (F9c §4.2), `_copy_stream`
chama `_drain` a cada `PACE` = 16 MiB: `fdatasync` + `posix_fadvise(DONTNEED)` na
faixa escrita (e na origem) — limita páginas sujas globais e mantém o progresso
honesto. Referência no comentário: SanDisk Cruzer Fit em USB 2.0 a 11,8 MB/s; 512
MiB de *dirty* seriam 46 s de travamento. Disco interno não tem pacing; todo
arquivo termina com `fsync`.

### 17.6 MTP via gvfs (`_gio_copy`)

Caminho FUSE → URI (`_mtp_uri`, componentes codificados por byte). Sobrescrita:
`gio remove` antes. Cancelar: `terminate` + `gio remove` do parcial. `rc≠0` →
`OSError(EIO)`. Progresso por arquivo inteiro. A GUI avisa quando a estratégia é
GIO e, em `net`, que a estimativa de espaço é pouco confiável
(`PreflightDialog.strategy_note`).

### 17.7 Execução — `copy_to(sources, dest_dir, on_progress, on_conflict, cancel, sanitize_names, plan)`

- Sem `on_conflict`: `skip`. Respostas `skip` / `rename` (`nome (1).ext`) /
  `overwrite` / `cancel`; tupla com `True` aplica a todos.
- Colisão criada pelo próprio sanitize (`a?b` e `a*b` → `a_b`) é numerada (A3).
- `EFBIG` → `SKIP_TOO_BIG`; `ENOSPC` → para o lote, `out_of_space`.
- Cancelar remove o parcial; `_apply_meta` (utime/chmod) só onde `times`/`perms`
  existem; progresso no máximo 10×/s.

### 17.8 Fila persistente e retomada (`copyjobs.py`, F10b #5)

Job = `(sources, dest, sanitize)` em `config.json`, chave `copy_queue`. `snapshot`
grava a cada **transição** (enfileirou/começou/terminou), não a cada arquivo;
`pending` valida e descarta malformadas; `clear` é o "Descartar". Retomar é seguro
porque a cópia é idempotente (ATOMIC não expõe meio-arquivo; o já concluído vira
conflito → Pular; part órfão é lixo reconhecível). Na GUI, `_maybe_resume_copies`
pergunta ao abrir; o `CopyWorker` é um único `QThread` por sessão (preflight →
diálogo → `copy_to`).

## 18. Erros humanos — `lfs/humane.py` (F10b #6)

Toda string de erro que chega à tela passa por `human_error(err, context="",
target="")`; errno cru e `strerror` ficam para log e `--json`. Baldes com frase-fonte
em inglês (traduzida em `i18n._PT`):

| Balde | errnos | Categoria |
|---|---|---|
| rede | ENOTCONN, EHOSTDOWN, EHOSTUNREACH, ENETUNREACH, ENETDOWN, ENETRESET, ECONNREFUSED, ECONNRESET, ECONNABORTED, ETIMEDOUT, ESTALE | `network` |
| espaço | ENOSPC, EDQUOT | `space` |
| demais | EACCES/EPERM, ENOENT, EROFS, ENAMETOOLONG, EIO ("o disco pode estar falhando"), EBUSY/ETXTBSY, EMFILE/ENFILE, EEXIST, EISDIR, ENOTDIR, ELOOP | `file` |

Cláusula de contexto em `_CLAUSES[(context, cat)]` para `search`, `copy`, `mount`
(ex.: rede + search → "A busca continuou nos demais locais"). Exceção não-`OSError`
passa o próprio texto; `OSError` sem errno vira a frase genérica. `SOURCE_STRINGS`
deriva das tabelas e alimenta a guarda de i18n.

---

## 19. F10 — A milha final humana, confiança e duplicatas

### 19.1 F10a — Painel de narrativa da busca (`on_event`)

O motor conta a busca **por raiz** através do callback `on_event(ev, info)`, aceito
por `engine.search()` e `boolean.search_boolean()` (padrão no-op). Desde o H12 o
booleano emite a **mesma** narrativa (`_atribuidor` fatorado para os dois motores;
`search_boolean` fecha cada raiz com `root_done`).

| Evento | Payload | Quem emite |
|---|---|---|
| `root_scanning` | `{path, klass, mountpoint}` | `_live_roots` quando a raiz passa o gate; `_estende_snapshots` para o dono de uma árvore podada |
| `root_skipped` | `{path, mount, fstype, klass, reason}` (+`erro` no particionado) | `_raiz_existe`/`_raiz_montada` (`invalid_root`, `not_mounted`), `_condena_montagem` (`no_response`, `broken_mount`), `planejar_raizes` (`not_entered`), `_rodada._grupo_terminou` (`error`) |
| `root_done` | `{path, found}` | `_rodada`: no particionado, **assim que o disco daquele grupo termina**; no fim, para as que sobraram |
| `snapshots_skipped` / `snapshots_searched` | `{path, ostree, trees}` | `_plano_extensao` (§20.1) |
| `copy` | `{path, of, snapshot}` | `_Entrega.entrega` quando o dedup absorve uma cópia (a GUI ignora; o `--json` publica) |

`engine.REASON_TEXTO` traduz `reason` numa frase EN-US (a chave do i18n); a GUI
passa por `t()` **no evento**, não no import.

**GUI** (`MainWindow._on_root_event` / `_render_narrative`): `QFrame#narrative`
entre a barra de filtros e os resultados, com cabeçalho
(`"{verb} {done}/{total} locations · {found} found · {sec}"`) e uma linha por raiz
com bolinha (verde = pronto, vermelha = pulada, acento = varrendo) e selo de classe
(`_KLASS_TAG`: HD/SSD/MTP/auto/network). O estado (`tab.roots`, `tab.root_order`)
mora **na aba**; um widget só desenha a aba visível; o rótulo do volume
(`disks.volume_label`) é resolvido uma vez no evento — o render não faz I/O.
Montagem morta = **linha vermelha no painel, sem popup**; heartbeat de 0,5 s
atualiza o relógio. Snapshots aparecem como anotação ao lado da raiz.

### 19.2 F10a — Filtro dentro dos resultados (`lfs/resultfilter.py`)

Núcleo puro, sem I/O: `compile_filter(text) -> Predicate(name, path, mtime)`.

| Token | Semântica |
|---|---|
| espaço | E (todos os termos precisam casar) |
| `*.odt` / `.odt` | extensão, sem diferenciar caixa (`_EXT_RE`) |
| `>2019-01` / `<2020` / `>2019-01-05` | mtime depois / antes do **período inteiro** (`_period_bounds`) |
| qualquer outra coisa | substring em nome **ou** caminho, sem diferenciar caixa |

Data inválida (mês 13) cai para substring; filtro vazio aceita tudo. Na GUI,
`ResultFilterProxy(QSortFilterProxyModel)` aplica o predicado sobre o `Match`
carregado, usando `engine.nome_exibivel` (22/09: "médico" casa nome não-UTF-8);
ordenação natural em `lessThan`; filtro **por aba** (`tab.ed_filter`).

### 19.3 F10a — Teclado de ponta a ponta

Os `QShortcut` ficam presos à **janela** (`MainWindow.__init__`), não à tabela —
com abas a tabela muda debaixo do atalho.

| Tecla | Ação |
|---|---|
| Esc | `_on_escape`: cancela se a aba busca **ou está na fila SMR** (`tab.pending`); senão limpa o filtro |
| ↑ / ↓ no campo Nome | `eventFilter` → `_history_step` (só com foco no campo) |
| Ctrl+F / Ctrl+L | foca o filtro da aba / o campo de caminho |
| F3 / Shift+F3 | `_preview_match(±1)`: navega os matches no preview |
| Ctrl+R | `repeat_last`: aba "virgem" (`searches.is_empty`) usa o topo do histórico (conserto de 21/09) |
| Ctrl+N / Ctrl+W | nova aba / fechar aba |
| Ctrl+Return | `start_search(True)` |
| Ctrl+E / Ctrl+S | exportar / salvar a busca |
| Ctrl+C, Ctrl+Shift+C, Alt+Return, Ctrl+T | copiar seleção, copiar caminhos, propriedades, tema |

### 19.4 Histórico, buscas salvas, abas e exportação (`lfs/searches.py`)

- **Snapshot do formulário:** `DEFAULTS` define as chaves; `normalize()` completa e
  **descarta** chave desconhecida (config antigo ou mais novo não quebra).
  `"snapshots"` entrou em `DEFAULTS` em 21/09/2026.
- **Histórico:** `add_history` insere no topo; repetir **reordena** sem duplicar;
  teto `HISTORY_CAP = 30`; formulário vazio não entra.
- **Buscas salvas:** mesmo nome **sobrescreve na mesma posição** (`save_search`);
  `delete_search`, `saved_list`.
- **Abas:** `title_for(form, maxlen=22)` (nome → conteúdo → última pasta); durante a
  busca `"(n…)"` (`_tab_badge`); cada sinal do `SearchWorker` carrega a aba de
  origem, então busca em segundo plano escreve só no modelo dela.
- **Exportação** (`export`): `.json` → JSON, o resto → CSV; grava em
  `path + ".sombrero-part"` e promove com `os.replace` (falha apaga o temporário);
  `errors="surrogateescape"` (nome não-UTF-8 volta aos bytes originais). A GUI
  exporta **na ordem da tela** (ordenada e filtrada).
  - CSV (`export_csv`): `;`, uma linha por trecho,
    `path;folder;name;size;modified;matches;snapshot;copies;line;text`.
  - **Anti-fórmula** (`celula_csv`, 21/09/2026): célula de **texto** que começa com
    `= + - @ TAB CR` (`_CSV_GATILHOS`) ganha `'`; números intactos; JSON cru.
  - JSON (`export_json`): um objeto por **arquivo**, com `lines[]`, `snapshot`, `copies[]`.

### 19.5 F10b — Pós-cópia: "seguro remover" e Ejetar

- `disks.removable_dest(path, mounts=None) -> (removível, mountpoint, dev)` (pura):
  `is_removable` = flag `removable=1` **ou** barramento USB, em qualquer disco do
  volume (`_sys_disks`).
- `disks.luks_backing(dev, sysfs=…)`: dm-crypt aberto (`dm/uuid` "CRYPT-" + um só
  `slaves/`) → `/dev/<partição cifrada>`; senão `None`.
- `disks.eject_command(mp, dev, *, which=None, backing=None)` → **lista de PASSOS**
  ou `None`: com `gio`, `[["gio","mount","-e",mp]]` (um passo: flush, tranca o LUKS,
  desliga); sem `gio`, `udisksctl unmount` → `lock` (só LUKS) → `power-off`; sem
  nenhum, `None` e o botão não aparece.
- **GUI:** `on_copy_done` guarda `_safe_eject` se a cópia gravou algo, não parou por
  espaço, o destino é removível e há comando; `on_copy_all_done` mantém
  *"Copied and synced — safe to remove."* com **⏏ Eject** (a frase se apoia no
  `fsync` por arquivo do ATOMIC). `_eject_dest` roda os passos em ordem
  (`timeout=30` cada) e para no primeiro erro; se o `unmount` passou e o `power-off`
  falhou, diz que já pode tirar.
- Cópia > 30 s com a janela minimizada/inativa → `_notify` (`notify-send`, senão a
  bandeja do Qt, senão silêncio).
- Validado em bancada real (pendrive com 2 LUKS + 1 ext4, 21/09): o udisks recusa
  desligar com partição vizinha montada; o `gio` ejeta o **pendrive inteiro** (como o
  Nautilus), desmontando e trancando as vizinhas.

### 19.6 F10c — Caçador de duplicatas (`lfs/dupes.py`)

**Linha vermelha:** acha, mostra e exporta; **não existe API de remoção**
(`test_dupes_no_delete_api` verifica o AST).

Duas entradas no mesmo funil `_dedup(cands, …)`: `find_duplicates(roots)` (`_walk`,
`os.walk`) e `find_duplicates_in_files(files)` (`_collect`, lista exata, sem descer
em pastas); `test_dupes_in_files_matches_walk` garante o mesmo resultado.

| Estágio | O que faz | Constantes |
|---|---|---|
| 0 — identidade | colapsa `(st_dev, st_ino)`: **hardlink = 1 candidato** com vários `paths`; symlink e tamanho 0 fora (`include_zero` liga); `min_size` | — |
| 1 — tamanho | só quem tem ≥ 2 com o mesmo tamanho | — |
| 2 — cabeça | BLAKE2b dos primeiros bytes, fila em ordem `(dev, path)` | `HEAD_BYTES` = 64 KiB, digest 16 B |
| 3 — completo | BLAKE2b completo, **sequencial por dispositivo**, cancelamento por bloco, progresso em **bytes** | `FULL_BLOCK` = 1 MiB, digest 32 B |

- `_fadvise_dontneed` após ler (não expulsa o cache de quem usa a máquina).
- 21/09/2026: `_head_and_full` — cabeça que bate no EOF (arquivo < 64 KiB) já dá o
  digest completo, sem reabrir.
- Cancelar → `[]`, sem estado. `DupGroup` (`size`, `digest`, `members`,
  `wasted = size·(n−1)`) ordenados por `wasted`; `summary()` → `(grupos, bytes)`.
- **`name_verdicts(files, groups)`**: "cópia × versão" **sem hash novo** — colapsa
  hardlinks por `lstat`, agrupa por basename → `IDENTICAL` / `DIVERGENT` / `MIXED`
  (tamanho diferente já é "versão").
- **Export** (`dupes.export`): CSV `group,hash,size,path` (com `celula_csv` no
  caminho) e JSON `hash,size,wasted,paths`, ambos `surrogateescape`.
- **GUI:** `DuplicatesPanel` = página "⧉ Duplicates" do `workspace`;
  `DupWorker(roots=… | files=…)`; modo "resultados" monta a árvore por nome com selos
  🟢/🟠/🟡; "varredura ampla", por conteúdo. Menu "Discos ▾" compartilhado com a
  busca (`preenche_menu_discos`, 22/09).

## 20. F11 — Snapshots, busca particionada por disco e funil de incompletude

### 20.1 Árvores de snapshot: poda, fallback e dedup

**Poda** (`engine.EXCLUSOES_SNAPSHOT`) — globs **por componente**, não substring
(`meus_timeshift_backups/` não é vítima):

`timeshift/snapshots*` · `timeshift-btrfs` · `.snapshots` · `.zfs/snapshot` · `@GMT-*` · `ostree/repo` · `ostree/deploy`

- `eh_snapshot(path)` casa os componentes em sequência; `_globs_snapshot()` gera
  `**/{m}/**` e `**/{m}` para o `--exclude` do fd e o `!glob` do rg — a poda é **no
  motor**, porque o custo é a caminhada.
- Ruído (`node_modules`, `.git`, `/nix/store`) **nunca** entra: só cópias do sistema.
- `_achados_snapshot(root)` → `(padrao, caminho)` de cada árvore que a raiz hospeda,
  **inclusive em montagens abaixo dela** (via `user_mounts()`), derivado de
  `EXCLUSOES_SNAPSHOT`. `tem_snapshot` é o `bool` disso. (No NAS TrueNAS de
  22/09: `.zfs/snapshot` exposto pelo SMB, pulado e anotado.)
- `_pula_snapshot(paths, base)`: raiz que aponta **para dentro** de um snapshot
  desliga a poda **só no grupo dela** (F11 bug3).

**"Vivo primeiro, podadas só se faltar"** (decisão de 09/09/2026): `search()` e
`search_boolean()` fazem a rodada viva **sempre podada**; depois
`_estende_snapshots` → `_plano_extensao` decide **por raiz DIGITADA**:

| Modo | Condição | Estende? | Motivo no funil |
|---|---|---|---|
| `stopped` | a rodada viva parou (teto/cancelamento) | não | `snapshots_skipped` |
| `requested` | `skip_snapshots=False` (`--snapshots` ou a caixa) | sim | `snapshots_searched` |
| `searched` | zero achados vivos na raiz digitada | sim | `snapshots_searched` |
| `skipped` | havia achado vivo | não | `snapshots_skipped` |
| `no_fallback` | só árvore de `EXCLUSOES_SEM_FALLBACK` (`ostree/repo`) | nunca | `snapshots_skipped` |

Texto em `_TEXTO_PODA[(tipo, modo)]` (tipo `ostree` quando todos os padrões são de
`_PADROES_OSTREE`). `_query_extensao`: as raízes viram as árvores, poda desligada,
montagens sob a árvore excluídas (no ostree `/var` é bind de `deploy/<os>/var`).
`_arvores_podadas` ignora árvore sob montagem morta/não viva e deduplica por `realpath`.

**Dedup de resultados** (`_Colapso` em `_Entrega`, compartilhado por busca,
booleano, CLI e GUI):
- Identidade: `Match.ident = (st_dev, st_ino)` do **lstat** (symlink é outro objeto).
- Cópia idêntica: `(caminho vivo, size, int(mtime))`; para achado de snapshot,
  `_caminho_vivo(path, arvore, padrao)` reconstrói o caminho vivo por layout
  (Timeshift `…/<data>/localhost/<rel>`, btrfs `@`/`@x`, snapper `<n>/snapshot`, ZFS,
  `@GMT-*`, `ostree/deploy/<os>/deploy/<hash>/`).
- Quem chega primeiro fica: o **vivo tem precedência por construção**; o absorvido
  entra em `dono.copies`, sai o evento `copy`; achado de snapshot ganha
  `m.snapshot = <árvore>`. GUI: "+N copies" no nome e as cópias no tooltip.
- Risco declarado no código: dois arquivos diferentes no mesmo caminho vivo, mesmo
  tamanho e mesmo segundo de mtime, colapsam.

### 20.2 Busca particionada por disco

Motivação (comentário em `engine.py`): um `fd` com 10 raízes tem um pool global e
cego às montagens — medido no acervo, 9 discos terminavam em < 1,4 s e o
4TB-Portable sozinho levava 168 s.

| Peça | Papel |
|---|---|
| `_chave_de_disco(root)` | identidade do **disco físico**: `("disco", frozenset(disks._sys_disks(dev)))`; ZFS → `("zpool", pool)`; composefs herda pelo `datadir` (`disks._backing_dev`); reserva `("dev", st_dev)` |
| `_grupos_por_disco(paths)` | raízes do mesmo prato no mesmo grupo; conjuntos que se cruzam (VG em 2 PVs) se **fundem**; sem `stat` → grupo `("?", r)` isolado |
| `_separa_raizes_com_mortas` | raiz com montagem morta embaixo ganha processo próprio (o `--exclude` do fd ancora na 1ª raiz — F12b) |
| `_iter_particionado` | uma thread por grupo (`sfs-disco-N`), fila com contrapressão `_FILA_MAX = 4096`, `ao_fim(paths, stats)` **depois** dos achados do grupo; saída antecipada → `terminate` em laço até 5 s; grupo sem `FIM` → `interrupted` (H9) |
| `_rodada` | 1 grupo → serial; mais → particionado; a mesma fábrica escolhe rg/rga/fd/Python (o fallback Python também particiona) |
| `_funde_stats` | soma os stats dos workers; o funil é **reanotado** (H7), preservando `args` |

**Threads por processo** (`_jobs_para_classe(classes, conteudo)` → `--threads` do
fd/rg e `rg_threads` do booleano):

| Situação | jobs |
|---|---|
| rede / gvfs / autofs | `disks.NET_WORKERS_PER_MOUNT` (4) |
| **conteúdo** (local) | `None` (padrão do motor; fila funda ajuda até em SMR) |
| nome, perfil `serialize=True` | 1 |
| nome, `ssd` / `unknown` | `None` |
| `rotational` (`_JOBS_POR_CLASSE`) | 1 |

Grupo misto fica com o mínimo concreto. Medições citadas nos comentários: NVMe
com `--threads 1` custa 12,5×; SMR de 1,15 M inodes, `--threads 1` ganha 21%; SMR
de 8 TB por nome: 1 thread 38 s × pool 48 s; por conteúdo: pool 35 s, 4 threads
38 s, 1 thread 52 s.

**`path_needs_serial`** (disco sob `/mnt|/media|/run/media|/var/mnt` **e**
`rotational != "0"`, desconhecido = serial): na GUI, `_serial_paths` → `_must_wait`
põe a aba na fila (`tab.pending`, liberada por `_start_pending`); no booleano,
`boolean._path_needs_serial` (espelho mantido para os mocks) alimenta `_max_workers`
(pool do OR **por grupo de disco**). O `NOT` computa o universo por grupo (correto:
a partição é disjunta).

### 20.3 Funil único de incompletude

Canal único: `stats["incompleto"]`, lista de `{motivo, onde, detalhe, n, args?}`.
Os canais antigos (`denied`, `skipped_mounts`, `engine_errors`, `erros`) seguem
preenchidos, mas são **vista**, não fonte.

- `anota_incompleto(stats, motivo, onde, detalhe, n, args)` agrega por
  `(motivo, onde)`; teto `_INCOMPLETO_MAX = 200` (excedente em
  `incompleto_omitidos`); `detalhe` cortado em `_DETALHE_MAX = 300`. `detalhe` é a
  frase EN-US **literal** (chave do i18n); o que varia vai em `args`. O booleano usa
  `_anota` (o mesmo, sob `_cache_lock`).
- `texto_detalhe(e, tr)` traduz e só então aplica `.format(**args)`.
- `resumo_incompleto(stats, tr) -> (grave, linhas)`: **fonte única** da barra da GUI
  e do exit code da CLI.
- `MOTIVOS_GRAVES = {engine_failed, engine_missing, disk_failed, invalid_root, not_mounted}`
  — "o resultado pode estar **errado**".

| Motivo | Origem principal | Grave |
|---|---|---|
| `engine_failed` | `_reap`: rc ∉ {0,1,−15,143}, exceto se a queixa é só permissão/laço de symlink, só erro por caminho (`_RX_ERRO_MOTOR`, 22/09), ou o processo foi morto por nós | ✔ |
| `engine_missing` | Popen falhou (fd/rg, `boolean`) | ✔ |
| `disk_failed` | exceção no worker de `_iter_particionado` | ✔ |
| `invalid_root` | `_raiz_existe`: não existe ou não é pasta | ✔ |
| `not_mounted` | `_raiz_montada`: está no `/etc/fstab` e não está montada | ✔ |
| `permission_denied` | stderr "ermission denied" (`_reap`), `_walk_onerror`, fallback Python | — |
| `read_error` | demais linhas de stderr por arquivo; erro de leitura no fallback | — |
| `dead_mount` | `_condena_montagem` (gate); errno 107/116/112/19 no stderr (`_linha_de_montagem_morta`) | — |
| `mount_not_entered` | `planejar_raizes`: gvfs/autofs/MTP (`enumerate_default=False`) | — |
| `empty_mountpoint` | vaga de montagem vazia que não é mountpoint (indício) | — |
| `stat_failed` | o motor listou, o `stat` falhou (H5) | — |
| `batch_failed` | lote do booleano falhou | — |
| `truncated` | `_Entrega` bateu em `max_results` | — |
| `interrupted` | o disco não respondeu ao cancelamento a tempo (H9) | — |
| `snapshots_skipped` / `snapshots_searched` | `_plano_extensao` | — |

**Como aparece:**
- **CLI:** cada linha vira `# incomplete: …` no stderr; com motivo grave,
  `results are INCOMPLETE — this is not 'nothing was found'`. No `--json`,
  `{"warn"|"error": "incomplete", reason, where, detail, count}` ("error" quando grave),
  junto de `mount_dead`, `denied` e das notas de `pruned_mounts`.
- **Exit codes** (estilo grep): **0** achou; **1** nada; **2** grave ou erro de uso
  (tamanho/profundidade inválidos, `--min-size` > `--max-size`, expressão booleana
  inválida, falhas do `--index`); **130** Ctrl-C (`_main_protegido`). Negação de
  permissão **não** muda o código.
- **GUI:** `on_done` → `_funil_para_barra` (✔/⚠/■, até 3 linhas + `(+N more)`). Os
  motivos que o painel já desenha para a raiz (`_MOTIVOS_NO_PAINEL`: snapshots_*,
  dead_mount, invalid_root, not_mounted, mount_not_entered) saem da barra, mas
  `grave` é calculado sobre o funil **inteiro**.

---

## 21. F12 — Expansão de raízes

> Código: `engine.planejar_raizes`, `_live_roots`, `_query_planejada`,
> `_condena_montagem`, `_separa_raizes_com_mortas`, `_excludes_fd`,
> `rg_flags_comuns`, `_iter_names_python`; topologia em `disks.mounts_under`,
> `search_profile`, `mount_status`. Os dois chamadores são idênticos:
> `engine.search()` e `boolean.search_boolean()`.

### 21.1 O problema

O gate F9a (`_live_roots`) só sondava o que o usuário **digitou**: numa busca em
`/`, a raiz passava como disco local e o `fd` descia sozinho até uma montagem de
rede morta — o congelamento que o gate existe para evitar (decisão de 09/09/2026).
O F12 dá outro sentido a "buscar em `/`" ou "em `/mnt`": **em tudo que mora ali
embaixo, inclusive NFS/SMB**.

### 21.2 Pipeline (igual na busca simples e na booleana)

```
planejar_raizes(q.paths, q.one_file_system, stats, on_event, mortas=mortas)
      → (roots, expandidas, forca_one_fs)
_live_roots(roots, stats, ..., expandidas=expandidas, mortas=mortas)   # gate F9a por raiz
      → raízes vivas
_query_planejada(q, roots, forca_one_fs, mortas)
      → Query(paths=roots, one_file_system |= forca_one_fs, excluded_paths=mortas sob as raízes)
_rodada(...) → _separa_raizes_com_mortas(_grupos_por_disco(roots), q.excluded_paths)
```

O booleano faz `parse(expr)` **antes** de `planejar_raizes` (21/09/2026): erro de
sintaxe não espera a sonda de cada NAS.

### 21.3 `planejar_raizes(paths, one_fs, stats=None, on_event=..., mounts=None, mortas=None, probe_timeout=3.0)`

Devolve `(roots, expandidas: set, forcar_one_fs: bool)`; `mounts` injetável.

1. Remove duplicatas de `paths`, mantendo a ordem.
2. Sem `disks` importável: devolve `(roots, set(), False)`.
3. **`one_fs` explícito** (`--one-fs` / "1 disco"): **não expande**. Mesmo assim
   cada montagem sob a raiz que não seja pseudo-fs passa por `mount_status`; quem não
   for `"alive"` é condenado (§21.5) — o walker com `--one-file-system` ainda faz
   `stat` em cada ponto de montagem para comparar `st_dev`, e isso trava em D-state
   (F12b).
4. **Expansão**, para cada montagem `mp` sob cada raiz:

| Condição | Tratamento | Canal |
|---|---|---|
| já é raiz digitada ou já vista | ignorada | — |
| fstype em `_PSEUDO_FS` do F12 (proc, sysfs, devtmpfs, devpts, cgroup/2, securityfs, pstore, efivarfs, bpf, debugfs, tracefs, configfs, fusectl, hugetlbfs, mqueue, binfmt_misc, nsfs, rpc_pipefs, selinuxfs) | podada | `stats['pruned_mounts']` (nota; a CLI imprime `# note: N kernel filesystem(s) not searched`) |
| `search_profile(mp).enumerate_default == False` (gvfs, autofs, MTP) | não entra | funil `mount_not_entered` (não-grave) + `root_skipped` `reason="not_entered"` |
| local de bloco e `st_dev(mp) == st_dev(raiz-mãe)` | bind do **mesmo FS**: não vira raiz | — |
| demais | candidata `(mp, ident)`; `ident = (st_dev, st_ino)` só se local de bloco — rede/FUSE ficam com `ident=None` e **nenhum `stat`** | — |

`tmpfs`, `squashfs` e `overlay` **ficam** na expansão ("há arquivo de verdade
lá"). Subvolume btrfs tem `st_dev` próprio e vira raiz.

5. **Bind do mesmo diretório entre irmãs (ostree/Bazzite).** `/var` é bind de
   `/sysroot/ostree/deploy/default/var`; as duas têm `st_dev` diferente do de `/`
   (composefs), então o `/var` era varrido 2×. Candidatas com a mesma identidade
   `(st_dev, st_ino)` entram **uma vez**: a digitada vence; entre expandidas, a de
   **caminho mais curto** (`(len(mp), mp)`) — o nome que o usuário conhece. Não é
   perda (o diretório é varrido sob o outro nome), por isso não passa pelo funil.
6. As vencedoras entram em `roots` e `expandidas`; `forcar_one_fs = bool(expandidas)`
   — o walker da mãe roda com `--one-file-system` para não entrar de novo.

**22/09/2026 (`dd85092`, NAS TrueNAS real):** o `stat` da **própria raiz**
(`_st_dev(r)`, `_ident(r)`) rodava antes da sonda; com a raiz sendo um NAS
congelado, a busca pendurava (150 s medidos). Agora a raiz só leva `stat` quando
`raiz_segura` (`search_profile(r)` local e fstype que não começa com `fuse`).
Coberto em `test_montagens_opcao_b_2026_09_22.py` (o `stat` do motor vira armadilha).

### 21.4 Gate das expandidas (`_live_roots`)

- A expandida é **sempre** sondada, de qualquer classe (FUSE de portal preso em D
  trava igual a um NFS): o teste é `prof.is_network or root in expandidas`.
- Expandida morta vira `dead_mount` (não-grave), não `invalid_root`; expandida viva
  não passa por `_raiz_existe` (está montada por definição).

### 21.5 F12b — montagem morta nunca é tocada (`Query.excluded_paths`)

`_condena_montagem` registra a morta em `stats['skipped_mounts']`, no funil
(`dead_mount`, `"{fstype}: {status}"`), no evento `root_skipped` e em `mortas`, que
`_query_planejada` filtra para as que estão **sob** alguma raiz viva e guarda em
`Query.excluded_paths`.

| Motor | Mecanismo | Onde |
|---|---|---|
| `fd` | `--exclude '/<rel>'` relativo à raiz; o fd 10.4 ancora `/x` só na **primeira** raiz do processo (medido), então cada raiz com morta embaixo ganha **processo próprio** | `_excludes_fd`, `_separa_raizes_com_mortas` |
| `rg` | `--glob '!**<abs>'` (no rg 14.1 `!/abs` não ancora — medido) | `rg_flags_comuns` |
| Python | poda `dns[:]` do `os.walk` **antes** de descer, sem `stat` | `_iter_names_python` |
| snapshots | a extensão recebe `excluded_paths` | `_query_extensao`, `_estende_snapshots` |

Detecção tardia no `_reap`: linha de stderr com errno de montagem morta
(`_ERRNO_MONTAGEM_MORTA` = 107/116/112/19, `_linha_de_montagem_morta`) vira
`dead_mount` naquele caminho, não `read_error`.

### 21.6 Lacuna declarada

`test_diferenca_conhecida_preview_lista_montagem_do_mesmo_fs`
(`test_correcoes_2026_09_10.py`) fixa de propósito: o preview
`disks.list_search_targets` **não** aplica a regra "mesmo `st_dev` da mãe", então o
número do preview pode ser **maior** que o de raízes efetivas.

### 21.7 Testes

`test_audit.py` (`test_planejar_expande_montagens`, `test_excluded_paths_todos_os_backends`),
`test_paralelo_por_disco.py` (bind do ostree), `test_correcoes_2026_09_10.py`
(identidade compartilhada com o preview, lacuna do §21.6),
`test_revisao_fable_2026_09_21.py` (parse antes do gate),
`test_montagens_opcao_b_2026_09_22.py` (raiz de rede sem `stat`).

---

## 22. Revisão de 21–22/09/2026 (Fable + sessão de correções)

Parecer de revisão do Fable (21/09, 17 defeitos, 3 commits) seguido de uma série
de itens, um por vez, cada um com teste que **falha** no código anterior. Fluxo
completo, com medições, no relatório de campo e nos commits `50c2cf9`…`7179468`.
Evidência bruta do teste com NAS real em `docs/campo/2026-09-22-nas-truenas/`.

### 22.1 Motor e cancelamento (`engine.py`)

| Mudança | Onde | Por quê (medido) |
|---|---|---|
| Thread-vigia por processo fd/rg dá `terminate()` quando `cancel()` vira True | `_vigia_cancel` | o `cancel` só era visto entre leituras do pipe; no Toledo, cache frio: 8,15 s → 1,02 s |
| Morte por sinal que NÓS mandamos não é falha | `_reap` (`nos_matamos`) | kill −9 de processo em D-state virava `engine_failed` |
| `rg --json` com `{"bytes": b64}` (caminho/linha não-UTF-8) | `_rg_caminho`, `_rg_linha` | achado de conteúdo em nome não-UTF-8 era descartado mudo |
| Booleano lê `rg -l --null` em bytes | `boolean._le_caminhos_nul` | nome mutilado virava `restrict` inválido → exit 2 |
| Laço de symlink (`File system loop found`) é queixa benigna | `_reap` (`benigna`) | com `--follow`, "search engine failed" + exit 2 sem perda nenhuma |
| Queixa só de CAMINHO (`<path>: … (os error N)`) é `read_error`, não `engine_failed` | `_reap` (`so_por_arquivo`) | 6 nomes reservados do DOS que o NAS lista mas não abre derrubavam a busca inteira |
| `_rodada` fecha o gerador em `try/finally` | `_rodada` | exceção no `on_result` (pipe, Ctrl-C) deixava fd/rg vivo até o GC |

### 22.2 Codificação legada — conteúdo E nome, qualquer idioma (`engine.py`)

Decisão do Rodrigo: sempre ligado, alcance mundial. Tabela `LEGADAS` (~30
codificações: Windows 1250–1258/874, ISO-8859-x, KOI8-R/U, DOS 850/866, Mac
Roman/Cyrillic; Shift-JIS/EUC-JP/GBK/Big5/EUC-KR só para termo com
ideograma/kana/hangul).

- **`legado_variantes(termo)`** → os BYTES que o termo teria em cada codificação
  que o representa, com a caixa dos bytes acentuados (`(?-u:[\xC7\xE7])`). Sai
  sempre da forma NFC.
- **Critério contra acerto falso em UTF-8** (`_possivel_em_utf8`): a variante entra
  se for impossível em UTF-8 válido, ou possível só nas bordas mas longa (≥ 4
  bytes) ou ancorada em letra ASCII. "é" sozinho (`E9`, começo de ideograma) fica
  fora. Para NOME, o critério vale **por trecho literal entre coringas**
  (`_encs_do_glob`) — o `*` não ancora nada.
- **`rg_padroes(termos, q)`**: fonte única do padrão nos 3 pontos que chamam o rg
  (conteúdo, termo e linhas do booleano). Termo ASCII e regex do usuário: como
  antes (`--fixed-strings`/regex crua). Custo medido: +1% a +6%.
- **Nome** (`_glob_to_regex(rust=True)`, `_merge_globs`): dialeto do fd em que `*`
  casa QUALQUER byte (`(?s-u:.)*`). Consertou também a fusão de 4+ globs, que
  perdia calada todo nome não-UTF-8. Glob com letra não-ASCII vai sempre para a
  regex fundida (caixa Unicode — o glob do fd só dobra ASCII).
- **Fallback Python** (`casa_legado`, `_name_matcher`): as mesmas codificações —
  paridade conferida por `test_parity_rg_python.py`.
- **`formas_unicode`**: termo e glob também na forma NFD (nome do macOS).
- **Exibição**: linha casada na codificação em que o termo aparece
  (`texto_para_termos`); sem termo (nome, preview), na codificação legada da
  REGIÃO (`codificacao_legada`, pelo locale; `SFS_LEGACY_ENCODING` força).
  cp1258 (vietnamita) com tom combinante (`_forma_cp1258`) + NFC na saída.

### 22.3 Montagens e rede (`engine.py`, `disks.py`)

- **`classifica_montagens`** (Opção B dos pareceres de julho): disco de usuário é
  o que NÃO é de sistema. `user_mounts()` (locais) e `network_mounts()` (NFS,
  SMB, sshfs, WebDAV, rclone). A lista de fs não-usuário é `_FS_NAO_USUARIO` —
  nome próprio: o homônimo `_PSEUDO_FS` do F12 a sobrescrevia no import e
  zram/overlay com origem `/dev` passavam como disco (`7179468`).
- **`mount_status`**: o filho faz `stat` **e** `statvfs` — o `stat` era respondido
  pelo cache de atributos com o servidor morto; `statvfs` vai ao servidor.
  Errnos de `statvfs` que significam "servidor mudo" → morta (`_DEAD_STATVFS_ERRNOS`).
- **`planejar_raizes`**: raiz de rede/FUSE não leva `stat` (a sonda vem depois).
- **`mount_ok`** não exige mais fonte `/dev/*` (cópia para NAS/ZFS sob /mnt).
- **Ejetar** (`eject_command` → PASSOS; `luks_backing`): sem `gio`, desmonta →
  tranca o LUKS → desliga; GUI para na primeira falha e diz a verdade.

Medido com TrueNAS real (VM, SMB pela tailnet): NAS congelado → pulado em 3,4 s
com `dead_mount`; o kernel (cifs) fica calado por 180 s. **Teste com NAS
"fresco"**: a segunda rodada engana, o cliente já marcou o servidor.

### 22.4 CLI (`cli.py`)

- Fala **inglês em qualquer locale** (o `detail` do `--json` é contrato de automação).
- `| head` e Ctrl-C saem limpos (pipe fechado cancela a busca; Ctrl-C → 130).
- Novas: `--max-size`, `--depth N` (≥ 1), `--follow`. Tamanho inválido e mínimo >
  máximo = exit 2 (antes `--min-size 10X` era ignorado calado). `--index --follow`
  recusado.

### 22.5 GUI (`app.py`)

- Ctrl+R em aba virgem cai na última busca do histórico (`searches.is_empty`).
- Nome não-UTF-8: legível (codificação da região), em **itálico**, tooltip com a
  codificação (`nome_exibivel`, `nota_nome_antigo`) — tabela, filtro, ordenação,
  Propriedades, duplicatas, preview, player, mensagens.
- Toda QUrl local passa por `url_local()` (bytes → percent-encoding): Abrir,
  Abrir pasta e o player chegavam em arquivo inexistente com `QUrl.fromLocalFile`.
- "Copiar caminho" e o texto do Ctrl+C/arrastar: forma do terminal
  (`caminho_para_shell`) para nome não-UTF-8.
- Menu "Discos ▾": função única `preenche_menu_discos`; seção **Rede** à parte,
  fora de "Todos os discos" (decisão do Rodrigo).
- `_peek` só lê arquivo regular, no máximo 256 KiB (FIFO congelava a janela).
- **Caracteres invisíveis no nome** (RLO e demais controles de direção, ZWSP, WJ,
  BOM, hífen suave — `engine._INVISIVEIS`): aparecem como marcador `⟦RLO⟧` no lugar
  exato, em itálico, com tooltip (o RLO fazia `fatura_\u202Etxt.exe` parecer
  "fatura_exe.txt"); "copiar caminho" os escreve como `\u202e` na forma do terminal.
  A busca por nome os ignora (fd: invisíveis opcionais entre cada letra da regex,
  custo no ruído; Python/`--index`: `sem_invisiveis`). Com isso **todo glob de
  basename vai à regex fundida** (o antigo limiar de 4 globs saiu). Decisões do
  Rodrigo; teste `test_invisiveis_2026_09_22.py`.

### 22.6 Exportação e duplicatas (`searches.py`, `dupes.py`)

- CSV à prova de fórmula (`celula_csv`: `= + - @ TAB CR` → `'`), busca e
  duplicatas; JSON cru. Decisão do Rodrigo (OWASP).
- `export` com `surrogateescape` + temporário/`os.replace`.
- `snapshots` entra em `searches.DEFAULTS` (busca salva e histórico lembram a caixa).
- Duplicatas: arquivo < 64 KiB lido uma vez (digest completo sai da cabeça);
  cabeça em ordem `(dev, caminho)`.

### 22.7 Testes novos

`test_revisao_fable_2026_09_21.py`, `test_cli_flags_2026_09_21.py`,
`test_nome_nao_utf8_2026_09_21.py`, `test_legado_mundo_2026_09_22.py`,
`test_nome_legado_2026_09_22.py`, `test_montagens_opcao_b_2026_09_22.py`, e
casos novos em `test_audit.py` (Ctrl+R, CSV, ejetar em passos). Todos são
scripts standalone: `python3 tests/<arquivo>.py`.

### 22.8 Em aberto

Ver §23.2 (inclui os caracteres invisíveis no nome e o `-i` sem efeito).

---

## 23. Handoff × código, e pendências conhecidas

Levantado na atualização deste documento (22/09/2026), lendo o código contra os
`HANDOFF_*.md` da raiz. **O código manda**; os handoffs são o histórico da decisão.

### 23.1 Onde o handoff ficou para trás

| Tema | Handoff dizia | Código hoje |
|---|---|---|
| Sonda de rede | `mount_alive` com `os.stat` numa thread daemon (HANDOFF_F9a) | fork + pipe (F1) e, desde 22/09, `stat` **+ `statvfs`** |
| EIO na sonda | "EIO fica vivo" (HANDOFF_F9_F1F2) | vale para o `stat`; no `statvfs`, EIO/ETIMEDOUT/erros de conexão = `broken_mount` |
| Quem é sondado | "roots locais passam direto" (HANDOFF_F9_Avanco) | desde a F12, expandidas de qualquer classe; gate também em `planejar_raizes` (inclusive `--one-fs`) |
| Destino de rede na cópia | capacidades de rede "entregues em julho" | até 21/09 `mount_ok` barrava NFS/CIFS/sshfs sob `/mnt` (exigia `/dev/*`) |
| MTP na busca | não citado | classificado como `gvfs` (`enumerate_default=False`) |
| Ejetar | "`gio mount -e` **ou** `udisksctl power-off`" (HANDOFF_F10) | PASSOS; sem gio, desmonta antes e tranca o LUKS (21/09) |
| Duplicatas, cabeça | lida "por grupo de tamanho" | fila única em ordem `(dev, path)`; < 64 KiB não é reaberto (21/09) |
| Decisão B (flock entre processos, `--no-serial-wait`) e `--no-index` | planejados | **não existem** em `lfs/*.py` |
| B6 (booleano × documentos) | exclusão mútua na GUI (auditoria de julho, §13) | revogado: o booleano combina com documentos; a trava saiu |

### 23.2 Pendências de código (pequenas, sem conserto ainda)

1. `-i/--ignore-case` é aceito pela CLI e **não faz nada** (`args.ignore_case` nunca
   é lido); o padrão já é insensível e `-s` prevalece.
2. `human_error(..., context="eject")` é chamado no ejetar, mas `_CLAUSES` não tem
   chave `eject` — a mensagem sai sem a cláusula de contexto.
3. `dupes.export` usa `,` (a busca usa `;`) e grava **direto** no destino, sem o
   `.sombrero-part` + `os.replace` que `searches.export` ganhou em 21/09.
4. `dupes.py` nunca escreve `stats["incompleto"]`: a barra das duplicatas só mostra
   `denied`, embora chame `resumo_incompleto`.
5. `{"warn":"mount_dead"}` do `--json` **não** traz `reason`, e o aviso de texto diz
   "not responding" também quando o motivo é `broken_mount`.
6. Comentários desatualizados: o de `_MOTIVOS_NO_PAINEL` (`app.py`) diz que "o
   booleano não emite eventos" (emite desde o H12); o de `MOTIVOS_GRAVES` cita o nome
   antigo `raiz_invalida` (a chave é `invalid_root`).
7. Com várias raízes em `--index`, a recusa de cobertura é raiz a raiz dentro do
   gerador: resultados de uma raiz íntegra anterior podem sair antes do exit 2.
8. No ramo `--one-fs`, montagens `autofs`/gvfs **são** sondadas (`stat` +
   `statvfs`) — não verificado se isso aciona o automount (na expansão elas não são
   tocadas).
9. ~~Caracteres invisíveis no nome~~ — **resolvido em 22/09** (§22.5): marcador
   visível `⟦RLO⟧`/`⟦ZWSP⟧`… em itálico com tooltip, e a busca por nome ignora
   esses caracteres (`_INVISIVEIS`, `nome_para_busca`, `_RX_INV_RUST`). ZWJ/ZWNJ
   (emoji compostos, persa/hindi) ficam intocados.
10. A docstring de `test_audit.py` ainda diz "ou via pytest" — não vale: os testes
    são scripts standalone (vários fazem `sys.exit()`).

### 23.3 Números citados só nos handoffs (não reverificados)

115/115 testes, SHAs de commit antigos, "Δ 0,0 MiB RSS" do soak, "CLI morre em
~3 s em 7/7" e "pai sai em 1,04 s" (HANDOFF_F9_F1F2). O "0,7 ms por sonda" do ramo
`--one-fs` é comentário de código, não remedido.
