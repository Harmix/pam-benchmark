# LoCoMo Dataset

The LoCoMo (Long Context Memory) benchmark is designed to evaluate the long-context memory capabilities of Large Language Models (LLMs) through question answering tasks over conversation histories.

## Dataset Structure

```
datasets/locomo/
├── data/
│   └── locomo10.json      # Main dataset file with conversations and QA pairs
├── registry.json          # Dataset registry for Harbor integration
└── README.md              # This file
```

## Data Format

The `locomo10.json` file contains samples with the following structure:

```json
{
  "sample_id": "unique_identifier",
  "qa": [
    {
      "question": "Question about the conversation",
      "answer": "Expected answer",
      "evidence": ["D1:3", "D2:5"],
      "category": 1
    }
  ],
  "conversation": [...]
}
```

### Question Categories

- **Category 1**: Single-hop factual questions
- **Category 2**: Temporal reasoning questions
- **Category 3**: Multi-hop reasoning questions

## Usage

This dataset is used with the `tasks/locomo` task for evaluating LLM memory capabilities.

## Reference

For more information about LoCoMo, see the original research materials in the `locomo/` directory.
