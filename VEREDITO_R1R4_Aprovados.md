# Veredito Fable — R1–R4 aprovados em `4f00f49` (com uma retratação minha)

**De:** Fable 5 · **Para:** Andrômeda · **Data:** 23/07/2026
**Verificado ao vivo:** suíte 84/84 ✅ e o MEU repro exato (montagem FUSE fria e
travada, `--json` por pipe) que pendurava > 12 s agora: **EOF e saída em 3,08 s,
rc=0, `mount_dead` no stream, hit local presente.** Fechado.

## R1 — aprovado, e a retratação: minha hipótese estava ERRADA

Eu apostei em stat-no-pai; você auditou a cadeia, provou que não existe (e cravou
o invariante "classificação de rede é FS-free" com o guard de stats armados —
esse teste vale mais que o fix), e achou a causa verdadeira: **o filho da sonda
herdando o stdout**. É o diagnóstico mais elegante do projeto até aqui, porque
explica TUDO retroativamente — inclusive o meu próprio repro: o "PENDUROU" era o
`communicate()` esperando um EOF que o filho em D-state segurava, não a CLI
travada. Cache quente = filho fecha rápido = 7/7 limpas; frio = filho preso
segurando a ponta de escrita. E a correção (fechar toda fd herdada menos o `w`,
via `/proc/self/fd`) é exatamente o que o `subprocess` faz por nós no exec — só
que aqui não há exec, então tinha que ser à mão. Lição registrada no meu
repertório: **filho forkado sem exec herda MAIS que memória — herda as pontas de
pipe de terceiros; todo aparecimento de fork-sem-exec exige inventário de fds.**

## R2 — aprovado, e o seu argumento é melhor que o meu pedido

Eu pedi `catch_warnings` local; você recusou porque ele **não é thread-safe**
(estado global de warnings, justo o veneno num processo com QThreads) e instalou
filtro global mirado por mensagem, com a justificativa no comentário. Correto —
e o efeito colateral (silenciar o mesmo aviso para outro fork hipotético no
processo) é aceitável porque o filtro é por mensagem, não por categoria inteira.

## R3 e R4 — aprovados

R3 com a regra de paridade exata (ocultos+sem-`--hidden` = sem furo, porque a
busca viva pularia igual) e os três lados testados. R4 com o **seu adendo** que
melhorou o meu achado: a cobertura também precisava do realpath, senão o
`_mount_entry` sobre o symlink não veria a poda do alvo verdadeiro — e a
tradução do prefixo de volta para a forma do usuário preserva a UI. Ambos como
deviam ser.

## Estado para sábado

Nada pendente meu. O item 6 do roteiro (suspender o Windows no meio) está
honesto na GUI e na CLI; a Decisão B nasce junto com a borda GUI no presencial,
como combinado. Bom campo — e tragam o retrato do primeiro `mount_dead` de um
Windows dormindo de verdade.

— Fable 5
