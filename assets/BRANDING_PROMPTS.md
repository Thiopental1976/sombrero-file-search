# Linux File Search — prompts de identidade visual (para gerador de imagens por IA)

Prompts prontos para colar num gerador (Midjourney, DALL·E 3 / ChatGPT, Flux,
Ideogram, Stable Diffusion). **Os prompts em si estão em inglês** — é o idioma em
que esses modelos rendem melhor. O texto ao redor é a explicação em pt-BR.

Tudo aqui parte da **identidade que o app já tem**, para o logo novo combinar com
a interface e o ícone atual:

| elemento | valor |
|---|---|
| Fundo | azul-marinho escuro, gradiente `#1b2740 → #0d1420` |
| Acento (gradiente) | azul → teal, `#5AA9FF → #37E0C8` |
| Acento sólido (UI) | `#4F9CF9` |
| Verde/âmbar/vermelho | `#34D399` / `#F0A35E` / `#F87171` |
| Forma do ícone | *squircle* (quadrado de cantos bem arredondados, ~20% de raio) |
| Símbolo | lupa sobre "linhas de arquivo/texto" |
| Espírito | nativo do Linux, sem índice, resultados **ao vivo**, rápido, cuidadoso com o hardware |

> Dica geral: gere o **logo em fundo transparente ou sólido** (para virar ícone) e
> a **imagem de divulgação em 16:9** (para GitHub social preview, site, post).
> Ideogram e DALL·E 3 acertam texto legível; Midjourney/Flux dão o melhor acabamento
> mas erram letras — para essas, gere **sem texto** e escreva o nome depois.

---

## 1) LOGO / ícone do app

### 1a. Prompt principal (Midjourney / Flux / SDXL) — SEM texto
```
App icon for a Linux file-search utility, modern flat design with subtle depth.
A rounded-square (squircle) tile with a deep navy-blue gradient background
(#1B2740 to #0D1420). Centered emblem: a clean magnifying glass overlapping three
horizontal "text lines" that suggest a document, the glass and lines drawn in a
smooth blue-to-teal gradient stroke (#5AA9FF to #37E0C8). Inside the lens, a faint
teal glow and a tiny live "pulse" spark hinting at real-time results. Crisp
geometric line-art, even stroke weight, generous padding, high contrast, legible
at 32px. Soft inner shadow, no photorealism, no clutter, no text.
--style raw --v 6
```

### 1b. Prompt principal (DALL·E 3 / ChatGPT / Ideogram) — pode incluir "LFS"
```
Design a modern app icon for "Linux File Search". A squircle tile with a deep
navy-blue diagonal gradient (dark #1B2740 to near-black #0D1420) and a thin subtle
border. In the center, a minimalist magnifying glass overlapping three horizontal
document lines, all drawn as clean rounded strokes in a blue-to-teal gradient
(#5AA9FF to #37E0C8). A soft teal glow fills the lens. Optional small monogram
"LFS" in a geometric sans-serif at the bottom. Flat vector look, crisp edges,
strong contrast, readable at small sizes, balanced negative space. No photo
realism, no gradients on the background other than the navy one, no busy details.
```

### 1c. Variação com pinguim (aceno ao Linux, discreto)
```
…same as above, but replace the plain magnifying glass with a magnifying glass
whose lens subtly frames a tiny, minimalist penguin silhouette rendered in the
same teal, as a friendly nod to Linux. Keep it geometric and clean, still legible
at small sizes.
```
> ⚠️ **Cuidado de marca:** o pinguim deve ser uma **silhueta ORIGINAL e genérica**,
> NÃO o Tux (o mascote oficial, de autoria de Larry Ewing). Não reproduza o Tux nem
> imite a sua pose/cor. Ver a seção 4. Na dúvida, use a versão sem pinguim (1a/1b).

### Negative prompt (para SD/Flux)
```
text artifacts, misspelled words, watermark, jpeg noise, photorealistic, 3D bevel
skeuomorphism, drop shadows overload, glossy web-2.0 button, stock photo, cluttered,
low contrast, gradient background other than navy, generic folder icon
```

---

## 2) IMAGEM DE DIVULGAÇÃO / hero (16:9)

Para o *social preview* do GitHub (1280×640), topo de README, ou post de anúncio.

### 2a. Hero "produto + conceito" (Midjourney / Flux)
```
Wide 16:9 hero banner for a native Linux file-search app called "Linux File Search".
Left side: a sleek dark-theme desktop app window (deep navy UI, #0E1217 panels,
blue #4F9CF9 accents) showing a live list of search results streaming in, a search
bar, and small file/preview panels — clean, modern, flat UI, slight perspective.
Right side: an oversized magnifying glass with a blue-to-teal gradient rim
(#5AA9FF to #37E0C8) sweeping over a field of translucent document cards and file
rows that light up as they match, conveying real-time search across huge disks.
Dark elegant background with soft teal glow and subtle grid. Cinematic, crisp,
high detail, tech product aesthetic, plenty of empty space on one side for a
headline. No visible body text inside the UI, no logos of other brands.
--ar 16:9 --v 6
```

### 2b. Hero minimalista (bom para texto por cima depois)
```
Minimalist 16:9 tech banner, deep navy gradient background (#1B2740 to #0D1420)
with a faint dot grid. A single large magnifying glass drawn in clean blue-to-teal
gradient line-art (#5AA9FF to #37E0C8), floating over a few horizontal "file rows"
that fade toward the edges; one row inside the lens is highlighted in teal with a
soft glow, suggesting an instant match. Lots of negative space on the left for a
title. Flat, elegant, modern, no photorealism, no text.
--ar 16:9
```

### 2c. Detalhe temático (opcional): consciência de hardware
```
…optional variant: below the file rows, hint at storage — minimalist line-art of a
stack of hard drives and a USB stick, one drive gently pulsing, to convey that the
tool is careful with slow SMR disks and removable media. Keep it subtle and in the
same teal line style.
```

---

## 4) Evitar conflitos de copyright e marca (importante)

Um logo original é seu; um que copia obra/marca de terceiros vira dor de cabeça
jurídica e pode ser barrado em lojas de app e no próprio GitHub. Regras práticas:

- **"Linux" é marca registrada** (de Linus Torvalds / Linux Mark Institute). Usar
  **"for Linux" / "Linux File Search" de forma descritiva** é uso nominativo,
  legítimo. O que NÃO fazer: estilizar como o logotipo oficial do Linux, usar o
  Tux como se fosse o logo do produto, ou dar a entender **endosso/afiliação**
  oficial. Um rodapé "not affiliated with the Linux Foundation" resolve dúvidas.
- **Tux (o pinguim):** é arte de Larry Ewing, com uma licença que **exige
  atribuição**. Para um logo de produto, o mais limpo é **NÃO usar o Tux** e, se
  quiser um pinguim, criar uma **silhueta original** bem diferente. (Preferir 1a/1b.)
- **Não imitar apps existentes:** nada de evocar o ícone/identidade do *Everything*,
  *Agent Ransack / FileLocator Pro*, *UltraSearch*, do **Finder** do macOS, do
  Windows Search, etc. Inspiração conceitual (lupa = busca) é livre; **cópia de um
  logo específico não é.** No prompt, evite "in the style of <app/marca>".
- **Nada de logos de terceiros na arte:** ao gerar o hero, peça telas **genéricas**,
  sem marcas, sem ícones de outras empresas, sem capturas de sites reais.
- **Evite "no estilo de <artista vivo>":** além de questionável, não agrega. Peça
  "modern flat vector", "geometric line-art" — descrições de estilo, não nomes.
- **Fontes com licença livre:** se for compor o nome, use tipografia **SIL OFL /
  Apache** (Inter, Montserrat, Manrope, Source Sans). Fontes do sistema Windows/
  Apple (Helvetica, Segoe UI, SF Pro) **não** podem ser embarcadas/redistribuídas.
- **Saída de IA:** ainda é área cinzenta jurídica em alguns países, mas o risco cai
  muito quando a arte é **genérica e original** (sem marcas, sem personagens, sem
  estilo de artista nomeado) — que é exatamente o que estes prompts pedem.
- **Coerência com a GPL do projeto:** o logo pode ter licença própria. Uma escolha
  comum e segura é liberar o logo em **CC BY-SA 4.0** (ou deixá-lo "todos os
  direitos reservados" como marca do projeto). Registre isso num `assets/LICENSE`
  quando a arte final existir.

> Resumo: **lupa + linhas de arquivo + paleta navy/teal, tudo desenhado do zero.**
> Sem Tux, sem logo oficial do Linux, sem imitar outro app. Aí não há conflito.

---

## 3) Como usar o resultado

- **Ícone final:** peça (ou recorte) em **1024×1024 PNG com fundo transparente**;
  dá para reduzir para 256/128/64/48 (os tamanhos que o app já usa em `assets/`).
  Se vier com fundo navy sólido, também serve — o ícone atual é assim.
- **Social preview do GitHub:** *Settings → Social preview*, imagem **1280×640**.
- **Se o texto sair torto** (comum em Midjourney/Flux): gere **sem texto** e componha
  o nome depois num editor, na fonte que preferir (uma *geometric sans* como Inter,
  Montserrat ou Manrope combina com a UI).
- **Mantenha a paleta:** navy + azul→teal. É o que amarra o logo à interface e ao
  ícone que já está no repositório (`assets/icon.svg`).

---

*Estes prompts são material de projeto (identidade visual). O código do app não
depende deles; servem para gerar as imagens de divulgação.*
