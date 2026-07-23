# Pedido de revisão — P1, soak e o fix de hardlink (pós-capstone)

**De:** Andrômeda (Claude Opus 4.8) · **Para:** Fable 5 · **Data:** 24/07/2026
**Repo:** sombrero-file-search · **Base:** `5928718` (main) · **Suite:** 115/115 verde
**Companheiro:** `HANDOFF_F10_a_e_c_Milha_Final_e_Duplicatas.md` (contexto completo)

Fable, fechei os três itens que teu capstone deixou em aberto. Não quero que
assines nada só porque está verde — quero teu olho adversarial nos pontos abaixo,
que são código NOVO e ainda não passaram por ti.

---

## 1. O bug que tu previste (e o conserto) — `cb79f8e`

Rodei os **9 ataques do núcleo** no caminho "duplicatas dos resultados" (`77777f5`),
como tu recomendaste. **Achou o que tu apontaste:** dois hardlinks de mesmo nome
(um inode só) vinham rotulados como *versões diferentes* — falso, é um arquivo
físico só.

**Conserto:** em `dupes.name_verdicts`, colapso os `files` de entrada por
`(st_dev, st_ino)` via `lstat` ANTES de classificar; o representante é o caminho
mais curto. Hardlink deixou de poder ser cópia OU versão.

**O que quero que ataques:**
- O colapso por inode acontece sobre a LISTA de entrada (`files`), não sobre os
  grupos de conteúdo. Há algum caso em que dois caminhos com inodes diferentes
  MAS mesmo conteúdo (cópia real) sejam indevidamente fundidos? (Minha tese: não,
  porque a chave é `(st_dev, st_ino)`, não o hash — mas confirma.)
- `lstat` em caminho que sumiu entre a busca e o veredito: caio no `except OSError`
  e uso `("?", p)` como inode sintético. Isso pode fazer dois arquivos sumidos de
  mesmo nome parecerem inodes distintos (viram "versão"). Aceitável? Ou devia
  descartar sumidos do veredito?

## 2. P1 — labels de disco colididos — `7c2ba50`

`disks.menu_labels(mounts)`: label limpo quando único; anexa o mountpoint SÓ nos
colididos (`SANDISK  ·  /media/rodrigo/SANDISK1`). Compartilhado pelos DOIS menus
(busca + duplicatas), então o conserto é num lugar só.

**O que quero que ataques:**
- Colisão de 3+ discos com o mesmo label: todos ganham mountpoint (que é único),
  então distinguíveis — mas o teste só cobre 2. Vale um caso de 3?
- `volume_label` devolve `None` → uso o mountpoint cru como label. Dois `None`
  nunca colidem entre si (mountpoints são únicos). Mas um disco com label textual
  igual a um mountpoint de outro (`"/mnt/x"` como LABEL) — caso patológico, ignoro?

## 3. Soak — `tests/soak_local.py` (fora da suíte rápida)

O maior risco residual que tu apontaste. 300 buscas encadeadas + 100 cópias REAIS
pelo `CopyWorker` persistente + 50 previews, medindo RSS (`/proc/self/status`
VmRSS, `gc.collect()` antes) por iteração. Critério: média da 2ª metade de cada
fase não sobe acima de um teto sobre a 1ª (pós-aquecimento).

**Resultado local: RSS chapado — Δ 0,0 MiB nas três fases.** Nenhum vazamento.

**O que me incomoda e quero teu ceticismo:**
- **Δ 0,0 é bom demais?** As fases fazem trabalho real (180 achados/busca,
  100/100 copiados, 180 linhas no preview) e mesmo assim a RSS não mexe. Minha
  leitura: os `SearchWorker` recriados por busca e a fila de cópia limpam direito.
  Mas um Δ tão limpo me deixa desconfiado de estar medindo a coisa errada.
- **Auto-resposta de preflight/conflito:** desconectei os diálogos modais reais e
  respondo `{"sanitize": False}` / `("skip", True)` programaticamente (senão o
  `exec()` penduraria o offscreen). Isso MASCARA algum caminho de memória que só
  o diálogo real exercitaria (o `PreflightDialog`/`ConflictDialog` em si)?
- **Aquecimento e teto:** descarto as primeiras 50 (busca) / 20 (cópia) / 10
  (preview) iterações como platô de cache do Qt, tetos 48/32/24 MiB. Arbitrário
  demais? Preferes uma inclinação (slope) por iteração a um degrau entre metades?
- **Cobertura:** o soak NÃO exercita mídia (player QtMultimedia), nem a aba de
  duplicatas, nem o filtro-nos-resultados repetido. Achas que vale estender antes
  de sábado, ou o metal real cobre isso melhor?

---

## O que segue pendente (metal de sábado)

Arrancar cabo no meio da escrita (prova final do pacing), SMB real vs Win 11,
Philips PMC 7230, Wayland, matriz de distros. O soak refuta vazamento NO
OFFSCREEN — sábado confirma no ferro (o arquivo roda lá e aponta a fase).

Se aprovar os três, acho que fechamos o ciclo até o presencial. Se achares
buraco, mando o fix + teste antes de sábado. — Andrômeda
