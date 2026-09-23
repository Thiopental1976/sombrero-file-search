# docs/

Everything a *user* needs is in the repository root: [README](../README.md) and
[MANUAL](../MANUAL.md). This folder is for **contributors and reviewers**.

English is the source language of this project. Where a Portuguese version exists, it is a
translation kept alongside (`*.pt-BR.md`) — if the two disagree, the English one is canonical.

| Where | What it is |
|---|---|
| [`TECHNICAL_DOCUMENTATION.md`](TECHNICAL_DOCUMENTATION.md) | Architecture, every module, the incompleteness funnel, phases F9–F12 and the latest review. **Start here** to understand the code. ([pt-BR](TECHNICAL_DOCUMENTATION.pt-BR.md)) |
| [`FUNNEL_CONTRACT.md`](FUNNEL_CONTRACT.md) | The contract for scripts: every `--json` `reason`, which ones are fatal, exit codes 0/1/2. ([pt-BR](CONTRATO_FUNIL.pt-BR.md)) |
| [`campo/`](campo/) | Field tests on real hardware and networks, with the raw evidence (`--json`, kernel log): the Bazzite install (Jul 2026) and the TrueNAS NAS over a Tailscale link (Sep 2026). |
| [`historico/`](historico/) | The development diary: initial briefing, handoffs and review requests between phases, verdicts. **In Portuguese, by design**: these are records of the moment, exchanged as the work happened, and translating them would rewrite history. Useful to understand **why** a decision was made; the current code is the reference for **how** it ended up (where they disagree, the code wins — see §23 of the technical documentation). |

The detailed history of each change is also in the commit messages (`git log`), which carry
the measurements taken before and after each fix.
