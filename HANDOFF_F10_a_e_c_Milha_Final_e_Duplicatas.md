# Handoff — F10 INTEIRO aplicado (A milha final humana + Duplicatas)

**De:** Andrômeda (Claude Opus 4.8) · **Para:** Fable 5
**Base:** desenho `DESENHO_F10_Milha_Final_Humana_e_Duplicatas.md`
**Repo:** sombrero-file-search · **Suite:** 103/103 verde · tudo commitado **e** empurrado.

> **Novidades desde a v1 deste handoff:** (1) o **F10b #4 e #5** entraram (seção própria
> abaixo); (2) o caçador de duplicatas foi **promovido de janela para ABA embutida** — a
> antiga decisão #1 está resolvida. Agora o F10 está **completo — a, b, c** — e testado
> (103/103), com o F10c na forma final que teu desenho pediu.

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

### F10b — confiança (a parte que fideliza)

**#6 humane.py** (`e6aff54`, já era) — nenhum errno cru chega à tela; guarda AST no
`app.py` garante que toda string de erro passa por `humane.human_error`.

**#4 O momento depois da barra: "pode remover com segurança"** (`ed5cc0e`)
- Cópia concluída para disco **removível** → a barra **não some**: vira
  *"Copiado e sincronizado — seguro remover"* com botão **⏏ Ejetar** ao lado. A
  promessa é verdadeira — o ATOMIC faz `fsync` por arquivo.
- Ejetar usa `gio mount -e` **ou** `udisksctl power-off -b <dev>`, o que existir;
  sem nenhum dos dois, o botão nem aparece (sem dependência nova). O comando é
  `disks.eject_command(mp, dev, which=…)` — **puro, `which` injetável** (testado).
- Cópia > 30 s numa janela minimizada/inativa → **notificação de desktop**
  (`notify-send` ou bandeja Qt, usa-se-existir).

**#5 Fila de cópia sobrevive ao fechamento** (`ed5cc0e`)
- Jobs pendentes + o interrompido persistidos em `config.json` a cada **transição**
  de job (não por arquivo — barato). Módulo **puro** novo `lfs/copyjobs.py`
  (serializa/valida/snapshot/pending/clear).
- Na abertura: *"Você tinha N cópias pendentes — retomar?"* [Retomar] [Descartar].
- Retomada **idempotente** por desenho: a escrita ATOMIC garante que concluído vira
  **conflito** (a política decide; padrão da GUI = Pular) e `.sombrero-part` órfão é
  lixo reconhecível. Destino não montado é barrado no preflight → o job fica
  pendente, não some.

**4 testes novos** (suite 99→103):
- `test_eject_command_prefers_gio_then_udisks` (gio → udisksctl → None, `which` fake);
- `test_copyjobs_snapshot_roundtrip`, `test_copyjobs_rejects_malformed`;
- `test_copyjobs_resume_is_idempotent` — **o teste do `kill -9`**: 2 jobs, "morte" no
  meio (um arquivo já copiado + um `.part` órfão), reabrir e retomar → estado final
  **idêntico** ao de uma execução sem morte. Rodado no nível do `fileops.copy_to`,
  headless. Smoke offscreen confirmou a barra "seguro remover" + Ejetar + o prompt de
  retomada lendo a fila do config.

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

**GUI — ABA embutida** (`9bb32b7` como janela, promovida a aba em commit desta
sessão): o app ganhou um **workspace de topo com duas páginas isoladas** —
*🔍 Buscar* (a busca inteira: formulário, abas de resultado, preview, cópia) e
*⧉ Duplicatas* (o caçador). É a "aba própria com os mesmos chips de caminho" que teu
desenho pediu, **resolvendo a decisão #1 da versão anterior deste handoff** (eu tinha
feito como janela não-modal e deixado para promover no presencial — o Rodrigo pediu
para fazer já).
- Campos de raízes (semeados a partir da busca), incluir-vazios, tamanho-mínimo;
  Varrer/Cancelar. Cabeçalho grande + barra de progresso; árvore
  [Arquivo / Tamanho / **Disco por label**]. Export CSV / Export JSON.
- **Por que duas páginas e não a aba de duplicatas dentro de `self.tabs`:** há dezenas
  de acessos a `self.tab.*` (tabela, modelo, formulário, worker) que só fazem sentido
  numa aba de BUSCA; uma aba de duplicatas ali dentro os quebraria. Páginas separadas
  dão isolamento total, cada modalidade com entradas e ciclo de vida próprios.
- `DuplicatesWindow(QDialog)` → `DuplicatesPanel(QWidget)`: saiu título/tamanho-mínimo/
  botão *Close*; entrou `seed()` (semeia só se vazio — não pisa no que o usuário digitou)
  e `shutdown()` (a janela principal aborta o hash em voo no `closeEvent`). O botão
  *Duplicatas…* da toolbar agora **pula para a aba** e semeia os caminhos da busca.

**9 testes novos** (suite 90→99), incluindo:
- `test_dupes_hardlink_is_not_duplicate`, `..._across_devices_groups` (monkeypatch st_dev),
  `..._cancel_leaves_no_state`, `..._no_delete_api` (guarda AST: nada de remove/unlink/
  rmtree/rename no módulo), `..._export_csv_json_hostile_names`,
  `..._parity_with_oracle` (carrega dedup_layer1.py e confirma grupos idênticos).

---

## Decisões que quero teu olhar

1. ✅ **RESOLVIDA — Entrada da GUI do F10c:** era janela não-modal, virou **aba embutida**
   nesta sessão (o Rodrigo pediu para fazer já, não no presencial). Detalhes na subseção
   *GUI — ABA embutida* acima. A forma final é a que teu desenho pedia.

2. **Notificação de ejeção sem tray real:** no smoke offscreen usei `notify-send`/bandeja
   com fallback silencioso. No teu ambiente headless (cron), nenhum dos dois existe e a
   notificação simplesmente não sai — de propósito, é um extra e não um dever. Se quiser
   que ela apareça num log, é um `log()` a mais, me diz.

3. **Nada mais pendente no F10.** a, b e c fechados e testados (103/103).

## O que falta (fora do F10, pra sábado presencial)

- Borda/visual da GUI.
- **SMB real** contra o Win 11 na LAN (F9 — busca em rede de verdade).
- Checklist do Philips PMC 7230.
