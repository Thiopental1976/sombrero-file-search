# docs/

**English** — Everything a *user* needs is in the repository root: [README](../README.md) and
[MANUAL](../MANUAL.md). This folder is for **contributors and reviewers**; most of it is written
in Portuguese.

**Português** — Tudo o que o *usuário* precisa está na raiz do repositório:
[README](../README.pt-BR.md) e [MANUAL](../MANUAL.pt-BR.md). Esta pasta é para quem vai
**contribuir ou revisar** o código.

| Onde | O que é |
|---|---|
| [`DOCUMENTACAO_TECNICA.md`](DOCUMENTACAO_TECNICA.md) | A documentação técnica: arquitetura, cada módulo, o funil de incompletude, as fases F9–F12 e a revisão mais recente. **Comece por aqui** para entender o código. |
| [`campo/`](campo/) | Testes de campo com hardware e redes reais, com a evidência bruta (`--json`, log do kernel): a instalação no Bazzite (jul/2026) e o NAS TrueNAS pela tailnet (set/2026). |
| [`historico/`](historico/) | O diário de desenvolvimento: briefing inicial, handoffs e pedidos de revisão entre as fases, vereditos. Útil para entender **por que** uma decisão foi tomada; o código atual é a referência de **como** ela ficou (onde divergem, o código manda — ver §23 da documentação técnica). |

O histórico detalhado de cada mudança está também nas mensagens de commit (`git log`), que
trazem as medições feitas antes e depois de cada conserto.
