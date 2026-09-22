# Teste de campo: NAS TrueNAS real pela tailnet (22/09/2026)

Evidência bruta do teste que motivou os commits `e3fc1ae` e seguintes. Guardada
por sugestão da revisão: saída `--json` do SFS + log do kernel do período valem
mais numa segunda análise do que a descrição do sintoma.

## Bancada

- **NAS:** TrueNAS SCALE 25.10.7 numa VM libvirt do ServidorCedro (4 vCPU, 8 GB),
  pool RAIDZ1 de 4 "baias" de 20 GB sobre HD mecânico; dataset `tanque/Compartilhado`
  SMB, *case-insensitive*, ACL NFSv4, LZ4. Só dados sintéticos (seed fixa).
- **Rede:** tailnet (Tailscale), `tailscale serve` repassando 445 → VM.
- **Cliente:** Bazzite (ostree), kernel 6.18, `mount -t cifs … vers=3.1.1` em
  `/var/mnt/NAS` (opções efetivas: `soft,echo_interval=60,actimeo=1`).
- **Conteúdo:** 3.261 arquivos sintéticos (~611 MB) + 27 criados no teste pelo
  próprio SMB em `idiomas_e_nomes/` (15 escritas, NFD do macOS, RTL override,
  largura zero, aspas, `$(…)`, nome de ~240 bytes, conteúdo cp1252/cp1251/Shift-JIS).
- **Falha simulada:** `virsh suspend nas-simulado` — o NAS congela com a montagem
  "viva" (TCP aberto, nada responde): o pior caso.

## Arquivos

| Arquivo | O quê |
|---|---|
| `1_nas_vivo.*` | busca por nome em escrita cirílica no NAS vivo: 0,7 s |
| `2_nas_congelado.*` | **NAS congelado, versão corrigida, 1ª rodada: 3,4 s**, `dead_mount` / `cifs: no_response` |
| `3_kernel_cifs.log` | kernel no congelamento curto: **vazio** |
| `4_congelado_5s/100s.ndjson` | congelamento longo: busca a 5 s e a 100 s — 3,4 s e 3,5 s, NAS pulado nas duas |
| `5_apos_retomar.txt` | depois do `resume`: NAS responde em 0,1 s, busca normal |
| `6_kernel_cifs_congelamento_longo.log` | kernel em 107 s de congelamento: **vazio** (o cifs só declara o servidor morto em 3 × `echo_interval` = 180 s) |
| `7_nas_vivo_conteudo_final.*` | conteúdo `AGULHA-` no NAS inteiro, código final: 91 arquivos (64 da origem + 27 criados), 6 reservados do DOS como `read_error` |

## O que o teste mostrou (e os consertos)

1. **Sonda enganada pelo cache.** `mount_status` fazia só `stat` — respondido
   pelo cache de atributos com o servidor morto (NFS local: "OK" em 0,0 s). Agora
   também `statvfs`, que vai ao servidor.
2. **`stat` da RAIZ fora da sonda.** `planejar_raizes` (F12) roda antes do gate e
   fazia `stat` na raiz — sendo a raiz o NAS congelado, pendurava (medido 150 s na
   build `e3fc1ae`; a mesma build "passou" em 15 s numa 2ª rodada só porque o
   cliente já marcara o servidor como morto — **a ordem dos testes engana**).
   Agora a raiz de rede/FUSE não leva `stat`; é trabalho da sonda.
3. **"search engine failed" por 6 arquivos.** Nomes reservados do DOS (`CON.txt`…)
   que o NAS lista como 8.3 (`AHY9U3~9`) mas não abre faziam o `rg` sair 2 e a
   busca inteira virar falha grave. Queixa que é só "`<caminho>`: motivo (os
   error N)" agora é `read_error` daqueles arquivos.
4. **NFD do macOS.** "médico" não achava `médico_decomposto_NFD.txt`. Termo e glob
   vão agora nas duas formas Unicode (NFC e NFD).

## Conferido contra a origem

`CODIGO-AGULHA-7731`: 57 no SFS = 57 na origem. `AGULHA-` nos casos de borda: as
diferenças são todas explicadas — `laudo.txt` fundido com `Laudo.txt` pelo NAS
case-insensitive (não existe lá); `.oculto/` fora por padrão (pasta oculta);
`utf16_bom.txt` achado pelo SFS e não pelo `grep` da origem (o grep não lê UTF-16).

## Fica em aberto

- `fatura_‮txt.exe` aparece na tela como "fatura_exe.txt" (RTL override) e
  `zero​width.txt` não é achado por "zerowidth": caracteres invisíveis no
  nome — item de exibição/busca próprio, decisão do Rodrigo.
- A busca por nome no NAS inteiro leva ~30 s e a de conteúdo ~110 s pela tailnet
  (SMB, latência real) — esperado, e o motivo da decisão "Rede fora de Todos os
  discos".
