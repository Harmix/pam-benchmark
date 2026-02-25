"""
LongMemEval Benchmark Runner

Runs the LongMemEval benchmark: sends full conversation history to an LLM,
generates answers, then evaluates with an LLM-as-judge.
Saves per-category results to MongoDB.

Based on agents/LongMemEval by Di Wu (2024).
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from typing import Dict, List, Optional

import backoff
import numpy as np
import openai
from openai import OpenAI
import tiktoken
from tqdm import tqdm

from pymongo import MongoClient


def load_secrets():
    """Load API keys from secrets.env file."""
    secrets_path = '/workspace/secrets.env'
    if os.path.exists(secrets_path):
        with open(secrets_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print("Loaded secrets from secrets.env")
    else:
        print("Warning: secrets.env not found, using existing environment variables")


def parse_args():
    parser = argparse.ArgumentParser(description='Run LongMemEval benchmark')
    parser.add_argument('--data-file', type=str,
                        default='/task_data/data/longmemeval_s_cleaned.json',
                        help='Path to LongMemEval dataset')
    parser.add_argument('--out-dir', type=str, default='/outputs',
                        help='Directory for output files')
    parser.add_argument('--model', type=str, default='gpt-4o',
                        help='Model for answer generation')
    parser.add_argument('--eval-model', type=str, default='gpt-4o',
                        help='Model for LLM-as-judge evaluation')
    parser.add_argument('--history-format', type=str, default='nl',
                        choices=['json', 'nl'],
                        help='Format for conversation history')
    parser.add_argument('--max-questions', type=int, default=0,
                        help='Max questions to process (0 = all)')
    parser.add_argument('--question-id', type=str, default=None,
                        help='Process a single question by ID')
    parser.add_argument('--cot', action='store_true',
                        help='Use chain-of-thought prompting')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing predictions')
    parser.add_argument('--skip-eval', action='store_true',
                        help='Skip LLM-as-judge evaluation')
    return parser.parse_args()


MODEL_MAX_LENGTHS = {
    'gpt-4o': 128000,
    'gpt-4o-2024-08-06': 128000,
    'gpt-4o-mini': 128000,
    'gpt-4o-mini-2024-07-18': 128000,
    'gpt-4.1': 1047576,
}

QUESTION_TYPES = [
    'single-session-user',
    'single-session-assistant',
    'single-session-preference',
    'multi-session',
    'temporal-reasoning',
    'knowledge-update',
]


@backoff.on_exception(backoff.constant, (openai.RateLimitError,), interval=5)
def chat_completions_with_backoff(client, **kwargs):
    return client.chat.completions.create(**kwargs)


def format_history_nl(sessions, dates):
    """Format conversation sessions in natural language."""
    parts = []
    for i, (session, date) in enumerate(zip(sessions, dates)):
        lines = [f"### Session {i+1}:", f"Session Date: {date}", "Session Content:"]
        for turn in session:
            lines.append(f"\n{turn['role']}: {turn['content'].strip()}")
        parts.append('\n'.join(lines))
    return '\n\n'.join(parts)


def format_history_json(sessions, dates):
    """Format conversation sessions as JSON."""
    parts = []
    for i, (session, date) in enumerate(zip(sessions, dates)):
        header = f"### Session {i+1}:\nSession Date: {date}\nSession Content:"
        parts.append(header + '\n' + json.dumps(session))
    return '\n\n'.join(parts)


def build_prompt(entry, history_format='nl', cot=False, tokenizer=None, max_context_tokens=None):
    """Build the generation prompt for a single question."""
    if cot:
        template = (
            'I will give you several history chats between you and a user. '
            'Please answer the question based on the relevant chat history. '
            'Answer the question step by step: first extract all the relevant '
            'information, and then reason over the information to get the answer.'
            '\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\n'
            'Answer (step by step):'
        )
    else:
        template = (
            'I will give you several history chats between you and a user. '
            'Please answer the question based on the relevant chat history.'
            '\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\n'
            'Answer:'
        )

    if history_format == 'nl':
        history = format_history_nl(entry['haystack_sessions'], entry['haystack_dates'])
    else:
        history = format_history_json(entry['haystack_sessions'], entry['haystack_dates'])

    if tokenizer and max_context_tokens:
        tokens = tokenizer.encode(history, allowed_special={'<|endoftext|>'})
        if len(tokens) > max_context_tokens:
            print(f'  Truncating history from {len(tokens)} to {max_context_tokens} tokens')
            history = tokenizer.decode(tokens[:max_context_tokens])

    return template.format(history, entry['question_date'], entry['question'])


def generate_answers(client, data, args, tokenizer, qid2type):
    """Generate answers for all questions. Returns predictions with per-question timing."""
    model_name = args.model
    gen_length = 800 if args.cot else 500
    model_max = MODEL_MAX_LENGTHS.get(model_name, 128000)
    max_context_tokens = model_max - gen_length - 1000

    predictions = []
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for entry in tqdm(data, desc="Generating answers"):
        prompt = build_prompt(
            entry,
            history_format=args.history_format,
            cot=args.cot,
            tokenizer=tokenizer,
            max_context_tokens=max_context_tokens,
        )

        q_start = time.time()
        try:
            kwargs = {
                'model': model_name,
                'messages': [{"role": "user", "content": prompt}],
                'n': 1,
                'temperature': 0,
                'max_tokens': gen_length,
            }
            completion = chat_completions_with_backoff(client, **kwargs)
            answer = completion.choices[0].message.content.strip()
            total_prompt_tokens += completion.usage.prompt_tokens
            total_completion_tokens += completion.usage.completion_tokens

            predictions.append({
                'question_id': entry['question_id'],
                'question_type': qid2type.get(entry['question_id'], 'unknown'),
                'hypothesis': answer,
                'generation_duration_sec': round(time.time() - q_start, 2),
            })
            print(f"  [{entry['question_id']}] Q: {entry['question'][:80]}...")
            print(f"  A: {answer[:120]}...")
        except Exception as e:
            print(f"  Error for {entry['question_id']}: {repr(e)}")
            predictions.append({
                'question_id': entry['question_id'],
                'question_type': qid2type.get(entry['question_id'], 'unknown'),
                'hypothesis': '',
                'generation_duration_sec': round(time.time() - q_start, 2),
            })

    print(f"\nToken usage — prompt: {total_prompt_tokens}, completion: {total_completion_tokens}")
    return predictions


def get_eval_prompt(task, question, answer, response, abstention=False):
    """Build the LLM-as-judge evaluation prompt (from LongMemEval)."""
    if not abstention:
        if task in ['single-session-user', 'single-session-assistant', 'multi-session']:
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate "
                "steps to get the correct answer, you should also answer yes. If the response only "
                "contains a subset of the information required by the answer, answer no. "
                "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == 'temporal-reasoning':
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate "
                "steps to get the correct answer, you should also answer yes. If the response only "
                "contains a subset of the information required by the answer, answer no. "
                "In addition, do not penalize off-by-one errors for the number of days. If the question "
                "asks for the number of days/weeks/months, etc., and the model makes off-by-one errors "
                "(e.g., predicting 19 days when the answer is 18), the model's response is still correct. "
                "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == 'knowledge-update':
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response contains some previous information along with an updated answer, "
                "the response should be considered as correct as long as the updated answer is the "
                "required answer."
                "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == 'single-session-preference':
            template = (
                "I will give you a question, a rubric for desired personalized response, and a response "
                "from a model. Please answer yes if the response satisfies the desired response. "
                "Otherwise, answer no. The model does not need to reflect all the points in the rubric. "
                "The response is correct as long as it recalls and utilizes the user's personal information "
                "correctly."
                "\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        else:
            raise ValueError(f"Unknown question type: {task}")
    else:
        template = (
            "I will give you an unanswerable question, an explanation, and a response from a model. "
            "Please answer yes if the model correctly identifies the question as unanswerable. "
            "The model could say that the information is incomplete, or some other information is "
            "given but the asked information is not."
            "\n\nQuestion: {}\n\nExplanation: {}\n\nModel Response: {}\n\n"
            "Does the model correctly identify the question as unanswerable? Answer yes or no only."
        )
    return template.format(question, answer, response)


def get_explanation_prompt(question, expected_answer, model_response, question_type):
    """Ask the judge to explain why the model's answer is incorrect."""
    return (
        "A model was asked the following question and gave an incorrect response. "
        "Briefly explain why the model's response is wrong (2-3 sentences max)."
        f"\n\nQuestion type: {question_type}"
        f"\n\nQuestion: {question}"
        f"\n\nExpected Answer: {expected_answer}"
        f"\n\nModel Response: {model_response}"
        f"\n\nExplanation:"
    )


def evaluate_predictions(client, predictions, ref_data, eval_model):
    """Run LLM-as-judge evaluation. Returns evaluated entries with judge explanation for incorrect ones."""
    qid2ref = {e['question_id']: e for e in ref_data}
    type2results = {t: [] for t in QUESTION_TYPES}
    evaluated = []

    for entry in tqdm(predictions, desc="Evaluating"):
        qid = entry['question_id']
        if qid not in qid2ref:
            print(f"  Warning: {qid} not in reference data, skipping")
            continue

        ref = qid2ref[qid]
        qtype = ref['question_type']
        question = ref['question']
        answer = str(ref['answer'])
        hypothesis = entry['hypothesis']

        abstention = '_abs' in qid
        prompt = get_eval_prompt(qtype, question, answer, hypothesis, abstention=abstention)

        eval_start = time.time()
        eval_explanation = ""
        try:
            kwargs = {
                'model': eval_model,
                'messages': [{"role": "user", "content": prompt}],
                'n': 1,
                'temperature': 0,
                'max_tokens': 10,
            }
            completion = chat_completions_with_backoff(client, **kwargs)
            eval_response = completion.choices[0].message.content.strip()
            label = 'yes' in eval_response.lower()

            if not label:
                expl_prompt = get_explanation_prompt(question, answer, hypothesis, qtype)
                expl_kwargs = {
                    'model': eval_model,
                    'messages': [{"role": "user", "content": expl_prompt}],
                    'n': 1,
                    'temperature': 0,
                    'max_tokens': 200,
                }
                expl_completion = chat_completions_with_backoff(client, **expl_kwargs)
                eval_explanation = expl_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"  Eval error for {qid}: {repr(e)}")
            label = False
            eval_explanation = f"Evaluation error: {repr(e)}"

        eval_duration = round(time.time() - eval_start, 2)

        entry['autoeval_label'] = {
            'model': eval_model,
            'label': label,
            'eval_duration_sec': eval_duration,
        }
        if not label:
            entry['autoeval_label']['explanation'] = eval_explanation

        entry['question_type'] = qtype
        entry['question'] = question
        entry['expected_answer'] = answer
        evaluated.append(entry)

        if qtype in type2results:
            type2results[qtype].append({
                'question_id': qid,
                'label': label,
                'generation_duration_sec': entry.get('generation_duration_sec', 0),
                'eval_duration_sec': eval_duration,
            })

    return evaluated, type2results


def build_category_records(type2results, evaluated, args, total_execution_time):
    """Build one MongoDB record per question category."""
    experiment_name = os.environ.get("EXPERIMENT_NAME", "")
    records = []

    evaluated_by_qid = {e['question_id']: e for e in evaluated}

    for qtype in QUESTION_TYPES:
        results = type2results.get(qtype, [])
        if not results:
            continue

        correct = sum(1 for r in results if r['label'])
        incorrect = len(results) - correct
        accuracy = round(correct / len(results), 4) if results else 0.0

        total_gen_duration = sum(r['generation_duration_sec'] for r in results)
        total_eval_duration = sum(r['eval_duration_sec'] for r in results)
        total_duration = round(total_gen_duration + total_eval_duration, 2)
        avg_duration = round(total_duration / len(results), 2) if results else 0.0

        correct_answers = []
        incorrect_answers = []
        for r in results:
            entry = evaluated_by_qid.get(r['question_id'], {})
            answer_record = {
                'question_id': r['question_id'],
                'question': entry.get('question', ''),
                'expected_answer': entry.get('expected_answer', ''),
                'model_answer': entry.get('hypothesis', ''),
                'generation_duration_sec': r['generation_duration_sec'],
            }
            if r['label']:
                correct_answers.append(answer_record)
            else:
                answer_record['judge_explanation'] = (
                    entry.get('autoeval_label', {}).get('explanation', '')
                )
                incorrect_answers.append(answer_record)

        record = {
            'experiment_name': experiment_name,
            'model': args.model,
            'eval_model': args.eval_model,
            'dataset_name': os.environ.get('DATASET_NAME', 'longmemeval@1.0'),
            'task_name': os.environ.get('TASK_NAME', 'longmemeval'),
            'question_category': qtype,
            'total_questions': len(results),
            'correct_count': correct,
            'incorrect_count': incorrect,
            'accuracy': accuracy,
            'total_duration_sec': total_duration,
            'avg_duration_sec': avg_duration,
            'total_generation_duration_sec': round(total_gen_duration, 2),
            'total_eval_duration_sec': round(total_eval_duration, 2),
            'correct_answers': correct_answers,
            'incorrect_answers': incorrect_answers,
            'config': {
                'history_format': args.history_format,
                'cot': args.cot,
                'max_questions': args.max_questions,
            },
            'total_execution_time_sec': round(total_execution_time, 2),
            'timestamp': datetime.utcnow(),
            'created_at': datetime.utcnow().isoformat(),
        }
        records.append(record)

    return records


def save_to_mongodb(records: List[Dict], db_name: str, connection_string: str) -> bool:
    """Save per-category records to MongoDB."""
    if not records:
        print("Warning: no records to save")
        return False

    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')

        db = client[db_name]
        collection = db["longmemeval_results"]

        result = collection.insert_many(records)
        print(f"\nMongoDB: saved {len(result.inserted_ids)} category records")
        for rec in records:
            print(f"  {rec['question_category']}: "
                  f"accuracy={rec['accuracy']} "
                  f"({rec['correct_count']}/{rec['total_questions']}), "
                  f"avg_duration={rec['avg_duration_sec']}s")

        client.close()
        return True
    except Exception as e:
        print(f"Warning: Failed to save to MongoDB: {str(e)}")
        return False


def print_metrics(type2results):
    """Print accuracy metrics by question type."""
    all_acc = []
    task_acc = []

    print("\n" + "=" * 60)
    print("Evaluation Results by Question Type")
    print("=" * 60)

    for qtype in QUESTION_TYPES:
        results = type2results.get(qtype, [])
        if results:
            correct = sum(1 for r in results if r['label'])
            acc = round(correct / len(results), 4)
            task_acc.append(acc)
            all_acc.extend([1 if r['label'] else 0 for r in results])
            total_dur = sum(r['generation_duration_sec'] + r['eval_duration_sec'] for r in results)
            avg_dur = round(total_dur / len(results), 2)
            print(f"  {qtype}: {acc} ({correct}/{len(results)}) "
                  f"— avg {avg_dur}s/question")
        else:
            print(f"  {qtype}: N/A (0 questions)")

    if task_acc:
        print(f"\n  Task-averaged Accuracy: {round(np.mean(task_acc), 4)}")
    if all_acc:
        print(f"  Overall Accuracy: {round(np.mean(all_acc), 4)} ({sum(all_acc)}/{len(all_acc)})")
    print("=" * 60)


def main():
    start_time = time.time()
    load_secrets()
    args = parse_args()

    print("=" * 60)
    print("LongMemEval Benchmark")
    print("=" * 60)
    print(f"  Model: {args.model}")
    print(f"  Eval model: {args.eval_model}")
    print(f"  Data file: {args.data_file}")
    print(f"  History format: {args.history_format}")
    print(f"  Chain-of-thought: {args.cot}")
    if args.max_questions > 0:
        print(f"  Max questions: {args.max_questions}")
    if args.question_id:
        print(f"  Single question: {args.question_id}")
    print("=" * 60)

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    tokenizer = tiktoken.get_encoding('o200k_base')

    print(f"\nLoading dataset from {args.data_file}...")
    with open(args.data_file) as f:
        data = json.load(f)
    print(f"Loaded {len(data)} questions")

    qid2type = {e['question_id']: e['question_type'] for e in data}

    if args.question_id:
        data = [e for e in data if e['question_id'] == args.question_id]
        if not data:
            print(f"Error: question_id '{args.question_id}' not found")
            sys.exit(1)
        print(f"Filtered to question: {args.question_id}")

    if args.max_questions > 0:
        data = data[:args.max_questions]
        print(f"Limited to {len(data)} questions")

    os.makedirs(args.out_dir, exist_ok=True)
    predictions_file = os.path.join(args.out_dir, 'longmemeval_predictions.jsonl')
    eval_file = os.path.join(args.out_dir, 'longmemeval_eval_results.jsonl')
    stats_file = os.path.join(args.out_dir, 'longmemeval_stats.json')

    existing_preds = {}
    if os.path.exists(predictions_file) and not args.overwrite:
        with open(predictions_file) as f:
            for line in f:
                entry = json.loads(line)
                existing_preds[entry['question_id']] = entry
        print(f"Loaded {len(existing_preds)} existing predictions")

    to_generate = [e for e in data if e['question_id'] not in existing_preds]
    print(f"Questions to generate: {len(to_generate)} "
          f"(skipping {len(data) - len(to_generate)} existing)")

    if to_generate:
        new_predictions = generate_answers(client, to_generate, args, tokenizer, qid2type)
        for pred in new_predictions:
            existing_preds[pred['question_id']] = pred

        with open(predictions_file, 'w') as f:
            for pred in existing_preds.values():
                f.write(json.dumps(pred) + '\n')
        print(f"\nPredictions saved to {predictions_file}")

    all_predictions = [
        existing_preds[e['question_id']]
        for e in data
        if e['question_id'] in existing_preds
    ]

    if args.skip_eval:
        print("\nSkipping evaluation (--skip-eval)")
    else:
        print(f"\nRunning LLM-as-judge evaluation with {args.eval_model}...")
        evaluated, type2results = evaluate_predictions(
            client, all_predictions, data, args.eval_model
        )

        with open(eval_file, 'w') as f:
            for entry in evaluated:
                f.write(json.dumps(entry, default=str) + '\n')
        print(f"Evaluation results saved to {eval_file}")

        print_metrics(type2results)

        execution_time = time.time() - start_time

        # Build per-category stats for local file
        stats = {
            'model': args.model,
            'eval_model': args.eval_model,
            'history_format': args.history_format,
            'cot': args.cot,
            'max_questions': args.max_questions,
            'execution_time_seconds': round(execution_time, 2),
            'timestamp': datetime.utcnow().isoformat(),
            'categories': {},
        }
        all_correct = 0
        all_total = 0
        for qtype in QUESTION_TYPES:
            results = type2results.get(qtype, [])
            if results:
                correct = sum(1 for r in results if r['label'])
                total_dur = sum(r['generation_duration_sec'] + r['eval_duration_sec']
                                for r in results)
                stats['categories'][qtype] = {
                    'total_questions': len(results),
                    'correct_count': correct,
                    'incorrect_count': len(results) - correct,
                    'accuracy': round(correct / len(results), 4),
                    'total_duration_sec': round(total_dur, 2),
                    'avg_duration_sec': round(total_dur / len(results), 2),
                }
                all_correct += correct
                all_total += len(results)

        stats['overall_accuracy'] = round(all_correct / all_total, 4) if all_total else 0.0
        stats['total_questions'] = all_total
        stats['correct_count'] = all_correct

        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"Statistics saved to {stats_file}")

        # Save to MongoDB (one record per category)
        db_name = os.environ.get("DB_NAME")
        connection_string = os.environ.get("CONNECTION_STRING")
        experiment_name = os.environ.get("EXPERIMENT_NAME")

        if experiment_name and db_name and connection_string:
            records = build_category_records(
                type2results, evaluated, args, execution_time
            )
            save_to_mongodb(records, db_name, connection_string)
        elif not experiment_name:
            print("\nEXPERIMENT_NAME not set, skipping MongoDB save")
        else:
            print("\nMongoDB not fully configured (missing DB_NAME or CONNECTION_STRING), "
                  "skipping save")

    execution_time = time.time() - start_time
    print(f"\nTotal execution time: {execution_time:.1f}s")
    print("Done.")


if __name__ == '__main__':
    main()
