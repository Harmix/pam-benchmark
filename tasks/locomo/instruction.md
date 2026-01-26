# LoCoMo Benchmark Task

This task evaluates the long-context memory capabilities of Large Language Models (LLMs) through question answering over extended conversation histories.

## Task Overview

The LoCoMo (Long Context Memory) benchmark tests an LLM's ability to:
1. Process and understand long multi-session conversations between two people
2. Answer questions that require recalling specific facts from the conversation
3. Handle temporal reasoning across conversation sessions
4. Perform multi-hop reasoning over conversation content

## Dataset Structure

The benchmark uses the `locomo10.json` dataset containing:
- **Conversations**: Multi-session dialogues with dates and speaker information
- **QA Pairs**: Questions with ground truth answers and evidence references

### Question Categories

- **Category 1**: Single-hop factual questions (multi-answer with partial F1 scoring)
- **Category 2**: Temporal reasoning questions (date/time related)
- **Category 3**: Open-domain questions
- **Category 4**: Multi-hop reasoning questions
- **Category 5**: Adversarial questions (testing for hallucination)

## Environment Setup

The environment includes:
- Python 3.11 with required ML/NLP packages
- NLTK for text processing
- OpenAI, Anthropic, and Google AI client libraries
- BERTScore and other evaluation metrics

## Task Execution Flow

1. **Data Loading**: Load conversation samples from `locomo10.json`
2. **Context Preparation**: Format conversations with dates and speaker information
3. **Question Processing**: Process questions in batches
4. **Answer Generation**: Generate answers using the specified LLM
5. **Evaluation**: Compute F1 scores against ground truth answers
6. **Statistics**: Generate aggregate accuracy by question category

## Supported Models

- **OpenAI**: gpt-4-turbo, gpt-3.5-turbo, gpt-3.5-turbo-16k
- **Anthropic**: claude-sonnet, claude-haiku
- **Google**: gemini-pro-1.0

## Expected Output

The task produces:
- `locomo10_qa.json`: Predictions with F1 scores for each QA pair
- `locomo10_qa_stats.json`: Aggregate statistics by question category

## Evaluation Metrics

- **F1 Score**: Token-level F1 between predicted and ground truth answers
- **Category Accuracy**: Aggregate accuracy for each question category
- **Overall Accuracy**: Weighted average across all categories

## Usage

Run the evaluation with:
```bash
python /task_data/run_locomo.py --model gpt-4-turbo --batch-size 20
```

Optional arguments:
- `--model`: Model to evaluate (default: gpt-4-turbo)
- `--batch-size`: Number of questions per batch (default: 20)
- `--use-rag`: Enable RAG-based evaluation
- `--overwrite`: Overwrite existing predictions
