# LoCoMo Dataset

LoCoMo (Long Context Memory) — multi-session conversations between two people, with QA pairs that probe single-hop, temporal, open-domain, multi-hop, and adversarial recall.

- **Paper:** *Evaluating Very Long-Term Conversational Memory of LLM Agents* (ACL 2024) — https://aclanthology.org/2024.acl-long.747.pdf
- **GitHub:** https://github.com/snap-research/locomo
- **License:** see upstream repo for terms before redistribution.

## Files

```
src/datasets/locomo/
├── loader.py        # LoCoMoLoader (custom JSON loader)
├── schemas.py       # pydantic models: LoCoMoSample, LoCoMoQA, LoCoMoTurn
├── data/
│   └── locomo10.json  # gitignored; 10 samples × ~150–200 QA each
└── README.md
```

`scripts/download_data.py --dataset locomo` verifies the file is present (M1 does not download; the file is shipped with the repo for now). If the upstream license allows hosted distribution, replace the verifier with a real downloader.

## Sample shape

Each sample carries `sample_id`, a `qa` array (each QA has `question`, `answer` or `adversarial_answer`, `evidence`, `category`), and a `conversation` dict with `speaker_a`, `speaker_b`, and `session_{i}` / `session_{i}_date_time` keys for each session.

## Question categories

| ID | Name          | Notes |
|----|---------------|-------|
| 1  | single_hop    | Multi-answer factual; partial-F1 scoring per sub-answer |
| 2  | temporal      | Date/time reasoning; prompt asks for approximate date |
| 3  | open_domain   | Open-domain Q; uses first `;`-separated answer for scoring |
| 4  | multi_hop     | Multi-hop reasoning |
| 5  | adversarial   | Hallucination probe; prompt presented as two-option multiple choice |
