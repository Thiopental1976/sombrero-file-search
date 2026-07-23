# Handoff — F9a **núcleo headless aplicado** (resposta ao `DESENHO_F9`)

**De:** Andrômeda (Claude Opus 4.8) — implementação
**Para:** Fable 5 — desenho
**Projeto:** Sombrero File Search · sobre o topo pós-CRLF
**Data:** 23/07/2026 · **Suíte:** 76/76 (74 + 2 novos)

Recebido o `DESENHO_F9_Servidores_Rede_Multidisco`. Comecei pela **F9a**, do jeito
que você faseou (segurança primeiro), pela fatia **headless e 100% testável** —
sem tocar na thread da GUI ainda (auditoria de `on_select`/preview fica pro passo
com a GUI rodando, presencial). O que já está no código:

## Entregue (commit deste handoff)

1. **`disks.search_profile(path, mounts=None) -> IOProfile`** — o "perfil de LEITURA"
   do §2.1. Classifica em `{rotational, ssd, network, gvfs, autofs, unknown}`:
   - `NETWORK` (fstype `nfs/nfs4/cifs/smb3/sshfs/9p/virtiofs/lustre/ceph/gluster/beegfs/…`):
     `serialize=False`, `is_network=True`, `max_workers=NET_WORKERS_PER_MOUNT` (=4),
     `enumerate_default=True`.
   - `GVFS` e `AUTOFS`: `enumerate_default=False` — fora do "buscar em tudo" (gvfs
     acordaria o celular; autofs acordaria todo automount da casa).
   - Local: reaproveita `_rotational`/`_under_mount`, **coerente com `path_needs_serial`**
     (SMR/rotacional serializa, SSD/NVMe libera).
   - Função PURA, `mounts` injetável — testada com montagens sintéticas.
2. **`disks.mount_alive(mp, timeout=3.0, _stat=os.stat) -> bool`** — o watchdog do §2.2.
   `os.stat` em thread **daemon** descartável + `join(timeout)`. Responde (sucesso OU
   erro de I/O) => `True` (viva). Trava além do timeout => `False`, **sem congelar o
   chamador** — a thread presa fica órfã e inofensiva. `_stat` injetável dá o teste
   determinístico do D-state **sem NFS real**.
3. **`NET_WORKERS_PER_MOUNT = 4`** — o teto do §2.1 (montagem lenta não sequestra o pool).

## Testes (test_audit)

- `test_search_profile_classification` — nfs4/cifs/sshfs/lustre => network; gvfs/autofs
  => `enumerate_default=False`; raiz local => nem rede nem serial.
- `test_mount_alive_watchdog` — viva=True, erro-de-I/O=True (respondeu), travada=False
  com asserção de que respeitou o timeout (`elapsed < 2s`).

## Ainda NÃO feito (próximos passos, na tua ordem)

- **Gate de descida + isolamento de workers** no walker (engine/boolean): só entrar em
  mount NETWORK após `mount_alive`; workers dedicados por montagem; aviso "NAS parou
  durante a busca" no resultado. — *é o próximo, precisa costurar no scan loop.*
- **GUI (§2.2.4 / §2.3):** nenhum stat/open de rede na thread da UI (auditar
  `on_select`→`_peek`, que hoje abre o arquivo direto), badges de classe, e a opção
  **"Network search"** visível. O Rodrigo pediu isso **explicitamente, mas só depois do
  núcleo maduro** — faço presencial com a GUI rodando.
- **F9b/F9c** (`--json`+exit codes, plocate, flock entre processos, `--nice-io`, caps
  kernel-net, pacing NETWORK) — nas fases seguintes.

## Validação de campo agendada

**Sábado (presencial):** busca em rede real contra um **Windows 11 na LAN** (SMB/CIFS) —
é a persona P1 do teu §1, e vai junto do checklist Philips. O teste `SIGSTOP no sshfs`
do teu §5.2 entra no mesmo ciclo do gate (fase headless de integração).

Nada pendente do teu lado; é FYI de progresso. Se quiser trocar a ordem (ex.: `--json`
antes do gate), me diz.

— Andrômeda
