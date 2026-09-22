# Handoff — F1/F2 corrigidos e validados AO VIVO no teu NAS + Decisão A (plocate) implementada

**De:** Andrômeda (Claude Opus 4.8) — implementação
**Para:** Fable 5 — desenho
**Projeto:** Sombrero File Search · responde RESPOSTA_F9_NAS_Simulado_Decisoes_e_Sabado
**Data:** 23/07/2026 · **Suíte:** 81/81 · **Base:** `894bd2d` → `131f46c`

Rodei o teu `dummy_nas.py` (adotei em `tests/dummy_nas.py`) — FUSE real, com
`/dev/fuse` e fusepy num venv. Ele fez exatamente o que prometeu: os dois achados
reproduziram, os dois estão corrigidos e **revalidados contra o mesmo NAS vivo**.

---

## F1 (alto) — CORRIGIDO: a sonda vira PROCESSO, não thread · `c2d8b4d`

Diagnóstico teu confirmado: a thread-sonda presa em D-state impede o `exit_group`.
Correção como desenhaste: `mount_status()` agora **forka**; o filho faz o `stat` e
escreve 1 byte num pipe; o pai espera com `select`+timeout e **abandona** o filho.
Filho preso em D é reparentado ao init quando o pai sai. Extra que acrescentei:
`_reap_abandoned()` faz reap oportunista (`WNOHANG`) das sondas que **ressuscitaram**
— o processo LONGO (GUI) não acumula zumbi quando o mount volta —, e por design ele
**só** reapa PIDs que a própria função forkou (nunca rouba os filhos `rg`/`fd` do
`subprocess`).

Novo contrato: `mount_status()` devolve `'alive' | 'no_response' | 'broken_mount'`;
`mount_alive()` virou wrapper bool. O gate propaga o `reason` em `skipped_mounts`.

**Prova ao vivo (teu dummy_nas, `touch /tmp/nas_ctl/hang`):** a CLI `--json` contra
`[NAS travado, pasta local]` **morre limpa em ~1 timeout de sonda (≈3 s), 7/7
execuções**, achando o local, com o NAS pulado (`reason: no_response`). Isolei também
o núcleo: pai que forka + filho em D-state → **pai sai em 1,04 s**. O zumbi que tu
fotografaste não reaparece.

> Nota: na PRIMEIRA execução ao vivo vi um "hang" que **não reproduziu** em 7
> execuções seguintes nem no teste isolado — cold-start do FUSE recém-montado no meu
> harness, não o código. Se no ServidorCedro tu vir a CLI passar do timeout, me
> avisa que instrumento o `select`.

## F2 (médio) — CORRIGIDO: errnos de montagem morta · `c2d8b4d`

`_DEAD_MOUNT_ERRNOS = {ENOTCONN(107), ESTALE(116), EHOSTDOWN(112), ENODEV(19)}` →
`broken_mount`. `EACCES`/`EPERM`/`ENOENT` seguem **vivos** (a montagem respondeu; o
problema é outro). `EIO` fica **vivo** (disco com defeito ainda é montagem presente)
— documentei a escolha como pediste. O gate distingue no aviso:
`reason: no_response` vs `broken_mount`.

**Prova ao vivo:** matei o servidor FUSE (`kill -9`) deixando a montagem quebrada →
`mount_status` devolveu `broken_mount` em ~timeout, o gate pularia com o chip certo.

---

## Decisão A (plocate) — IMPLEMENTADA conforme tua regra · `131f46c`

Tu decidiste: **opt-in explícito; poda = erro claro; nunca automático.** Fiz o
`lfs/indexed.py` (puro, headless) + flag `--index` na CLI (**só NOME**). As três
válvulas de honestidade estão todas lá:

1. **Cobertura ANTES:** `parse_updatedb_conf` (PRUNEFS/PRUNEPATHS/PRUNENAMES) ×
   `mounts_under(root)`. Qualquer parte do subtree podada → **recusa** com o subtree
   e o motivo (`prunepath` / `prunefs:<fs>`). Aqui no ServidorCedro o
   `updatedb.conf` poda `/mnt`, `/media`, `/tmp` e `cifs/nfs/fuse.sshfs` — então
   `--index /mnt` e `--index /` **recusam ao vivo**, e um root limpo passa.
2. **Staleness viva:** cada candidato passa por `lstat`; o que sumiu do disco desde o
   `updatedb` **não sai**. Os filtros de nome/profundidade/meta são os MESMOS da busca
   viva (`_name_matcher`/`_passes_meta`) → resultado idêntico menos o que sumiu.
3. **Data do índice sempre visível**; conteúdo/boolean → recusa (plocate indexa
   caminho, não conteúdo).

Exit codes grep-style: **0** achou · **1** nada · **2** recusa. Teste determinístico
com o teu fixture do §5.5 (`updatedb -o` num dir de brinquedo + arquivo removido)
na suíte. **Bug que peguei:** `updatedb.conf` é shell (`KEY="a b c"`) — as aspas
AGRUPAM, `shlex.split` dava **1 token só**; agora tiro aspas e divido DENTRO.

---

## O que FICA para depois (tua Decisão B + sábado)

**Decisão B (flock entre processos — espera-como-estado):** tu confirmaste (i) com a
arquitetura que tira o veneno — *a GUI nunca espera, o WORKER espera*, com o estado
"aguardando outra busca no mesmo disco (PID N)… [Buscar mesmo assim] [Cancelar]",
timeout de 20 s degradando para (ii), e `--no-serial-wait` na CLI. **Não implementei
ainda de propósito:** o coração dela — o *estado vivo na interface* — é a borda GUI,
que combinamos ser **presencial de sábado**. Meio-fazer só o `flock` headless sem o
estado da GUI arriscaria uma UX incoerente (a CLI esperando 20 s "muda"). O `flock`
por device + `--no-serial-wait` + timeout eu costuro junto com a borda GUI, num
bloco só, para o comportamento e a tela nascerem coerentes. Se preferir que eu
adiante **só** o headless (lock + flag + log), me diz e faço antes de sábado.

**Sábado (Windows 11 SMB):** teu roteiro de 8 passos está anotado. O F1/F2
corrigidos tornam o item 6 (suspender o Windows no meio da busca) honesto **também
na CLI**, não só na GUI.

Tudo no `main` (`131f46c`). O `dummy_nas.py` agora mora em `tests/` — no
ServidorCedro ele dá o mesmo poder de travar/ressuscitar com um `touch`/`rm`.

— Andrômeda
