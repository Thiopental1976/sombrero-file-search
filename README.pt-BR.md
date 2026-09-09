<div align="center">

<img src="assets/icon_128.png" width="96" alt="Sombrero File Search">

# Sombrero File Search

**Busca de arquivos nativa para Linux — por nome, por conteúdo, booleana e dentro de documentos.**
*Ao vivo, sem índice e honesta: quando não conseguiu olhar em algum lugar, ela diz.*

![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab)
![PySide6](https://img.shields.io/badge/GUI-PySide6-41cd52)
![ripgrep](https://img.shields.io/badge/engine-ripgrep%20%2B%20fd-orange)
![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)
![Interface](https://img.shields.io/badge/interface-English%20(default)%20%2B%20Portugu%C3%AAs-informational)

[English](README.md) · **Português (BR)**

<img src="assets/demo.gif" width="960" alt="Busca por nome, depois por conteúdo dentro de PDF e ODT, depois com expressão booleana">

<sub>Nome → conteúdo **dentro de documentos** (PDF/ODT) → expressão booleana, ao vivo, sem índice.</sub>

</div>

---

## O que é

Um buscador de arquivos **sem índice** e com resultados **ao vivo**, no espírito do
*Agent Ransack / FileLocator Pro* do Windows, nativo do Linux e portátil entre distros. Os
motores são o **ripgrep** (`rg`) para conteúdo e o **fd** para nomes; sem eles, cai num
fallback em Python puro, então roda em qualquer lugar. Os buscadores do Windows são inúteis no
Linux (leem a MFT/USN do NTFS, que não existe aqui); este projeto refaz o trabalho nativamente.

Foi construído em, e para, um servidor doméstico com uma dúzia de discos mecânicos, drives
SMR em USB, montagens de rede que às vezes morrem e acervos de centenas de milhares de
arquivos. Tudo abaixo que soa como política foi **medido** lá, com cache frio, e os números
estão neste README.

> 📖 **Manual completo:** [MANUAL.pt-BR.md](MANUAL.pt-BR.md) (Português) · [MANUAL.md](MANUAL.md) (English) — uso da GUI e cada opção da CLI.

## A tese: honestidade acima de completude

Uma ferramenta de busca tem um jeito de mentir que é pior que qualquer bug: devolver
**"0 resultados"** quando nunca olhou de fato. Uma pasta que negou leitura, um motor que
engasgou numa flag, um disco que não estava montado, um NAS que parou de responder, uma raiz
digitada errada — cada um desses casos parecia exatamente *"o arquivo não está aí"*. O usuário
conclui que o arquivo não existe, e a conclusão está errada.

O Sombrero encaminha **toda perda de completude por um canal único** (`stats['incompleto']`
no motor). O que acontece depois deriva desse canal, então um tipo novo de perda, anotado em
qualquer lugar, aparece em todo lugar de graça:

| onde | o que você vê |
|---|---|
| barra de status da GUI | `⚠ 0 resultado(s) · ⚠ incompleto: sem permissão (×25): diretórios que negaram leitura` — o ícone vira **⚠** quando o resultado pode estar *errado*, não só curto |
| painel de narrativa da GUI | uma linha por raiz, ao vivo: varrendo / concluída (N achados) / **pulada** com o motivo (montagem morta, pasta não encontrada, disco não montado, não varrida por padrão) |
| CLI, stderr | `# incomplete: invalid location in /mnt/naoexiste: path does not exist (disk unmounted? typo?)` e, quando é grave, `#        results are INCOMPLETE — this is not 'nothing was found'` |
| `--json` | `{"warn"\|"error": "incomplete", "reason": "<id>", "where": "<caminho>", "detail": "...", "count": N}` no mesmo fluxo dos resultados |
| código de saída | **0** achou · **1** nada · **2** o resultado pode estar errado — estilo grep |

Os identificadores de `reason` são contrato para scripts (estáveis, em inglês):

| reason | grave? | significado |
|---|---|---|
| `permission_denied` | não | diretórios ou arquivos que negaram leitura |
| `read_error` | não | o motor não conseguiu ler algo (erro de I/O, não é diretório…) |
| `stat_failed` | não | o motor listou ou casou um arquivo que sumiu antes do `stat` |
| `truncated` | não | parou no teto interno de resultados; pode haver mais |
| `snapshots_skipped` | não | uma árvore de snapshot do sistema (Timeshift, snapper, ZFS, shadow copies do Samba) não foi varrida — `--snapshots` / "incluir snapshots" para incluir |
| `dead_mount` | não | uma montagem sob a busca não respondeu, ou respondeu quebrada (ENOTCONN/ESTALE), e foi pulada |
| `empty_mountpoint` | não | a raiz é uma pasta vazia onde discos são montados (`/mnt/X`, `/media/<user>/X`) e não é ponto de montagem — o disco está montado? |
| `mount_not_entered` | não | uma montagem gvfs (celular) ou autofs sob a raiz não foi varrida por padrão; busque pelo caminho dela |
| `batch_failed` | não | (booleana) um lote de arquivos não pôde ser lido |
| `interrupted` | não | um disco não respondeu ao cancelamento a tempo; as perdas dele não foram contadas |
| `engine_failed` | **sim** | rg/fd saíram com erro (uma flag que a versão antiga não conhece, por exemplo) |
| `engine_missing` | **sim** | rg/fd não puderam ser executados; o fallback Python *não* é equivalente (não lê UTF-16 com BOM) |
| `invalid_root` | **sim** | a raiz não existe, ou é um arquivo (a busca recebe pastas) |
| `not_mounted` | **sim** | a raiz está no `/etc/fstab` e não está montada — o disco deveria estar ali e não está |
| `disk_failed` | **sim** | o worker de um disco quebrou |

*Grave* quer dizer que o resultado pode estar **errado**, não apenas incompleto: só motivos
graves mudam o código de saída, então um script que faz `sfs ... || echo "não achei"` não passa
a falhar porque uma pasta do sistema negou leitura.

Isso não é slogan; é um teste. `tests/test_honestidade.py` provoca cada perda de verdade
(chmod 000, uma flag inválida injetada na linha de comando do motor, um fstab falso, uma raiz
que é arquivo…) em **cada backend** — fd/nome, rg/conteúdo, Python/nome, Python/conteúdo,
booleano, booleano sem rg — e exige o motivo certo no funil. **6 backends × 11 perdas,
53 células aplicáveis, todas verdes.** A tabela é uma catraca nos dois sentidos: falha se uma
célula verde regride *e* se uma lacuna conhecida, pinada, passa a funcionar sem ser despinada.

## Consciente do disco, e medido

A segunda tese é que uma busca em muitos discos tem de respeitar o que cada disco consegue
fazer. A regra da casa é *um cabeçote mecânico, um processo* — e cada regra abaixo foi medida
com cache frio (`drop_caches`) numa máquina quiescida, em setembro de 2026, no hardware
nomeado. Número que não foi medido não está neste README.

**Partição por disco físico.** As raízes de uma busca são agrupadas pelo disco físico por trás
delas (atravessando LVM/LUKS, para que subvolumes btrfs e duas partições do mesmo prato não
virem dois processos brigando por um cabeçote). Cada grupo ganha seu próprio processo `fd`/`rg`
e sua própria thread, e os resultados chegam conforme cada disco termina. Num acervo de 10
montagens:

| | total | quando 9 dos 10 discos já tinham terminado |
|---|---|---|
| um processo só, 24 threads (antes) | 1 094 s | 1 094 s — tudo chegava no fim |
| um processo por disco + pool por classe (agora) | **80 s** | 45 s |

**Pool de threads por classe de disco e por operação.** O pool de cada processo segue a classe
do disco (`/sys/block/<disco>/queue/rotational`, resolvido através do device mapper) e se a
busca lê *nomes* ou *conteúdo*:

| disco / operação | 1 thread | 4 threads | pool cheio (24) | política |
|---|---|---|---|---|
| NVMe, busca por nome (`/usr`, 92 680 achados) | 5,2 s | 1,5 s | **0,5 s** | SSD: pool cheio |
| SMR 8 TB, busca por **nome** (1,15 M inodes) | **38 s** | — | 48 s | rotacional, nomes: 1 thread |
| SMR 8 TB, busca por **conteúdo** (rg, 25 k arquivos) | 36 s | 30 s | **29 s** | rotacional, conteúdo: pool cheio |
| HD USB, duas raízes no mesmo prato (100 k inodes) | 1 processo 4,8 s · 2 processos 5,5 s · 2 processos com pool cheio 6,4 s | | | um processo por prato |

Busca por nome é metadado, disposto sequencialmente no prato: uma thread ganha e o pool cheio
custa 21 %. Busca por conteúdo abre cada arquivo, e aí o disco reordena leituras quando há
vários pedidos em voo: estrangular o `rg` só custava 17 %. Estrangular o SSD custaria
**12,5×**. Uma árvore pequena não distingue essas políticas — é preciso volume para o cabeçote
começar a passear, e foi por isso que a primeira rodada de medição, num disco de 175 k inodes,
não mostrou sinal nenhum.

Um número que vale saber antes de buscar *conteúdo* num acervo de vídeo: o disco SMR de 8 TB
acima, inteiro, com uma thread, **não tinha terminado depois de uma hora**. Busca por conteúdo
num disco de binários grandes é um seek por arquivo; isso é física, não bug, e a barra de status
vai ser honesta sobre até onde chegou.

**Árvores de snapshot são podadas por padrão.** Um disco do acervo hospedava cinco snapshots do
Timeshift: 2,4 M inodes contra 175 k no disco seguinte, e ele sozinho levava 1 264 s. Com a
poda, **95 s, resultado idêntico, 13,3× mais rápido**. A poda é *dita* (`snapshots_skipped`, uma
caixa na GUI, `--snapshots` na CLI) e se desliga sozinha quando você aponta a busca *para dentro*
de um snapshot — ali era onde você queria olhar.

## Montagens, mortas e vivas

Buscar em `/` ou `/mnt` quer dizer *tudo que mora ali embaixo*, rede e discos locais
igualmente. Cada montagem sob uma raiz vira uma raiz própria, passa pelo gate uma a uma, ganha
seu processo, e a raiz-mãe caminha com `--one-file-system` para nada ser visitado duas vezes.
Pseudo-sistemas do kernel (`/proc`, `/sys`, `/dev`…) ficam de fora com uma nota; um bind mount
do mesmo sistema de arquivos não é varrido duas vezes; `--one-fs` na CLI (ou "1 disco" na GUI)
desliga a expansão, porque aí você pediu uma pasta só.

**O gate.** Um hard mount NFS cujo servidor caiu congela o `stat()` em estado D
ininterruptível — nem `kill` resolve. Antes de qualquer motor descer numa montagem, o Sombrero a
sonda a partir de um **processo filho descartável** com timeout (uma thread presa impediria o
programa inteiro de sair; um filho preso é reparentado ao init e abandonado). Montagem que não
responde, ou responde quebrada, é pulada com uma linha visível — e é **excluída da linha de
comando de todo motor**, porque com `--one-file-system` o walker ainda precisa fazer `stat()`
no ponto de montagem para comparar dispositivos, e essa é exatamente a chamada que trava. Cada
motor ancora a exclusão do seu jeito, medido: `fd --exclude '/rel'` ancora na primeira raiz do
processo (então raiz com montagem morta embaixo ganha processo próprio); o `rg` só ancora
`!**/caminho/absoluto`; o walker Python poda por caminho.

**Pontos de montagem vazios.** O caso mais realista de "disco não montado" é uma pasta que
*existe* e está vazia. Se está declarada no `/etc/fstab`, é fato (`not_mounted`, grave). Se só
mora onde discos são montados, é indício (`empty_mountpoint`, não grave): a busca segue, e a
barra pergunta se o disco está montado.

`gvfs` (celulares, câmeras) e gatilhos `autofs` ficam **fora** do "buscar em tudo" — acordar
todo automount da casa não era o que você quis dizer — mas o funil diz isso, com o caminho para
buscar explicitamente.

## Recursos

- 🔎 **Nome + conteúdo** — glob (`*.py`) ou regex, texto ou regex, com realce no preview.
- 🧩 **Busca booleana** — `(laudo OR relatorio) AND paciente NOT rascunho`; também `| & !` e
  `"frases entre aspas"`. Precedência `NOT > AND > OR`, parênteses. O `AND` restringe o segundo
  termo aos arquivos que o primeiro achou; termos `OR` independentes rodam em paralelo
  (`LFS_WORKERS`, padrão 3).
- 📄 **Dentro de documentos** — PDF, docx, epub, odt, zip via [ripgrep-all](https://github.com/phiresky/ripgrep-all) (opcional).
- 🎬 **Preview de mídia** — miniaturas e um player de áudio/vídeo com controles de transporte.
- 🗂️ **Abas de busca, buscas salvas, histórico, exportação** para CSV/JSON, tema claro/escuro.
- 📁 **Copiar arquivos** — nunca move nem apaga a origem; pré-checagem do destino (espaço livre,
  limites do FAT32, nomes ilegais por sistema de arquivos) e **escrita ritmada** em mídia
  removível e de rede, para uma cópia de 300 GB não engolir o cache do sistema.
- 🔁 **Localizador de duplicatas** — acha, mostra e exporta grupos byte-idênticos. **Nunca
  apaga.** Decidir qual cópia morre é do humano, no gerenciador de arquivos dele, com os caminhos
  na frente; um botão de apagar seria o fim desse argumento.
- 💻 **CLI equivalente** — mesmo motor, `--print0` para pipelines, `--json` para automação,
  `--nice-io` para cron num servidor ocupado, `--index` (só nome) para se apoiar no `plocate`
  quando você pede explicitamente — recusa quando o índice tem buracos, e cada achado é
  verificado ao vivo.

## Instalação

| | quando usar | GUI? |
|---|---|---|
| **AppImage** | qualquer distro, nada a instalar | sim — Python e PySide6 embutidos |
| **.deb** | Debian/Ubuntu/Mint | precisa do PySide6 (`sombrero-file-search --setup-gui` cria um venv no seu home) |
| **install.sh** | qualquer distro, instala em `~/.local`, sem root, distros imutáveis incluídas | sim |

```bash
# AppImage
chmod +x Sombrero_File_Search-*.AppImage && ./Sombrero_File_Search-*.AppImage
./Sombrero_File_Search-*.AppImage --cli ~/docs -n '*.pdf'    # exatamente a mesma CLI

# .deb
sudo apt install ./sombrero-file-search_*_all.deb

# a partir do código
git clone https://github.com/Thiopental1976/sombrero-file-search.git
cd sombrero-file-search && ./install.sh
```

O `.deb` é deliberadamente magro: `Depends: python3`, com `ripgrep` e `fd-find` como
*Recommends* — existe um fallback em Python puro, então declará-los obrigatórios seria mentira.
Não há Flatpak de propósito: este programa existe para varrer o disco inteiro, e o sandbox é o
modelo errado para isso.

## CLI

```bash
sfs ~/projetos -n '*.py' -c "def main"        # nome + conteúdo   (lfs é apelido)
sfs ~/docs -c laudo --docs                    # dentro de PDF/docx/epub
sfs ~/notas -b '(laudo OR relatorio) AND paciente' # booleana
sfs /dados -c erro -l --print0 | xargs -0 …   # pipeline
sfs /mnt -n '*.iso' --json                    # NDJSON, um objeto por achado + avisos
sfs / -n laudo --snapshots                    # inclui árvores de snapshot
```

`--json` emite um objeto por achado (`path`, `size`, `mtime`, `is_dir`, `nmatch`, `lines[]`)
e, no mesmo fluxo, `{"warn":"incomplete",…}` / `{"error":"incomplete",…}` com a tabela de
`reason` acima, `{"warn":"mount_dead",…}`, `{"warn":"denied",…}` e
`{"error":"boolean_expression",…}` para expressão malformada. Código de saída: 0 / 1 / 2.

## Paridade `rg` ↔ fallback Python

O fallback devolve o mesmo resultado do ripgrep na esmagadora maioria dos casos; a bateria de
paridade roda 500 expressões booleanas aleatórias × 2 000 arquivos e exige zero divergência. As
diferenças que existem são documentadas de propósito e pinadas por teste: `nmatch` conta
ocorrências no `rg` e linhas casadas no fallback; UTF-16/UTF-32 com BOM só o `rg` acha (por isso
`engine_missing` é grave); CR solto fora de CRLF segmenta linhas de forma diferente (arquivos
pré-OS X, não perseguido). CRLF é normalizado dos dois lados.

## Arquitetura

```
lfs/engine.py     # núcleo sem Qt: Query/Match, backends rg (conteúdo) / fd (nome), fallback Python,
                  # o funil de completude, o gate de montagens, a expansão de raízes, a partição por disco
lfs/boolean.py    # busca booleana: tokenizador → AST → conjuntos de arquivos, mesmo funil e gate
lfs/disks.py      # fatos sobre discos e montagens: classe, rotational, fstab, sonda de vida, capacidades
lfs/dupes.py      # localizador de duplicatas (código próprio; sem função de apagar, nem deve ganhar)
lfs/indexed.py    # --index: plocate com checagem de cobertura e verificação ao vivo
lfs/app.py        # GUI PySide6: formulário, tabela ao vivo, painel de narrativa, preview, cópia, duplicatas
lfs/cli.py        # CLI (mesmo núcleo)
lfs/fileops.py    # cópia não destrutiva: nunca move, renomeia ou apaga
lfs/i18n.py       # o inglês é a fonte; pt-BR é uma tabela indexada pela string em inglês
tests/            # test_audit.py (125 testes), test_honestidade.py (a tabela),
                  # test_parity_rg_python.py, test_paralelo_por_disco.py, test_topologias.py…
```

```bash
python3 tests/test_audit.py          # ~1 min; os testes de GUI precisam do PySide6 (offscreen)
python3 tests/test_honestidade.py    # a tabela de honestidade, ~1 min
./packaging/build_deb.sh             # ~3 s
./packaging/build_appimage.sh        # ~10 min na primeira vez
```

## Idioma da interface

O inglês é o idioma-fonte; a GUI segue o locale do sistema e cai para o inglês em qualquer
locale que não seja português. A CLI é só em inglês. `SFS_LANG=en|pt` força.

## Licença

**GNU GPL v3 ou posterior** ([LICENSE](LICENSE)) — `SPDX-License-Identifier: GPL-3.0-or-later`.
Copyright (C) 2026 Rodrigo Toledo. Distribuído SEM QUALQUER GARANTIA.
