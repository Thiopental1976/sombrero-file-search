# Sombrero File Search — Manual de uso

**Idioma:** **Português (BR)** · [English](MANUAL.md)

Buscador de arquivos **sem índice** e com resultados **ao vivo**, no espírito do
*Agent Ransack / FileLocator Pro* do Windows, mas nativo do Linux. O motor é o
**ripgrep** (`rg`) para conteúdo e o **fd** para nome, com fallback em Python puro
quando não há binários. Roda em qualquer distro.

Duas caras, o mesmo motor:

- **GUI** — `sombrero-file-search` (ou pelo menu, *Sombrero File Search*).
- **CLI** — `lfs`, feita para scripts e pipelines (`| xargs`, `| wc`, `| fzf`).

O que a GUI acha, a CLI acha igual: são a mesma engine.

---

## 1. Conceitos que valem para as duas interfaces

**Busca por NOME.** O termo é *contido* no nome: `rotina` acha `exames de rotina.txt`.
Se você usar curingas de glob (`*`, `?`, `[`), eles valem como digitados: `*.pdf`,
`IMG_????.jpg`, `[Rr]elatorio*`. Vários padrões separados por vírgula funcionam como
**OU**: `nota,*.txt` acha o que casa com qualquer um dos dois.

**Busca por CONTEÚDO.** Texto ou expressão regular que o arquivo precisa conter. O
resultado mostra a linha casada (a GUI destaca o trecho; a CLI imprime `arquivo:linha:texto`).

**Busca BOOLEANA de conteúdo.** `(A OR B) AND C NOT D`. Aceita as formas curtas
`|` `&` `!` e `"aspas"` para frases exatas. Precedência: `NOT` > `AND` > `OR`,
com parênteses para agrupar. Resolve por **conjuntos de arquivos** (usa `rg -l`
por termo e combina), então é rápida mesmo em acervos grandes.
Exemplo real: `(laudo OR relatório) AND paciente NOT rascunho`.

**Dentro de documentos.** Com o modo *docs* liga o [ripgrep-all](https://github.com/phiresky/ripgrep-all)
(`rga`), que busca **dentro** de PDF, docx, epub, odt e zip. Precisa do `rga`
instalado (o AppImage já traz; no `.deb`/`install.sh` é opcional).

**Filtros** (valem para nome, conteúdo e booleano):

| filtro | o que faz |
|---|---|
| tamanho mínimo | só arquivos ≥ N (`10M`, `1G`, `500K`, ou bytes) |
| últimos N dias | modificados nos últimos N dias |
| sensível a caixa | por padrão a busca **ignora** a caixa; ligue para diferenciar |
| palavra inteira | `nota` não casa `anotação` |
| ocultos | inclui arquivos/pastas que começam com `.` |
| respeitar `.gitignore` | pula o que o `.gitignore` esconde |
| não cruzar montagens | não desce para dentro de outros discos montados |
| regex no nome | trata o termo de nome como regex, não glob |

**Não cruzar montagens** (`--one-file-system`) é útil para buscar só no disco atual
sem entrar em pendrives/HDs externos montados debaixo da pasta.

---

## 2. A GUI

### O formulário
No topo você tem os campos **Nome** e **Conteúdo**, o campo **Em** (pastas onde
buscar, separadas por `;`) e os botões de filtro. **Buscar** dispara; **Cancelar**
interrompe (a busca é ao vivo — a tabela cresce enquanto roda).

### Resultados e preview
A tabela lista *Arquivo · Pasta · Tamanho · Modificado · Trechos*. Clique numa
coluna para ordenar. O painel de preview mostra:

- **Imagens** — miniatura.
- **Áudio/vídeo** — player com transporte (⏮ ▶/⏸ ⏭), barra de posição e navegação
  entre as mídias dos resultados.
- **Texto/código** — as linhas casadas, com o trecho **destacado**.

### Abas de busca *(F5)*
Cada aba é uma busca independente: seu próprio formulário e seus próprios resultados.
Trocar de aba devolve o formulário **daquela** busca — você nunca olha resultados de
uma busca com o formulário de outra na frente.

| atalho | ação |
|---|---|
| `Enter` | dispara a busca (de qualquer campo de busca) |
| `Esc` | cancela a busca em andamento; sem busca, limpa o filtro dos resultados |
| `↑` / `↓` | *(no campo de nome)* percorre para trás/frente o histórico de buscas |
| `Ctrl+F` | vai para a caixa de **filtro dos resultados** |
| `Ctrl+L` | vai para o campo de **pastas** (e o seleciona) |
| `F3` / `Shift+F3` | próximo / anterior match **dentro do preview** |
| `Ctrl+R` | repete a busca da aba |
| `Ctrl+N` | nova aba |
| `Ctrl+W` | fecha a aba (a última não fecha o programa — ela se esvazia) |
| `Ctrl+Enter` | busca numa **nova** aba (preserva a atual) |
| `Ctrl+S` / `Ctrl+E` | salva a busca atual / exporta os resultados |
| `Ctrl+T` | alterna tema claro / escuro |
| `Ctrl+C` / `Ctrl+Shift+C` | copia arquivo(s) selecionado(s) / copia caminho(s) |
| `Alt+Enter` | propriedades do resultado selecionado |

### Buscas salvas + histórico *(F5)*
No menu **Buscas ▾** (ao lado de *Discos*):

- **Salvar busca atual** (`Ctrl+S`) — guarda o formulário **inteiro** (não só o
  termo: pastas, filtros, tudo). Reabrir reproduz o resultado. Salvar com um nome
  que já existe **sobrescreve** no lugar.
- **Recentes** — as últimas buscas, sem duplicata (repetir sobe ao topo).
- **Remover salva** / **Limpar histórico**.

Abrir uma busca salva **abre outra aba** — não substitui a que você está vendo.

### Exportar resultados *(F5)*
**Buscas ▾ → Exportar** (`Ctrl+E`) grava o que está na tela, **na ordem em que
está** (se você ordenou por tamanho, o arquivo sai por tamanho):

- **CSV** — uma linha por trecho casado, com cabeçalho e separador `;` (abre no
  LibreOffice pt-BR com dois cliques). Colunas: `path;folder;name;size;modified;matches;line;text`.
- **JSON** — um objeto por **arquivo**, com os trechos aninhados (`jq -r '.[].path'`
  continua trivial).

O formato é escolhido pela extensão do arquivo que você nomear (`.json` → JSON,
qualquer outra → CSV).

### Copiar arquivos *(F7)*
Selecione resultados e:

- **Arraste** para outro aplicativo/gerenciador de arquivos, ou
- **Copie** para uma pasta de destino.

Antes de copiar, o LFS faz uma **pré-checagem do destino**: espaço livre, limite de
4 GiB do FAT32, nomes ilegais para o sistema de arquivos de destino, e se a montagem
está de fato montada. Em **pendrive/removível**, a escrita é feita **em ritmo**
(sincroniza a cada 16 MiB) para não sequestrar o cache do sistema e travar a máquina —
num disco interno isso não acontece, o kernel administra bem.

> **Nunca destrói a origem.** O LFS lê e copia; jamais move, renomeia ou apaga o
> arquivo de origem. Se a cópia for cancelada, o destino parcial é removido.

> **Dispositivos MTP (celular, media players).** A escrita via MTP montado (gvfs)
> tem limitações do próprio protocolo; para esses destinos, prefira o app do
> aparelho ou `gio copy`.

### Tema
`Ctrl+T` alterna claro/escuro; a preferência fica salva.

---

## 3. A CLI — `lfs`

```
lfs [opções] PASTA [PASTA ...]
```

Uma ou mais pastas como argumento posicional; as opções dizem **o que** procurar.
Sem nenhum critério, lista tudo sob a(s) pasta(s) (como um `ls -R` com filtros).

### Opções

| opção | forma longa | o que faz |
|---|---|---|
| `-n TERMO` | `--name` | nome CONTÉM o termo; globs (`* ? [`) valem como digitados; vários separados por vírgula = OU |
| `-c TEXTO` | `--content` | texto/regex que o arquivo deve conter |
| `-b EXPR` | `--bool` | busca booleana de conteúdo: `'(A OR B) AND C NOT D'` (`| & !` e aspas) |
| `-D` | `--docs` | busca DENTRO de documentos (PDF/docx/epub/zip…) via `rga` |
| | `--name-regex` | trata o termo de `-n` como **regex** (não glob) |
| | `--content-regex` | trata o termo de `-c` como regex |
| `-i` | `--ignore-case` | ignora a caixa (já é o padrão) |
| `-s` | `--case-sensitive` | diferencia maiúsculas/minúsculas |
| `-w` | `--word` | palavra inteira |
| | `--hidden` | inclui ocultos (`.`) |
| | `--gitignore` | respeita `.gitignore` |
| | `--one-fs` | não cruza pontos de montagem |
| | `--min-size N` | tamanho mínimo (`10M`, `1G`, ou bytes) |
| | `--days N` | modificado nos últimos N dias |
| `-0` | `--print0` | separa caminhos por NUL (para `xargs -0`) |
| `-l` | `--files-only` | só o caminho (sem as linhas casadas) |
| `-V` | `--version` | versão + licença |
| `-h` | `--help` | ajuda |

### Saída e pipelines
- Os **caminhos vão para o `stdout`**; o cabeçalho `# engine: …` e o rodapé
  `# N files · Ns` vão para o `stderr`. Ou seja, `2>/dev/null` te dá uma lista
  limpa, pronta para pipe.
- Com `-l` sai só o caminho; sem `-l`, as buscas de conteúdo saem no formato
  `caminho:linha:texto`.
- Com `-0` os caminhos vêm separados por NUL — o jeito seguro de passar nomes com
  espaços/quebras de linha para o `xargs -0`.

### Exemplos

```bash
# todos os PDFs sob ~/docs, só os caminhos
lfs ~/docs -n '*.pdf' -l 2>/dev/null

# arquivos que contêm "laudo" (mostra a linha)
lfs ~/docs -c laudo

# booleano dentro de documentos (PDF/docx…)
lfs ~/docs -D -b '(laudo OR relatório) AND paciente NOT rascunho' -l

# vídeos grandes modificados na última semana
lfs /mnt/DiscoL -n '*.mp4,*.mkv' --min-size 500M --days 7 -l 2>/dev/null

# alimentar outro comando com segurança (nomes com espaço)
lfs ~/fotos -n '*.jpg' -0 2>/dev/null | xargs -0 -n1 identify

# contar quantos arquivos batem
lfs ~/projetos -c 'TODO' -l 2>/dev/null | wc -l

# escolher interativamente
lfs ~ -n '*.md' -l 2>/dev/null | fzf
```

### Observações
- A busca é **insensível à caixa por padrão**; use `-s` quando a diferença importar.
- O **código de saída é 0** mesmo sem resultados (não use o exit code como "achou/
  não achou" — conte as linhas do `stdout`).
- `-n` usa glob por padrão; para expressão regular no nome, junte `--name-regex`
  (ex.: `--name-regex -n 'IMG_\d{4}\.jpg$'`).

---

## 4. Instalação (resumo)

| | quando usar | GUI |
|---|---|---|
| **AppImage** | qualquer distro, nada a instalar (Python + PySide6 e `rga` embutidos) | sim |
| **.deb** | Debian/Ubuntu/Mint, integrado ao apt | precisa de PySide6 |
| **install.sh** | qualquer distro, instala no `~`, sem root | usa o do sistema ou cria um venv |

Detalhes de cada caminho e das dependências opcionais (`rg`, `fd`, `rga`) estão no
`README_SOMBRERO_FILE_SEARCH.md`.

---

*Sombrero File Search — software livre sob GNU GPL v3 ou posterior. Sem índice, sem
serviço, sem nag: você busca, ele acha.*
