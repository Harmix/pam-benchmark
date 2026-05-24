# Licensing & Data Handling

## Licensing

| Artifact | License | Internal (Harmix) Use | External Sharing |
|---|---|---|---|
| Code (this repo) | Harmix-internal | ✓ | not released externally |
| LoCoMo data (`src/datasets/locomo/data/locomo10.json`) | upstream — see https://github.com/snap-research/locomo | ✓ for evaluation | redistribute via upstream link only |
| Model outputs / Mongo records | Harmix-internal | ✓ | gated — see external-claim policy below |

## Per-baseline vendor terms (vendor-ToS check)

| Baseline | Vendor | Can we run them on our data? | Can we publish comparison numbers? | Source |
|---|---|---|---|---|
| gpt-4-turbo | OpenAI | Yes | Yes — subject to OpenAI Brand Guidelines + Usage Policies | https://openai.com/policies/usage-policies |
| Pam | Harmix ([manager.harmix.ai](https://manager.harmix.ai)) | Yes | Yes | n/a |
| Honcho / Supermemory / mem0 / Zep (M4) | various | TBD per vendor | TBD per vendor — check before publishing | per-vendor ToS |

> **Action before any external comparison number:** confirm each named vendor's ToS allows published benchmark comparisons. Some vendors expressly forbid them. Update this table before publishing.

## PII / sensitive content

- LoCoMo is synthetic; no PII risk.
- Customer-derived datasets (e.g. MEMTRACK when wired up) must pass a PII redaction step + an access-control review before being added to this benchmark. Pam itself is SOC2- and GDPR-aligned in production; the benchmark inherits those constraints.

## External-claim policy

A benchmark number leaves Harmix only after:

1. **Vendor-ToS check** (above) confirms the comparison is permitted.
2. **Sign-off:** the Mongo doc and the report PDF/HTML are linked in a PR/Slack thread approved by the engineering lead.
3. **Context attached:** any external claim must include `exp_name`, `seed(s)`, image digest (or commit hash), date of run, judge model, and dispersion (single-seed M1 numbers are NOT publishable externally).
4. **Audit trail:** every external use of a number — slide deck, customer email, content on [manager.harmix.ai](https://manager.harmix.ai), analyst briefing — is logged in a Harmix Slack channel so we can re-issue or retract if upstream APIs drift.
