# Baselines

Systems under test — Harmix's Pam ([manager.harmix.ai](https://manager.harmix.ai)) and each memory product we compare it against. Every baseline gets a card in [[system-cards]] regardless of whether it's open source, hosted API, or Pam itself.

- [System Cards](./system-cards.md)

**Note on results.** Results are not stored in `.memory-bank/`. Per-run records live in MongoDB (`<dataset>_results`); rendered reports live under `reports/<exp-name>/` and are regenerated on demand by `scripts/generate_report.py`.
