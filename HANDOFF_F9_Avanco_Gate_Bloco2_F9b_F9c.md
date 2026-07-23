# Handoff — F9 avançou muito + Bloco 2 fechado (2 decisões de SEMÂNTICA p/ você)

**De:** Andrômeda (Claude Opus 4.8) — implementação
**Para:** Fable 5 — desenho
**Projeto:** Sombrero File Search · sobre o topo pós-CRLF/F9a-núcleo
**Data:** 23/07/2026 · **Suíte:** 80/80 · **Paridade standalone:** 12 OK / 10 conhecidas / 0 BUGS

Rodrigo pediu para eu avançar o **máximo** possível nesta sessão ("corrigimos os
problemas na medida em que aparecem; o Fable pode testar os ambientes de rede de
forma simulada"). Fiz — 6 commits, todos verdes e no GitHub para você baixar. No
fim, **paro em duas coisas que são decisão SUA** (mexem em *semântica de
resultado*, não em mecânica), com a pergunta objetiva de cada uma.

---

## O que LANDOU (empurrado p/ o main)

### 1. Gate de descida no walker — F9a §2.2 (`fc391a3`)
`engine._live_roots(paths, stats)`: antes de o walker entrar num root, se ele for
**rede**, sonda `mount_alive` numa thread descartável. Montagem morta → **pulada**,
aviso em `stats["skipped_mounts"]` (lista de `{path, mount, fstype, reason}`).
Roots locais passam direto, sem custo de sonda. Aplicado nos **dois** motores
(`engine.search` e `boolean.search_boolean`) via `dataclasses.replace` — não muta a
`Query` do chamador. Teste determinístico com `search_profile`/`mount_alive`
monkeypatched (NAS morto pulado + vivo passa + todos-mortos = lista vazia).

### 2. Campanha 2 / Bloco 2 — fuzz de nomes + dirigido multi-termo (`8d75f74`)
Você liberou no §0. Dois casos novos no harness de paridade:
- **`caso_fuzz_nomes`** — fuzz de busca **por NOME** comparando o mundo **fd**
  contra o fallback **os.walk+fnmatch/re**. Varia glob (1..6 padrões — **≥4 dispara
  a FUSÃO** `_merge_globs`/`_glob_to_regex`, que era o alvo principal), regex, caixa,
  ocultos, profundidade e recursão. Nomes ASCII de propósito (case-fold do Python
  `.lower` ≡ `--ignore-case` do fd), p/ isolar bug de **lógica**. **300 queries × 600
  arq: fd ≡ Python, zero divergência** — a tradução glob→regex está correta.
- **`caso_multitermo_dirigido`** — dois termos positivos: (a) **mesma linha →
  dedup** (a linha aparece 1×, não 1 por termo); (b) **linhas distintas → ordenação**
  por nº de linha; `max_results` apertado; vale nos 2 mundos. Confirmei nos dois
  caminhos de exibição (`_display_lines` do rg e `_display_lines_py`) que o dedup e a
  ordem já saem naturais — o teste **pina** isso contra regressão.

### 3. F9b núcleo — `--json` + exit codes + `--nice-io` + EACCES visível (`48b8462`)
A interface de automação da persona servidor (seu §3):
- **`--json`** — NDJSON, um objeto por match (`path,size,mtime,is_dir,nmatch,lines[]`).
  Nome com `\n` é **escapado pelo json** e nunca racha o framing (o teste do seu
  §5.6); nomes não-UTF-8 sobrevivem via `surrogatepass`. Avisos **no mesmo stream**
  (`{"warn":"mount_dead"}` do gate, `{"warn":"denied"}`); erro de expressão →
  `{"error":"boolean_expression"}`.
- **Exit codes estilo grep:** 0 = achou, 1 = nada, 2 = erro.
- **`--nice-io`** — `os.nice(19)` + `ionice` idle no próprio processo (os filhos rg/fd
  herdam) p/ busca de cron não brigar com o serviço do servidor.
- **EACCES visível** — `stats["denied"]` e as montagens puladas reportados no stderr
  (texto) e no stream (json): parcial **anunciado**, nunca mudo.

### 4. F9c — caps de rede do KERNEL + pacing de rede (`31955e5`)
- **`_FS_CAPS` estendida** aos mounts que o SO já montou (não-gvfs): `nfs/nfs4/9p/
  virtiofs` → POSIX pleno (`net=True`); `cifs/smb3/smbfs/smb` → perfil **SMB**
  (charset do protocolo, sem symlink) — **isto era um furo**: antes um CIFS caía em
  `_DEFAULT_CAPS` (POSIX otimista) e a pré-checagem **liberava** `: ? *` num nome que
  o SMB recusa; `fuse.sshfs/sshfs` → SFTP (rename atômico → ATOMIC).
- **Pacing de escrita** (fdatasync+fadvise por 16 MiB) generalizado de `removable`
  p/ `{removable, NETWORK}` — CIFS/NFS lento acumula writeback global igual ao
  pendrive. (Nota sua registrada no código: fsync sobre NFS é caro, mas "copiado =
  está lá" vale mais no NAS.)

### 5. F9a §2.3 — visibilidade de fronteira (`d263245`)
`disks.mounts_under(root)` e `disks.list_search_targets(paths)` — **puros, headless**:
p/ cada root e as montagens que moram sob ele, devolvem a **classe** (disco/ssd/
rotational/network/gvfs/autofs) e, p/ rede, o **status de vida**. É o núcleo do
preview "buscar em `/mnt` vai tocar N montagens" e dos badges de chip, **sem tocar na
thread da GUI** (a borda GUI fica p/ o presencial).

### 6. README
Nova seção **"Servidores, NAS e montagens de rede"** (watchdog, classe de I/O, caps
por protocolo, fronteira visível) + a **recusa de identidade do seu §7** escrita como
você pediu ("não é indexador residente; apoia-se no `plocate` se existir, daemon
próprio não; não vira serviço web — SSH + `--json`"). Bloco `--json`/exit-code/
`--nice-io` no uso da CLI.

---

## Onde eu PAREI de propósito — 2 decisões de SEMÂNTICA (suas)

O gate/caps/json/visibilidade são **mecânica e segurança** — implementei direto. As
duas abaixo mudam **o que o usuário vê como resultado ou como a busca se comporta no
tempo**, e isso é semântica, que é sua. Não quis decidir sozinho.

### A. `plocate` (F9b §3.2) — aceleração por índice: **completude vs. poda**
O risco que me fez parar: `updatedb` **poda** caminhos por padrão (`/tmp`, `/var`,
montagens removíveis, **filesystems de rede**…). Se um root inteiro está podado do
índice, `plocate` devolve **zero** — e numa ferramenta "viva, mostra o que está no
disco AGORA", um **vazio que parece 'nada encontrado' quando na verdade é 'não
indexado'** é pior que uma divergência: é uma mentira silenciosa, contra a identidade
do §1/§7.
- Sua rede de segurança já prevista (verificação viva + `--no-index` + aviso "índice
  de \<data\>") cobre **staleness** (arquivo sumiu/apareceu), mas **não** cobre o caso
  "root 100% podado → resultado vazio".
- **Pergunta:** quando `plocate` retorna **zero candidatos** para um root, eu **caio
  para o `fd`/walk** desse root (seguro, mas então a aceleração "não ajuda quando mais
  importa") ou **confio no zero** com o aviso? E qual é o **gatilho** de usar plocate —
  só sob demanda (`--index`/flag), ou "usa se existir" com fallback automático no zero?
  Me diga a regra e eu implemento + testo com o seu fixture do §5.5 (`updatedb -o` +
  arquivo removido).

### B. Trava entre processos / isolamento de workers (F9b §3.3 + F9a §2.2.3) — **UX do bloqueio**
A serialização SMR de hoje é **in-process** (`_max_workers`→1). A trava `flock` que
você desenhou serializa **dois processos** (GUI + cron no mesmo SMR). Mecanicamente é
tranquilo e não muda resultado nenhum — **muda o TEMPO**: uma busca interativa pode
**esperar** o cron soltar o disco.
- **Pergunta:** o comportamento certo quando a trava está tomada por outro processo é
  **(i)** esperar educadamente (com aviso "aguardando outra busca no mesmo disco…") —
  respeita o SMR mas a GUI "trava" por um tempo; ou **(ii)** seguir sem serializar
  entre processos (aceita o *seek thrash* raro) e só logar? Sua §3.3 diz "não-bloqueante
  com espera educada e log" — confirmo que a **GUI** também espera, ou aí eu prefiro
  degradar p/ (ii) e manter a interface sempre responsiva? O **isolamento de workers
  por montagem** (§2.2.3) eu costuro junto assim que a arquitetura de pool cobrir o
  walker de conteúdo (hoje o conteúdo é um `rg` único; o pool é só do OR booleano).

---

## Testes de campo agendados (sábado, presencial)
Busca em rede real contra um **Windows 11 na LAN** (SMB/CIFS — persona P1) + o
`SIGSTOP no sshfs` do seu §5.2 (mata a montagem de forma determinística p/ validar o
gate e o watchdog end-to-end). A **borda GUI** (chips com badge de classe, opção
"Network search", `on_select`/preview fora da thread da UI) também é presencial.

**Se você puder rodar as simulações headless** (sshfs p/ localhost = montagem NETWORK
real e barata, §5.1; e o SIGSTOP), elas exercitam `search_profile`/`mount_alive`/
`_live_roots` com uma montagem de rede de verdade — bom teste de integridade antes de
sábado. Todo o núcleo está no main.

— Andrômeda
