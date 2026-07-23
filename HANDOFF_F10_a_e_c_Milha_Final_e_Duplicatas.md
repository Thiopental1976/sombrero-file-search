# Handoff — F10a + F10c aplicados (A milha final humana + Caçador de duplicatas)

**De:** Andrômeda (Claude Opus 4.8) · **Para:** Fable 5
**Base:** desenho `DESENHO_F10_Milha_Final_Humana_e_Duplicatas.md`
**Repo:** sombrero-file-search · **Suite:** 99/99 verde · tudo commitado **e** empurrado.

---

## O que ficou pronto

### F10a — A milha final humana

**#1 Filtro-nos-resultados** (já estava; núcleo + GUI)
- `c200efd` núcleo: predicado puro, sem I/O (`resultfilter.py`).
- `f428edf` GUI: caixa de filtro + **discos por label** (não mountpoint) na caixa de seleção.

**#2 Painel de narrativa da busca — NO ALTO da GUI, legível** (pedido explícito do Rodrigo:
"barras e informações no alto, legíveis, não fonte miúda no fundo")
- `3051ea5` engine: emite `root_scanning` / `root_skipped` / `root_done` por raiz.
- `889507c` GUI: `QFrame#narrative` entre os chips e os resultados. Cabeçalho grande
  ("Varrendo 3/12 locais · 240 achados · 4s") + uma linha por raiz com bolinha colorida
  (verde=pronto, vermelho=inacessível, cor de acento=varrendo agora). Montagem de rede
  morta vira **linha vermelha, não popup**. Estado é por-aba; um widget só renderiza a
  aba visível.

**#3 Teclado de ponta a ponta** (`fff7f9e`)
- Esc inteligente (cancela busca / limpa filtro), ↑/↓ histórico no campo de nome,
  Ctrl+F filtro, Ctrl+L caminho, F3/Shift+F3 navegam matches no preview, Ctrl+R repete.
- MANUAL.md / MANUAL.pt-BR.md com as tabelas completas; refs velhas de F3/Ctrl+L
  corrigidas em DOCUMENTACAO_TECNICA e README.

### F10c — Caçador de duplicatas NATIVO

**A linha vermelha primeiro:** o SFS **acha, mostra e exporta** duplicatas — **nunca apaga**.
Nem com confirmação, nem "só a lixeira". `lfs/dupes.py` não tem função de remoção e não
deve ganhar uma. Recusa escrita no README ao lado das outras (`49ffb70`).

**Núcleo** (`9340c65`) — `lfs/dupes.py`, **código próprio do SFS** (não dependência; o
motor do cedro `dedup_layer1.py` serve só de **oráculo** nos testes de paridade):
- Estágio 0 — identidade física por `(st_dev, st_ino)`: **hardlinks são UM candidato,
  não duplicatas**. Symlinks fora. Tamanho 0 fora por padrão.
- Estágio 1 — tamanho (só grupos com ≥2).
- Estágio 2 — hash de cabeça BLAKE2b 64 KiB.
- Estágio 3 — hash completo BLAKE2b, **sequencial por dispositivo** (ordena por st_dev —
  disciplina SMR), `fadvise DONTNEED`, cancel por bloco, progresso honesto em bytes.
- Grupos ordenados por bytes desperdiçados. `export()` CSV/JSON com `surrogateescape`
  (nomes hostis do acervo não estouram).

**GUI** (`9bb32b7`) — janela *Duplicatas…* na toolbar (não-modal):
- Campos de raízes (semeados), incluir-vazios, tamanho-mínimo; Varrer/Cancelar.
- Cabeçalho grande + barra de progresso; árvore [Arquivo / Tamanho / **Disco por label**].
- Export CSV / Export JSON. Fechar cancela o worker.

**9 testes novos** (suite 90→99), incluindo:
- `test_dupes_hardlink_is_not_duplicate`, `..._across_devices_groups` (monkeypatch st_dev),
  `..._cancel_leaves_no_state`, `..._no_delete_api` (guarda AST: nada de remove/unlink/
  rmtree/rename no módulo), `..._export_csv_json_hostile_names`,
  `..._parity_with_oracle` (carrega dedup_layer1.py e confirma grupos idênticos).

---

## Decisões que quero teu olhar

1. **Entrada da GUI do F10c:** o desenho sugeria uma **aba "Duplicatas" embutida**. Fiz
   como **janela não-modal** (mais seguro no QTabWidget centrado em SearchTab). Fácil de
   promover a aba na sessão presencial se o Rodrigo preferir — o worker e o render já são
   independentes.

2. **Nada mais.** F10a e F10c estão fechados e testados.

## O que falta (F10b — não comecei)

- **#4** pós-cópia "Copiado e sincronizado — seguro remover" + botão Ejetar + notificação
  (em `caps.removable`). O worker persistente do A6 já existe parcial.
- **#5** fila de cópia persistente no config.json (snapshot por transição, retomar após
  kill -9).

Presencial de sábado: borda/visual da GUI, SMB real contra o Win11 na LAN, checklist Philips.
