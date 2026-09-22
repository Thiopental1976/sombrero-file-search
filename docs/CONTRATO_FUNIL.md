# Contrato do funil de incompletude (`--json` e código de saída)

O SFS diz **o que ficou de fora e por quê**, num canal só (`stats["incompleto"]` em
`lfs/engine.py`), e dali derivam a barra da GUI, o painel por raiz, o stderr da CLI, o
`--json` e o código de saída. Esta página é o **contrato para scripts**: os IDs abaixo são
API. Renomear um exige manter o antigo como alias.

## Código de saída (estilo grep)

| Código | Significado |
|---|---|
| **0** | achou pelo menos um resultado e nenhuma perda **grave** |
| **1** | não achou nada e nenhuma perda **grave** — "nada encontrado" é verdade |
| **2** | perda **grave** (o resultado pode estar errado: não é "nada encontrado") **ou** erro de uso (flag inválida, tamanho/profundidade inválidos, expressão booleana inválida, `--index` recusado) |
| **130** | interrompido com Ctrl-C |

Perdas não-graves (pasta sem permissão, arquivo ilegível, snapshot pulado…) **não** mudam o
código: aparecem como aviso.

## Motivos (`reason`)

| `reason` | Texto (`detail` curto) | Grave? | Quando |
|---|---|---|---|
| `engine_failed` | search engine failed | **sim** | fd/rg saiu com erro que não é de um arquivo nem sinal nosso (ex.: flag não suportada) |
| `engine_missing` | search engine missing | **sim** | fd/rg não pôde ser executado; a busca caiu no fallback Python, que não é equivalente |
| `disk_failed` | disk failed | **sim** | exceção no processamento de um disco na busca particionada |
| `invalid_root` | invalid location | **sim** | a pasta pedida não existe ou não é pasta |
| `not_mounted` | disk not mounted | **sim** | a pasta pedida está no `/etc/fstab` e o disco não está montado |
| `dead_mount` | mount not responding | **sim, se é a pasta DIGITADA**; não, se foi achada por baixo de outra (ex.: NAS sob `/`) | montagem de rede/FUSE que não respondeu à sonda (3 s) — `detail` traz `no_response` ou `broken_mount` |
| `permission_denied` | permission denied | não | pastas ou arquivos que negaram leitura (`count` = quantos) |
| `read_error` | read error | não | arquivos listados que não puderam ser lidos |
| `stat_failed` | file vanished | não | o motor listou, mas o arquivo sumiu antes do `stat` |
| `mount_not_entered` | mount not entered | não | gvfs/autofs/MTP não são enumerados por padrão; busque pelo caminho deles |
| `empty_mountpoint` | empty mount point | não | vaga de montagem vazia (indício de disco ausente) |
| `batch_failed` | batch failed | não | um lote do booleano falhou; os demais seguiram |
| `truncated` | truncated | não | bateu no teto de resultados (`max_results`) |
| `interrupted` | interrupted | não | um disco não respondeu ao cancelamento a tempo |
| `snapshots_skipped` / `snapshots_searched` | snapshots skipped / searched | não | árvore de snapshot podada, ou incluída (`--snapshots` ou zero achados vivos) |

A gravidade vem de `engine.MOTIVOS_GRAVES` **ou** da marca `grave` da entrada (é assim que
`dead_mount` é grave só na pasta digitada). A fonte única é `engine.resumo_incompleto`.

## Eventos no `--json` (NDJSON, um objeto por linha)

- Resultado: `{"path", "size", "mtime", "is_dir", "nmatch", "lines": [...], "snapshot", "copies": [...]}`
- Cópia absorvida pelo dedup depois do dono: `{"copy": "<caminho>", "of": "<dono>", "snapshot": ...}`
- Perda: `{"warn"|"error": "incomplete", "reason", "where", "detail", "count"}` — `"error"` quando grave
- Montagem pulada: `{"warn": "mount_dead", "path", "mount", "fstype", "reason"}` (`reason`: `no_response` | `broken_mount`)
- Pastas negadas (contagem): `{"warn": "denied", "count"}`
- Índice: `{"warn": "index_used", "index_date"}` · `{"error": "index_coverage", "detail"}`
- Booleano inválido: `{"error": "boolean_expression", "detail"}`

O `detail` sai sempre em **inglês**, em qualquer locale (a CLI é o contrato de automação).

## Exemplo real — NAS digitado e congelado

```json
{"warn": "mount_dead", "path": "/var/mnt/NAS", "mount": "/var/mnt/NAS", "fstype": "cifs", "reason": "no_response"}
{"error": "incomplete", "reason": "dead_mount", "where": "/var/mnt/NAS", "detail": "cifs: no_response", "count": 1}
```
→ código de saída **2** (a pergunta era o NAS, e ele não foi olhado). Evidência de campo em
`docs/campo/2026-09-22-nas-truenas/` (capturada antes desta regra, quando a saída era 1).

## Como é verificado

`tests/test_honestidade.py` (matriz motor × perda), `tests/test_funil_incompleto.py`,
`tests/test_motor_falhou.py`, `tests/test_revisao_fable_2026_09_22.py` (gravidade por lugar).
Detalhe da implementação: `DOCUMENTACAO_TECNICA.md` §20.3.
