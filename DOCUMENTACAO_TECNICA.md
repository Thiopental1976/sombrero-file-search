# Linux File Search — Documentação Técnica

> Documento de referência para **avaliação e depuração** do projeto. Descreve arquitetura,
> cada módulo, o fluxo de dados, o modelo de concorrência, a gramática da busca booleana,
> o modo documentos, o player de mídia, o sistema de temas e a matriz de dependências por distro.
>
> **Versão do documento:** 2026-07-14 · **Autor:** Rodrigo Toledo (com Andrômeda/Claude)
> **Licença:** aberta e gratuita (baseada na MIT, sem direito de revenda)

---

## 1. Visão geral

**Linux File Search** é um buscador de arquivos **nativo para Linux**, sem índice, com
resultados **ao vivo**, no espírito do *Agent Ransack / FileLocator Pro* do Windows. Ele busca
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

---

## 2. Estrutura de arquivos

```
linux_file_search/
├── lfs/
│   ├── engine.py      # NÚCLEO sem Qt: Query/Match, backends rg/fd, fallback Python
│   ├── boolean.py     # Busca booleana: tokenizer → AST → conjuntos de arquivos
│   ├── cli.py         # Interface de linha de comando (mesma engine)
│   └── app.py         # GUI PySide6: form, tabela ao vivo, preview texto/mídia, temas
├── assets/
│   ├── icon.svg       # ícone-fonte (256×256, gradiente + lupa)
│   └── icon_{48,64,128,256}.png, icon.png   # rasterizações (via QtSvg)
├── install.sh         # instalador universal multi-distro
├── linux-file-search  # lançador (aponta pro venv com PySide6)
├── README.md          # documentação de usuário
├── DOCUMENTACAO_TECNICA.md  # este arquivo
├── LICENSE            # MIT
├── requirements.txt   # PySide6 (motores são pacotes de sistema)
└── .gitignore
```

---

## 3. Núcleo — `lfs/engine.py`

Módulo sem dependência de Qt. Define os tipos de dados, detecta binários e implementa quatro
iteradores de busca (dois por nome, dois por conteúdo) mais a API pública `search()`.

### 3.1 Detecção de binários

```python
_APP_BIN = ~/.local/share/linux-file-search/bin   # binários empacotados (rga/pandoc)
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

**`Match`** (dataclass) — um resultado: `path`, `size`, `mtime`, `is_dir`, `lines:
list[(lineno, texto)]` (até 200), `nmatch` (nº de casamentos).

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

`argparse` sobre a mesma engine. Principais flags:

| Flag | Efeito |
|---|---|
| `path...` | pasta(s) (posicional, 1+) |
| `-n/--name` | globs separados por vírgula (`'*.py,*.txt'`) |
| `-c/--content` | texto/regex a conter |
| `-b/--bool EXPR` | busca booleana |
| `-D/--docs` | busca dentro de documentos (rga) |
| `--name-regex`, `--content-regex` | tratar como regex |
| `-s/--case-sensitive`, `-w/--word` | caixa / palavra inteira |
| `--hidden`, `--gitignore`, `--one-fs` | ocultos / respeitar .gitignore / não cruzar mounts |
| `--min-size 10M`, `--days N` | filtros de tamanho / data |
| `-l/--files-only` | só caminhos |
| `-0/--print0` | separador NUL (para `xargs -0`) |

Imprime o status do motor em `stderr` (`# motor: rg=… fd=… rga=…`) e avisa se `--docs` foi
pedido sem `rga`. Erros de expressão booleana saem com **exit code 2**.

Exemplos:
```bash
lfs ~/projetos -n '*.py' -c "def main"
lfs ~/docs -c laudo --docs
lfs ~/notas -b '(nota OR laudo) AND paciente NOT rascunho'
lfs /dados -c erro -l --print0 | xargs -0 du -h
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
Esc → cancel_search (flag) ; Ctrl+L foca conteúdo ; Ctrl+T alterna tema
```

A UI thread nunca faz I/O de busca. O `_cancel` é lido pelo iterador entre itens; processos
externos recebem `terminate()`.

### 6.3 Sistema de temas

- `THEMES = {"dark": {...}, "light": {...}}` — paletas com ~15 chaves (bg0..bg3, alt, border,
  txt, muted, accent, on_accent, green/amber/red…).
- `_STYLE_TMPL` — folha de estilo Qt com placeholders `{chave}`; `build_style(pal)` faz
  `.format(**pal)`.
- `apply_theme(name)` aplica o stylesheet, ajusta status e botão, e chama `_refresh_badges`.
- `toggle_theme()` inverte e **persiste** em `~/.config/linux-file-search/config.json`
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
`~/.local/share/linux-file-search/`, cria lançadores `linux-file-search` (GUI) e `lfs` (CLI),
ícones hicolor e atalho `.desktop`. Não precisa de root para o app (tudo em `~/.local`).

### 9.2 Manual

```bash
sudo apt install ripgrep fd-find poppler-utils   # exemplo Debian
pip install PySide6
python3 lfs/app.py     # GUI    |    python3 lfs/cli.py --help    # CLI
```

---

## 10. Testes e depuração

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

- **F5 — Conforto**: abas simultâneas, buscas salvas/histórico, export CSV/JSON, mais atalhos.
- **F6 — Portabilidade**: empacotar `.deb` e **AppImage** (PySide6 embutido; evitar Flatpak, cuja
  sandbox brigaria com ler o filesystem inteiro).
- Contagem de "inacessíveis" (permission-denied) no rodapé — hoje `stderr` é descartado.
- `rga` pré-compilado só para `x86_64`; em outras arquiteturas, instalar pelo gerenciador.

---

## 12. Referência rápida de símbolos

| Módulo | Símbolos-chave |
|---|---|
| `engine.py` | `Query`, `Match`, `search`, `engine_info`, `_which`, `_iter_content_rg`, `_iter_names_fd`, `_iter_content_python`, `_iter_names_python`, `_passes_meta`, `_name_matcher` |
| `boolean.py` | `parse`, `tokenize`, `search_boolean`, `positive_terms`, `_eval`, `_files_with_term`, `_universe`, `_display_lines`, `BooleanError`, `Term/Not/And/Or` |
| `cli.py` | `main` (argparse) |
| `app.py` | `MainWindow`, `SearchWorker`, `ResultModel`, `THEMES`, `build_style`, `media_kind`, `_build_preview`, `_show_media`, `_nav_media`, `apply_theme` |
