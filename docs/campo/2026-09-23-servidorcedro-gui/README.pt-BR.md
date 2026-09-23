# Teste de campo: a GUI do `.deb` 1.2.0 num servidor de 12 discos (2026-09-23)

*Versão canônica em inglês: [README.md](README.md). Em caso de divergência, vale a inglesa.*

Verificação do lado **gráfico** do pacote Debian no ServidorCedro (Linux Mint, i7-13700K, 12
discos montados), depois de a CLI já ter sido validada lá. Guardado porque a máquina é uma
bancada que nenhuma máquina de desenvolvimento reproduz: doze discos reais, uma sessão X11 viva
alcançada por RustDesk sobre Tailscale, e uma tela que muda de resolução durante a sessão.

## A bancada

- **Máquina:** ServidorCedro, Linux Mint, 24 threads, 12 discos montados sob `/mnt`
  (onze partições ext4 mais um mapper LUKS), um deles um NVMe Optane.
- **Instalação:** `sombrero-file-search` 1.2.0 pelo `.deb`; GUI no venv do usuário em
  `~/.local/share/sombrero-file-search/venv` (PySide6 6.11.1), já que Debian/Mint não
  empacotam PySide6. O `python3` do sistema não tem PySide6 — quem roda é o plano B do lançador.
- **Tela:** X11 no `:0`, alcançada por RustDesk sobre Tailscale. Modo nativo do monitor
  **3440x1440**; a sessão estava em **1920x1080**, reduzida de propósito para poupar banda
  num enlace Wi-Fi lento.

## Arquivos

| Arquivo | O quê |
|---|---|
| `1_montagens_e_menu.txt` | `classifica_montagens()` nos 12 discos reais, a montagem deixada de fora e o menu "Discos" como a GUI o monta |
| `2_tela_e_janelas.txt` | `xrandr` / `xdpyinfo` / `wmctrl`: modo nativo vs. tamanho real da raiz do X, e a geometria de cada janela aberta |
| `3_duas_versoes.txt` | 1.1.0 e 1.2.0 rodando ao mesmo tempo, offscreen e na tela real |

## O que passou

| Verificação | Resultado |
|---|---|
| `import PySide6`, `QApplication` | ok (venv, 6.11.1) |
| `MainWindow()`, `show()`, `processEvents()` | ok — título "Sombrero File Search" |
| Lançador do pacote `/usr/bin/sombrero-file-search` | sobe e fica no event loop |
| Busca por nome (6 logs) | 0,01 s |
| Busca por conteúdo (`classifica_montagens`) | 2 arquivos, 6 ocorrências, 0,02 s |
| Classificação de montagens | **12 discos locais, 0 falsos "rede"** |
| Menu "Discos" | 15 entradas: *All disks*, separador, *Home folder*, 12 discos |

A única montagem `/mnt/*` que o motor deixou de fora foi a `rustdesk-cliprdr-fs` — um FUSE
somente-leitura da área de transferência, corretamente não tratado como disco do usuário.

## Em aberto

### 1. A janela não é resgatada quando a resolução da tela encolhe

O `_fit_to_screen` (`lfs/app.py`) traz a janela de volta para dentro da área visível, e está
ligado ao primeiro `show()` e ao `QWindow.screenChanged` — ou seja, quando a janela muda de
**monitor**. Ele nunca é chamado quando o **mesmo** monitor muda de resolução, o que o Qt
sinaliza por `QScreen.geometryChanged` / `availableGeometryChanged`.

**Falha:** abrir a GUI em 3440x1440 com a janela mais à direita e deixar a sessão cair para
1920x1080. A janela mantém as coordenadas, fica fora da raiz do X e continua viva e invisível —
e reabrir não ajuda, porque nada a reposiciona. Nesta máquina esse encolhimento é rotina: a
resolução é reduzida de propósito quando o enlace está lento.

Prova viva na mesma captura: a janela do RustDesk está em `x=3240` numa raiz de 1920 de largura.

O `_fit_geometry` já é puro e coberto por teste; o que está em questão é apenas *quando* ele é
chamado. Se o programa deve mover uma janela que o usuário pode ter colocado ali de propósito é
decisão de desenho, **pendente do autor** — nada implementado.

### 2. O menu de discos mostra o rótulo do sistema de arquivos, não o ponto de montagem

`/mnt/CB69B31B5CC6C5D7` (7,3 TB) aparece como **"UnidadeOptane"**, rótulo remanescente de uma
vida anterior do disco, enquanto o Optane de verdade (`/mnt/optane`, 13,4 GB) aparece como
"OptaneCache". O SFS está reportando fielmente o dado do próprio disco, mas a entrada não bate
com o nome que o usuário usa — e as duas parecem o mesmo dispositivo. Ou se corrige o rótulo no
disco, ou o menu mostra rótulo **e** ponto de montagem quando divergem. Decisão do autor.

## Nota sobre o sintoma relatado

O sintoma que abriu este teste — "uma segunda instância não renderizava com uma versão diferente
aberta" — **não se reproduziu**, nem offscreen nem na tela real: as duas versões rodaram lado a
lado, as duas janelas visíveis, `config.json` idêntico byte a byte antes e depois. Não existe
mecanismo de instância única no código (sem `QLocalServer`, `QSharedMemory` ou lockfile). A
evidência aponta o item 1 acima como a causa real: a janela estava renderizando, fora da área
visível.
