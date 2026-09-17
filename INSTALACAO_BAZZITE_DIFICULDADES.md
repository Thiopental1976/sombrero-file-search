# Instalação do Sombrero File Search em distros imutáveis (Bazzite / Fedora Atomic)

**Relatório de campo — 30/07/2026**
Ambiente: Bazzite 44.20260721.0 (Silverblue), GNOME/Wayland, x86_64, ASUS GL553VD.
Commit testado: `907085f` (25/07/2026), branch `main`.

---

## Resumo executivo

O `install.sh` **não completa** numa instalação limpa de Bazzite. Ele não falha com
erro — ele **trava indefinidamente na primeira dependência** e abre uma janela de
navegador na tela do usuário. Nada é instalado.

A causa não é o script estar errado: é que ele assume uma premissa que vale em
Debian/Fedora/Arch tradicionais e **deixa de valer em distros de imagem imutável** —
"existir um gerenciador de pacotes no PATH significa que dá para instalar pacotes".
No Bazzite, `dnf` existe, está no PATH, e é uma armadilha.

Três problemas independentes, em ordem de gravidade:

| # | Problema | Efeito | Gravidade |
|---|---|---|---|
| 1 | `dnf` é um *stub* que abre o navegador e bloqueia | **Instalador trava para sempre** | 🔴 Bloqueador |
| 2 | `/usr` somente-leitura | Nenhum pacote de sistema instalável sem reboot | 🟠 Estrutural |
| 3 | `rg` e `fd` ausentes numa instalação limpa | Os **dois motores** do app caem no fallback Python | 🟠 Desempenho |

Todos têm solução, e ela já existe no próprio script — só não está sendo aplicada
a estes pacotes. Detalhes na seção *Correções propostas*.

---

## 1. 🔴 O `dnf` do Bazzite trava o instalador

### O que aconteceu

```
[1/5] Dependências de busca (ripgrep, fd, poppler)
Instalando ripgrep (via dnf)…
ERROR: Fedora Atomic images utilize rpm-ostree instead (and is discouraged to use).
Please, read our documentation
https://docs.bazzite.gg/Installing_and_Managing_Software/
```

…e o script **parou aqui**. Seis minutos depois ainda estava vivo, sem consumir CPU,
sem avançar. Simultaneamente, **uma janela do Firefox abriu sozinha** na área de
trabalho, exibindo a documentação do Bazzite. O usuário não pediu nada disso.

### Por que trava

`/usr/sbin/dnf` no Bazzite não é o dnf — é um invólucro de 19 linhas:

```bash
# Show the error if we attempt to use the install/uninstall commands
for arg in "$@"; do
    if [[ $arg == "install" || $arg == "in" || $arg == "remove" || $arg == "rm" ]]; then
        echo -e "ERROR: Fedora Atomic images utilize rpm-ostree instead..." >&2
        ${SUDO_USER:+sudo -u $SUDO_USER dbus-launch} bash -lc 'xdg-open "https://docs.bazzite.gg/..."'
        exit 1
    fi
done
exec /usr/bin/dnf5 "$@"     # qualquer outro subcomando passa adiante
```

A linha do `xdg-open` é executada **de forma síncrona**. Em um terminal interativo
ela retorna rápido; chamada de dentro de um script com a saída redirecionada, o
`dbus-launch` deixa um daemon segurando o descritor de arquivo herdado e o `dnf`
nunca retorna. O `install.sh` fica esperando um comando que jamais termina.

### Condições exatas do gatilho — importam para a correção

- Só dispara em `install`, `in`, `remove`, `rm`. **Consultas passam** para o `dnf5`
  real e funcionam normalmente (`dnf info`, `dnf search`). Isso é relevante: o
  `pkg_exists()` do instalador, que usa `dnf -q info`, **é seguro**.
- O navegador só é aberto quando **`SUDO_USER` está definido**, isto é, quando o dnf
  é chamado via `sudo`. E o `install.sh` monta `INSTALL="sudo dnf install -y"` —
  cai exatamente no caminho que trava.
- Não há *timeout* em lugar nenhum da cadeia. O travamento é permanente.

### Onde o script é vulnerável

Dois pontos, ambos via `$INSTALL`:

1. **`sys_install()`** — `[1/5]`, para `ripgrep`, `fd`, `poppler`.
   Só é alcançado se o binário estiver ausente (o `has "$probe"` retorna cedo se
   já existir). Numa Bazzite limpa, `rg` e `fd` **estão** ausentes → trava aqui.
2. **`setup_python()`** — `[4/5]`, na tentativa de instalar `python3-pyside6` pelo
   sistema. O `ask()` devolve "sim" automaticamente fora de TTY, então o único
   obstáculo entre o script e o `$INSTALL` é o `pkg_exists()`.

   ⚠️ **Neste Bazzite o segundo travamento NÃO disparou — por acidente.**
   `dnf -q info python3-pyside6` retorna **1**, porque a imagem não traz os metadados
   dos repositórios Fedora. O `! pkg_exists` vira verdadeiro, o script registra
   *"não existe no repositório desta distro — usando venv"* e desvia para o venv sem
   nunca chamar o gerenciador.

   O motivo alegado está errado — o pacote **existe** no Fedora; o que falta são os
   metadados locais — mas o desvio salvou a instalação. **É uma salvaguarda
   acidental, não um comportamento projetado.** Em qualquer sistema imutável com
   repositórios populados (ou nesta mesma máquina após um `dnf makecache`), o
   `pkg_exists` retornaria 0 e o script travaria aqui.

Ou seja: **corrigir só o `[1/5]` não basta**, e a correção 5.1 segue necessária
mesmo tendo esta instalação concluído sem ela.

---

## 2. 🟠 `/usr` é somente-leitura — o modelo de instalação muda

```
$ touch /usr/lib/systemd/system-sleep/.teste
touch: cannot touch ...: Read-only file system
```

Em Fedora Atomic, pacotes de sistema entram por `rpm-ostree install`, que **monta uma
nova imagem e exige reboot**. Isso é incompatível com a promessa de um instalador
de uma passada só: não dá para instalar `ripgrep` e usá-lo na linha seguinte.

Marcador confiável para detectar o caso: **o arquivo `/run/ostree-booted`** existe.
É mais robusto que procurar `rpm-ostree` no PATH (que também existe em sistemas
mutáveis com o pacote instalado).

A boa notícia: **o app não precisa de root para nada.** O destino `~/.local` já é
o padrão do script, e funciona perfeitamente aqui.

---

## 3. 🟠 Numa Bazzite limpa faltam os DOIS motores

| Componente | Presente? | Papel | Sem ele |
|---|---|---|---|
| `ripgrep` (`rg`) | ❌ **ausente** | busca de conteúdo | fallback Python puro |
| `fd` | ❌ **ausente** | busca por nome | fallback Python puro |
| `pdftotext` (poppler) | ✅ presente | texto de PDF | — |
| `libxcb-cursor` | ✅ presente | plugin xcb do Qt | GUI não abriria em X11 |
| `ensurepip` | ✅ presente | criação de venv | venv impossível |
| PySide6 | ❌ ausente | GUI | resolvido por venv |

`rpm -q ripgrep` → *package ripgrep is not installed*. Bazzite é uma imagem de jogos;
nem `ripgrep` nem `fd` fazem parte dela.

Isso é grave para este projeto em particular: o Sombrero é vendido como *"powered by
ripgrep/fd with a proven pure-Python fallback"*, e o alvo declarado são **acervos
grandes em discos SMR e USB**. Cair no fallback é justamente o cenário em que o
fallback dói mais.

### ⚠️ Armadilha de detecção: `command -v` enxerga funções de shell

Vale registrar porque custou tempo no diagnóstico. Uma sondagem manual indicou
`ripgrep` presente:

```
$ command -v rg
rg
```

Repare que a saída **não é um caminho**. `rg` era uma **função de shell** injetada no
perfil do usuário pelo Claude Code, que redireciona para o ripgrep embutido no
próprio binário `claude`. Não havia binário nenhum.

O `has()` do instalador usa `command -v`, que **casa com funções e aliases**. O script
não foi enganado nesta execução (roda em shell próprio, sem o perfil interativo), mas
a mesma sondagem feita à mão, ou um instalador executado com `source`, seria.

**Correção defensiva:** usar `type -P` em vez de `command -v` — `type -P` procura
**apenas executáveis no PATH**, ignorando funções, aliases e builtins.

```bash
has(){ type -P "$1" >/dev/null 2>&1; }
```

---

## 4. ✅ O que funciona — solução validada nesta máquina

Todo o resto do instalador está correto e roda bem aqui. E a saída para os motores
**já existe no próprio script**: é o padrão de binário estático usado em
`install_rga()` e `install_pandoc()`. Basta estendê-lo ao `ripgrep` e ao `fd`, que
publicam tarballs `x86_64-unknown-linux-musl` oficiais no GitHub.

Testado e funcionando, sem root e sem reboot:

```bash
# ripgrep estático
curl -fsSL https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/\
ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz | tar xz
install -m755 ripgrep-*/rg ~/.local/bin/rg

# fd estático
curl -fsSL https://github.com/sharkdp/fd/releases/download/v10.4.2/\
fd-v10.4.2-x86_64-unknown-linux-musl.tar.gz | tar xz
install -m755 fd-*/fd ~/.local/bin/fd
```

Resultado:

```
$ ~/.local/bin/rg --version
ripgrep 15.2.0 (rev e89fff89ac)
$ ~/.local/bin/fd --version
fd 10.4.2
```

`~/.local/bin` já está no PATH do usuário, então os binários passam a ser vistos
pelo `has()` do instalador — que então pula o `dnf` e nunca trava.

---

## 5. Correções propostas ao `install.sh`

### 5.1 🔴 Prioridade máxima — nunca deixar o `$INSTALL` travar

Duas linhas de defesa, ambas baratas:

**(a) Detectar sistema imutável ANTES de escolher o gerenciador.** Em ostree, não há
gerenciador utilizável para o nosso caso: melhor declarar `PM=""` e seguir direto
para o caminho de espaço de usuário, que é o que funciona.

```bash
detect_pm() {
  if [ -e /run/ostree-booted ]; then
    PM=""; OSTREE=1
    wn "sistema imutável (ostree) — pacotes de sistema exigiriam rpm-ostree + reboot;"
    wn "usando binários estáticos e venv em ~/.local (nenhum root necessário)."
    return
  fi
  if   has apt-get; then PM=apt;    INSTALL="sudo apt-get install -y"
  ...
}
```

**(b) Cinto de segurança universal — pôr um `timeout` em toda instalação de sistema.**
Vale para qualquer distro, não só ostree: nenhum instalador deveria poder pendurar
para sempre por causa de um gerenciador de pacotes que resolveu abrir um navegador.

```bash
INSTALL="timeout 300 sudo dnf install -y"
```

### 5.2 🟠 Estender o padrão de binário estático a `ripgrep` e `fd`

Espelhando `install_rga()`, que já resolve o mesmo problema para o `rga`:

```bash
install_static_engines() {
  mkdir -p "$PREFIX/bin"
  [ "$ARCH" = "x86_64" ] || { wn "binários estáticos só p/ x86_64"; return; }
  has rg || dl_tar "https://github.com/BurntSushi/ripgrep/releases/download/$RGV/ripgrep-$RGV-x86_64-unknown-linux-musl.tar.gz" rg
  has fd || dl_tar "https://github.com/sharkdp/fd/releases/download/$FDV/fd-$FDV-x86_64-unknown-linux-musl.tar.gz" fd
}
```

Ganho: em **qualquer** distro sem esses pacotes — imutável, corporativa travada, ou
sem privilégio de root — o app passa a rodar com os motores nativos em vez do
fallback. Deixa de ser um remendo para o Bazzite e vira robustez geral.

### 5.3 🟡 `has()` imune a funções e aliases

```bash
has(){ type -P "$1" >/dev/null 2>&1; }
```

### 5.4 🟡 Oferecer o caminho `rpm-ostree` como alternativa explícita

Para quem prefere pacotes do sistema, documentar (sem executar por conta própria,
já que exige reboot):

```bash
rpm-ostree install ripgrep fd    # requer reiniciar para valer
```

### 5.5 🟢 `ask()` fora de TTY assume "sim" — reconsiderar

```bash
ask(){ [ "$ASSUME_YES" = 1 ] && return 0; [ -t 0 ] || return 0; ... }
```

Fora de terminal, o script **consente sozinho** com instalações de sistema via `sudo`.
Foi assim que ele chegou ao `dnf` sem que ninguém confirmasse. O padrão mais seguro
para automação é o inverso: sem TTY e sem `-y` explícito, **recusar** o que exige
privilégio, e seguir pelo caminho de espaço de usuário.

---

## 6. Estado final desta máquina — ✅ instalado e funcionando

| Item | Estado |
|---|---|
| Repositório clonado | ✅ `~/projetos/sombrero-file-search` (`907085f`, 25/07) |
| `rg` 15.2.0 estático | ✅ `~/.local/bin/rg` |
| `fd` 10.4.2 estático | ✅ `~/.local/bin/fd` |
| `pdftotext` | ✅ do sistema |
| `rga` / `pandoc` | ✅ estáticos em `~/.local/share/sombrero-file-search/bin` |
| PySide6 6.11.1 (venv) | ✅ `~/.local/share/sombrero-file-search/venv` |
| App + atalho de menu | ✅ build `907085f+ (2026-07-25)` |

### Como a instalação foi concluída

**Sem patch no `install.sh`.** Bastou pré-instalar os dois motores como binários
estáticos (seção 4) *antes* de rodar o script. Com `rg` e `fd` visíveis no PATH, o
`has()` retorna cedo e o passo `[1/5]` nunca chega ao `dnf`; e o passo `[4/5]` foi
poupado pela salvaguarda acidental do `pkg_exists` descrita na seção 1.

Resultado: o instalador rodou de ponta a ponta **sem uma única chamada ao `dnf`**,
sem root e sem reboot.

### Verificação

O próprio app confirma que está usando os motores nativos, não o fallback:

```
$ sfs ~/projetos/sombrero-file-search -n '*.md'
# engine: rg=/home/rtoledo/.local/bin/rg fd=/home/rtoledo/.local/bin/fd rga=…/bin/rga
```

- **CLI** — busca por nome e por conteúdo, ambas retornando resultados corretos.
- **GUI** — `QApplication` criada em modo *offscreen*, `lfs.app` importado,
  `MainWindow` presente, saída 0. PySide6 6.11.1 sobre Wayland.

> Nota: o `+` em `907085f+` indica árvore suja — é este próprio arquivo de relatório,
> ainda não commitado.

---

## 7. Conclusão

Nenhum dos três problemas é culpa da arquitetura do Sombrero — o app é bem-comportado,
instala em `~/.local`, não pede root e já tem o mecanismo certo (binário estático)
implementado para outras dependências. O que falta é **não confiar na existência de
um gerenciador de pacotes** e estender aos dois motores principais a estratégia que
já funciona para `rga` e `pandoc`.

Feito isso, o Bazzite deixa de ser um caso especial: passa a ser apenas mais uma
distro onde o instalador roda até o fim, sem root e sem reboot.
