# Sombrero File Search — identidade visual (prompts para IA)

Guia da identidade visual do app e prompts para gerar logo e imagem de divulgação
num gerador de imagens (Grok, DALL·E 3, Midjourney, Flux, Ideogram, SDXL).

**Motivo central:** a **Galáxia Sombrero (Messier 104)** — disco visto quase de
perfil, bojo central brilhante e a faixa escura de poeira cortando o meio —
enquadrada pela **lente de uma lupa** (busca). É o que já está desenhado no
`icon.svg` do projeto; os prompts abaixo pedem a mesma coisa em alta resolução.

| elemento | valor |
|---|---|
| Fundo | azul-marinho escuro, gradiente `#1B2740 → #0D1420` |
| Acento (gradiente) | azul → teal, `#5AA9FF → #37E0C8` |
| Acento sólido (UI) | `#4F9CF9` |
| Verde/âmbar/vermelho | `#34D399` / `#F0A35E` / `#F87171` |
| Forma do ícone | *squircle* (quadrado de cantos bem arredondados, ~20% de raio) |
| Símbolo | **galáxia Sombrero dentro da lente de uma lupa** |
| Espírito | nativo do Linux, sem índice, resultados **ao vivo**, rápido, cuidadoso com o hardware |

> **Prontos para colar (texto puro, sem markdown):**
> **[`prompt_icone.txt`](prompt_icone.txt)** (ícone) e
> **[`prompt_fundo.txt`](prompt_fundo.txt)** (fundo/hero).
> O passo a passo pro Grok está em **[`PROMPTS_LOGO_E_FUNDO.md`](PROMPTS_LOGO_E_FUNDO.md)**.

---

## Por que a galáxia Sombrero

O nome nasceu da busca por uma galáxia **curta e conhecida**, sem colisão de marca
no nicho de buscadores de arquivo (ver a nota de nomes no repositório). A Sombrero
é, além de icônica, um presente de design: o bojo brilhante sobre a faixa escura
lembra um olho — ou um chapéu de aba larga visto de perfil — e cai perfeitamente
dentro de uma lente. "Buscar" + "Sombrero" numa só figura.

---

## Regras de geração (todos os modelos)

- **Gere arte ORIGINAL**, não uma astrofoto real recolorida (ver copyright abaixo).
- Mantenha a **paleta navy + azul→teal**; é o que amarra o logo à interface.
- Para o ícone: **quadrado 1:1**, fundo transparente ou navy sólido, legível a 32 px.
- Para o hero: **16:9**, com metade vazia para o título depois.
- **Sem texto** quando o modelo erra letras (Midjourney/Flux) — componha o nome à parte.
- **Sem** Tux, sem logo oficial do Linux, sem imitar ícone de outro buscador,
  sem logos de terceiros na cena.

---

## Copyright e marca (importante)

Um logo original é seu; um que copia obra/marca de terceiros vira dor de cabeça
jurídica e pode ser barrado em lojas de app e no próprio GitHub.

- **Arte gerada e original** é o caminho seguro. **Não** use uma astrofoto real do
  M104 como logo sem checar a licença: imagens do **Hubble/NASA** costumam ser de
  uso livre, mas as de **ESO e observatórios** têm licença própria (muitas
  **CC BY**, que **exige crédito**). Gerar do zero evita o problema.
- **"Sombrero"** é palavra comum (o chapéu, a galáxia); o produto se distingue como
  *"Sombrero File Search"*. Não imite o ícone/identidade de *Everything*,
  *Agent Ransack / FileLocator Pro*, *UltraSearch*, do **Finder** ou do Windows
  Search. Inspiração conceitual (lupa = busca) é livre; cópia de um logo, não.
- **"Linux" é marca registrada.** Usar **"for Linux" / "native Linux"** de forma
  descritiva é uso nominativo legítimo. NÃO estilizar como o logotipo oficial do
  Linux, NÃO usar o **Tux** (arte de Larry Ewing, exige atribuição), NÃO sugerir
  endosso oficial. Um rodapé "not affiliated with the Linux Foundation" tira dúvida.
- **Fontes de licença livre** ao compor o nome: SIL OFL / Apache (Inter, Montserrat,
  Manrope, Source Sans). Fontes de sistema (Segoe UI, SF Pro, Helvetica) **não**
  podem ser embarcadas/redistribuídas.
- **Licença do logo:** o código é GPL-3.0-or-later, mas o logo pode ter licença
  própria. Uma escolha comum e segura é **CC BY-SA 4.0** (ou "todos os direitos
  reservados" como marca do projeto). Registre num `assets/LICENSE` quando a arte
  final existir.

> Resumo: **galáxia Sombrero dentro de uma lupa, paleta navy/teal, desenhada do
> zero.** Sem Tux, sem logo oficial do Linux, sem imitar outro app. Aí não há conflito.

---

## Como usar o resultado

- **Ícone final:** 1024×1024 PNG (transparente ou navy sólido); reduz para
  256/128/64/48, os tamanhos que o app usa em `assets/`.
- **Social preview do GitHub:** *Settings → Social preview*, imagem **1280×640**.
- **Se o texto sair torto:** gere sem texto e componha o nome num editor, numa
  *geometric sans* (Inter/Montserrat/Manrope) que combine com a UI.

*Material de projeto (identidade visual). O código do app não depende dele.*
