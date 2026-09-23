# Field test: a real TrueNAS over the tailnet (2026-09-22)

*Versão em português: [README.pt-BR.md](README.pt-BR.md).*

Raw evidence of the test that led to commit `e3fc1ae` and the ones after it. Kept on the
review's suggestion: the SFS `--json` output plus the kernel log of the period are worth more
in a second analysis than a description of the symptom.

## The bench

- **NAS:** TrueNAS SCALE 25.10.7 in a libvirt VM on ServidorCedro (4 vCPU, 8 GB), RAIDZ1 pool
  of four 20 GB "bays" on a mechanical disk; dataset `tanque/Compartilhado` over SMB,
  *case-insensitive*, NFSv4 ACL, LZ4. Synthetic data only (fixed seed).
- **Network:** tailnet (Tailscale), `tailscale serve` forwarding 445 → VM.
- **Client:** Bazzite (ostree), kernel 6.18, `mount -t cifs … vers=3.1.1` at `/var/mnt/NAS`
  (effective options: `soft,echo_interval=60,actimeo=1`).
- **Content:** 3,261 synthetic files (~611 MB) plus 27 created during the test over SMB itself
  in `idiomas_e_nomes/` (15 writing systems, macOS NFD, RTL override, zero width, quotes,
  `$(…)`, a ~240-byte name, cp1252/cp1251/Shift-JIS content).
- **Simulated failure:** `virsh suspend nas-simulado` — the NAS freezes with the mount still
  "alive" (TCP open, nothing answers): the worst case.

## Files

| File | What |
|---|---|
| `1_nas_vivo.*` | name search in Cyrillic on the live NAS: 0.7 s |
| `2_nas_congelado.*` | **frozen NAS, fixed build, first run: 3.4 s**, `dead_mount` / `cifs: no_response` |
| `3_kernel_cifs.log` | kernel during the short freeze: **empty** |
| `4_congelado_5s/100s.ndjson` | long freeze: search at 5 s and at 100 s — 3.4 s and 3.5 s, NAS skipped in both |
| `5_apos_retomar.txt` | after `resume`: the NAS answers in 0.1 s, search back to normal |
| `6_kernel_cifs_congelamento_longo.log` | kernel during 107 s of freeze: **empty** (cifs only declares the server dead at 3 × `echo_interval` = 180 s) |
| `7_nas_vivo_conteudo_final.*` | content `AGULHA-` across the whole NAS, final code: 91 files (64 from the source + 27 created), 6 DOS reserved names as `read_error` |

> **Note (2026-09-22, Fable's commit `7ec3a71`):** these captures show the typed, frozen NAS
> exiting with `rc=1` and `"warn": "incomplete"`. The evidence itself revealed that this was a
> lying "nothing found": since then, a dead mount that is the **typed root** is fatal —
> `rc=2` and `"error": "incomplete"`. Contract in `docs/FUNNEL_CONTRACT.md`.

## What the test showed (and the fixes)

1. **The probe was fooled by the cache.** `mount_status` only did a `stat` — answered by the
   attribute cache with the server dead (local NFS: "OK" in 0.0 s). It now also does
   `statvfs`, which goes to the server.
2. **A `stat` on the ROOT, outside the probe.** `planejar_raizes` (F12) runs before the gate
   and did a `stat` on the root — with the root being the frozen NAS, the search hung
   (measured 150 s on build `e3fc1ae`; the same build "passed" in 15 s on a second run only
   because the client had already marked the server dead — **the order of the tests
   deceives**). A network/FUSE root no longer takes a `stat`; that is the probe's job.
3. **"search engine failed" because of 6 files.** DOS reserved names (`CON.txt`…) that the NAS
   lists in 8.3 form (`AHY9U3~9`) but will not open made `rg` exit 2 and turned the whole
   search into a fatal failure. A complaint that is only "`<path>`: reason (os error N)" is now
   a `read_error` for those files.
4. **macOS NFD.** "médico" did not find `médico_decomposto_NFD.txt`. The term and the glob now
   go in both Unicode forms (NFC and NFD).

## Checked against the source

`CODIGO-AGULHA-7731`: 57 in SFS = 57 at the source. `AGULHA-` in the edge cases: every
difference is explained — `laudo.txt` merged into `Laudo.txt` by the case-insensitive NAS (it
does not exist there); `.oculto/` out by default (hidden folder); `utf16_bom.txt` found by SFS
and not by `grep` at the source (grep does not read UTF-16).

## Left open

- `fatura_‮txt.exe` is displayed as "fatura_exe.txt" (RTL override) and
  `zero​width.txt` is not found by "zerowidth": invisible characters in the name — an item
  of its own for display/search, Rodrigo's decision. *(Fixed in v1.2.0.)*
- A name search across the whole NAS takes ~30 s and a content search ~110 s over the tailnet
  (SMB, real latency) — expected, and the reason behind the "Network outside All disks"
  decision.
