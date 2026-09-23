# Incompleteness contract (`--json` and exit codes)

*Versão em português: [CONTRATO_FUNIL.pt-BR.md](CONTRATO_FUNIL.pt-BR.md).*

SFS says **what was left out and why**, through a single channel
(`stats["incompleto"]` in `lfs/engine.py`), and from it derive the GUI status bar, the
per-root panel, the CLI stderr, `--json` and the exit code. This page is the **contract
for scripts**: the IDs below are API. Renaming one requires keeping the old one as an alias.

## Exit codes (grep style)

| Code | Meaning |
|---|---|
| **0** | at least one result, and no **fatal** loss |
| **1** | nothing found, and no **fatal** loss — "nothing found" is true |
| **2** | a **fatal** loss (the result may be wrong: this is *not* "nothing found") **or** a usage error (invalid flag, invalid size/depth, invalid boolean expression, `--index` refused) |
| **130** | interrupted with Ctrl-C |

Non-fatal losses (a folder that denied reading, an unreadable file, a skipped snapshot…)
do **not** change the code: they are shown as warnings.

## Reasons (`reason`)

| `reason` | Text (short `detail`) | Fatal? | When |
|---|---|---|---|
| `engine_failed` | search engine failed | **yes** | fd/rg exited with an error that is neither about one file nor a signal we sent (e.g. an unsupported flag) |
| `engine_missing` | search engine missing | **yes** | fd/rg could not be run; the search fell back to the Python walker, which is not equivalent |
| `disk_failed` | disk failed | **yes** | an exception while processing one disk in the partitioned search |
| `invalid_root` | invalid location | **yes** | the folder asked for does not exist, or is not a folder |
| `not_mounted` | disk not mounted | **yes** | the folder asked for is in `/etc/fstab` and the disk is not mounted |
| `dead_mount` | mount not responding | **yes, if it is the folder you TYPED**; no, if it was found underneath another root (e.g. a NAS under `/`) | a network/FUSE mount that did not answer the probe (3 s) — `detail` carries `no_response` or `broken_mount` |
| `permission_denied` | permission denied | no | folders or files that denied reading (`count` = how many) |
| `read_error` | read error | no | files that were listed but could not be read |
| `stat_failed` | file vanished | no | the engine listed it, but it was gone before the `stat` |
| `mount_not_entered` | mount not entered | no | gvfs/autofs/MTP are not enumerated by default; search them by their own path |
| `empty_mountpoint` | empty mount point | no | an empty mount slot (a hint that a disk is missing) |
| `batch_failed` | batch failed | no | one boolean batch failed; the others went on |
| `truncated` | truncated | no | the result cap was reached (`max_results`) |
| `interrupted` | interrupted | no | a disk did not answer the cancellation in time |
| `snapshots_skipped` / `snapshots_searched` | snapshots skipped / searched | no | a snapshot tree was pruned, or included (`--snapshots`, or zero live hits) |

Fatality comes from `engine.MOTIVOS_GRAVES` **or** from the entry's own `grave` mark — that
is how `dead_mount` is fatal only for the folder you typed. The single source is
`engine.resumo_incompleto`.

## `--json` events (NDJSON, one object per line)

- Result: `{"path", "size", "mtime", "is_dir", "nmatch", "lines": [...], "snapshot", "copies": [...]}`
- Copy absorbed by the dedup after its owner was printed: `{"copy": "<path>", "of": "<owner>", "snapshot": ...}`
- Loss: `{"warn"|"error": "incomplete", "reason", "where", "detail", "count"}` — `"error"` when fatal
- Skipped mount: `{"warn": "mount_dead", "path", "mount", "fstype", "reason"}` (`reason`: `no_response` | `broken_mount`)
- Denied folders (count): `{"warn": "denied", "count"}`
- Index: `{"warn": "index_used", "index_date"}` · `{"error": "index_coverage", "detail"}`
- Invalid boolean: `{"error": "boolean_expression", "detail"}`

`detail` is always in **English**, in every locale (the CLI is the automation contract).

## Real example — a typed NAS, frozen

```json
{"warn": "mount_dead", "path": "/var/mnt/NAS", "mount": "/var/mnt/NAS", "fstype": "cifs", "reason": "no_response"}
{"error": "incomplete", "reason": "dead_mount", "where": "/var/mnt/NAS", "detail": "cifs: no_response", "count": 1}
```
→ exit code **2** (the question *was* the NAS, and it was never looked at). Field evidence in
`docs/campo/2026-09-22-nas-truenas/` (captured before this rule, when the exit code was 1).

## How it is verified

`tests/test_honestidade.py` (engine × loss matrix), `tests/test_funil_incompleto.py`,
`tests/test_motor_falhou.py`, `tests/test_revisao_fable_2026_09_22.py` (fatality by place).
Implementation detail: `TECHNICAL_DOCUMENTATION.md` §20.3.
