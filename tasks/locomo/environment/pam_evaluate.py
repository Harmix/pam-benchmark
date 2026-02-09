#!/usr/bin/env python3
"""
PAM Evaluation Script for LoCoMo

Evaluates PAM answers against ground truth, calculates metrics, and saves to MongoDB.
Supports both token-based F1 scoring and LLM-as-a-Judge evaluation.
This is run after PAM answers all questions for a sample.
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add task_data to path for imports
sys.path.insert(0, '/task_data')

from task_eval.evaluation import f1_score as compute_f1

# MongoDB import (optional)
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not installed, MongoDB saving disabled")

# OpenAI import (optional, for LLM judge)
# Supports both old SDK (openai==0.28.x) and new SDK (openai>=1.0)
OPENAI_AVAILABLE = False
OPENAI_NEW_SDK = False
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
    OPENAI_NEW_SDK = True
except ImportError:
    try:
        import openai as openai_module
        OPENAI_AVAILABLE = True
        OPENAI_NEW_SDK = False
    except ImportError:
        pass


# LLM-as-a-Judge prompt (adapted from agents/mem0/metrics/llm_judge.py)
LLM_JUDGE_PROMPT = """Your task is to label an answer to a question as 'CORRECT' or 'WRONG'. You will be given the following data:
    (1) a question (posed by one user to another user),
    (2) a 'gold' (ground truth) answer,
    (3) a generated answer
which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other user based on their prior conversations.
The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer: A shell necklace
The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT.

For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it's the same date.

For questions where the gold answer is a list of items, the generated answer should contain the key items from the gold answer. It is acceptable if the generated answer includes additional correct items, as long as the core items from the gold answer are present.

Now it's time for the real question:
Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}

First, provide a short (one sentence) explanation of your reasoning, then finish with CORRECT or WRONG.
Do NOT include both CORRECT and WRONG in your response, or it will break the evaluation script.

Just return the label CORRECT or WRONG in a json format with the key as "label"."""


def evaluate_with_llm_judge(question: str, gold_answer: str, generated_answer: str) -> int:
    """
    Evaluate a single answer using LLM-as-a-Judge.
    Supports both old OpenAI SDK (v0.28.x) and new SDK (v1.0+).
    
    Returns:
        1 if CORRECT, 0 if WRONG, -1 if error
    """
    if not OPENAI_AVAILABLE:
        print("Warning: openai not available, skipping LLM judge")
        return -1
    
    prompt_content = LLM_JUDGE_PROMPT.format(
        question=question,
        gold_answer=gold_answer,
        generated_answer=generated_answer
    )
    
    try:
        if OPENAI_NEW_SDK:
            # New SDK (openai >= 1.0)
            client = OpenAI()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt_content}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            content = response.choices[0].message.content
        else:
            # Old SDK (openai == 0.28.x)
            import openai as openai_module
            openai_module.api_key = os.environ.get('OPENAI_API_KEY', '')
            response = openai_module.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt_content}],
                temperature=0.0,
            )
            content = response['choices'][0]['message']['content']
        
        # Extract JSON from response (handle potential extra text)
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            label = json.loads(json_match.group())["label"]
        else:
            label = json.loads(content)["label"]
        return 1 if label == "CORRECT" else 0
    except Exception as e:
        print(f"  Warning: LLM judge failed for question: {e}")
        return -1


def load_secrets():
    """Load environment variables from secrets.env file."""
    secrets_path = '/workspace/secrets.env'
    if os.path.exists(secrets_path):
        with open(secrets_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value


def normalize_answer(answer: str) -> str:
    """Normalize answer for comparison."""
    if answer is None:
        return ""
    answer = str(answer).lower().strip()
    # Remove common prefixes
    for prefix in ["answer:", "a:", "the answer is", "the answer:"]:
        if answer.startswith(prefix):
            answer = answer[len(prefix):].strip()
    return answer


def calculate_f1_score(prediction: str, ground_truth: str) -> float:
    """Calculate F1 score between prediction and ground truth."""
    pred_norm = normalize_answer(prediction)
    truth_norm = normalize_answer(ground_truth)
    
    if not pred_norm or not truth_norm:
        return 0.0
    
    # Use the evaluation function from locomo
    try:
        return compute_f1(pred_norm, truth_norm)
    except Exception:
        # Fallback to simple token overlap
        pred_tokens = set(pred_norm.split())
        truth_tokens = set(truth_norm.split())
        
        if not pred_tokens or not truth_tokens:
            return 0.0
        
        common = pred_tokens & truth_tokens
        precision = len(common) / len(pred_tokens) if pred_tokens else 0
        recall = len(common) / len(truth_tokens) if truth_tokens else 0
        
        if precision + recall == 0:
            return 0.0
        
        return 2 * precision * recall / (precision + recall)


def evaluate_pam_answers(
    pam_answers_file: str,
    data_file: str,
    sample_index: int,
    max_questions: int = 0,
    use_llm_judge: bool = False
) -> Tuple[Dict, List[Dict]]:
    """
    Evaluate PAM answers against ground truth.
    
    Args:
        pam_answers_file: Path to PAM answers JSON
        data_file: Path to LoCoMo data file
        sample_index: Index of sample to evaluate
        max_questions: Max questions to evaluate (0 = all)
        use_llm_judge: Whether to also run LLM-as-a-Judge evaluation
    
    Returns:
        Tuple of (metrics dict, incorrect_responses list)
    """
    # Load PAM answers
    with open(pam_answers_file, 'r') as f:
        pam_answers = json.load(f)
    
    # Load ground truth
    with open(data_file, 'r') as f:
        data = json.load(f)
    
    sample = data[sample_index]
    qa_pairs = sample.get('qa', [])
    
    if max_questions > 0:
        qa_pairs = qa_pairs[:max_questions]
    
    # Calculate metrics
    total_questions = len(qa_pairs)
    total_f1 = 0.0
    correct_count = 0
    incorrect_responses = []
    
    # LLM judge tracking
    total_llm_judge = 0.0
    llm_judge_count = 0
    category_llm_judge_sums = {}
    
    # Category tracking
    category_counts = {}
    category_f1_sums = {}
    
    F1_THRESHOLD = 0.5
    
    # Category names for locomo
    category_names = {
        1: "single_hop",
        2: "temporal",
        3: "open_domain",
        4: "multi_hop",
        5: "adversarial"
    }
    
    if use_llm_judge and not OPENAI_AVAILABLE:
        print("Warning: openai package not available, disabling LLM judge")
        use_llm_judge = False
    
    for i, qa in enumerate(qa_pairs):
        question = qa.get('question', '')
        expected_answer = str(qa.get('answer', ''))
        category = qa.get('category', 0)
        
        # Find PAM answer
        pam_answer = ''
        for pa in pam_answers:
            if pa.get('question_num') == i + 1:
                pam_answer = pa.get('pam_answer', '')
                break
        
        # Calculate F1 (with special handling for adversarial category 5)
        if category == 5:
            # Adversarial: correct if model says "not mentioned" or "no information available"
            pam_lower = pam_answer.lower()
            if 'not mentioned' in pam_lower or 'no information available' in pam_lower:
                f1_score = 1.0
            else:
                f1_score = 0.0
        else:
            f1_score = calculate_f1_score(pam_answer, expected_answer)
        total_f1 += f1_score
        
        # LLM judge evaluation (skip category 5 -- use binary check above)
        llm_judge_score = None
        if use_llm_judge and category != 5:
            llm_judge_score = evaluate_with_llm_judge(question, expected_answer, pam_answer)
            if llm_judge_score >= 0:
                total_llm_judge += llm_judge_score
                llm_judge_count += 1
                if category not in category_llm_judge_sums:
                    category_llm_judge_sums[category] = 0.0
                category_llm_judge_sums[category] += llm_judge_score
        
        # Track category metrics
        if category not in category_counts:
            category_counts[category] = 0
            category_f1_sums[category] = 0.0
        category_counts[category] += 1
        category_f1_sums[category] += f1_score
        
        # Check if correct
        if f1_score >= F1_THRESHOLD:
            correct_count += 1
        else:
            error_entry = {
                'question_num': i + 1,
                'question': question,
                'expected_answer': expected_answer,
                'pam_answer': pam_answer,
                'f1_score': round(f1_score, 4),
                'category': category,
                'category_name': category_names.get(category, f"category_{category}")
            }
            if llm_judge_score is not None:
                error_entry['llm_judge_score'] = llm_judge_score
            incorrect_responses.append(error_entry)
    
    # Calculate overall metrics
    overall_accuracy = total_f1 / total_questions if total_questions > 0 else 0.0
    
    # Calculate per-category accuracy
    category_metrics = {}
    for cat, count in category_counts.items():
        cat_name = category_names.get(cat, f"category_{cat}")
        category_metrics[f'{cat_name}_accuracy'] = round(category_f1_sums[cat] / count, 4) if count > 0 else 0.0
        category_metrics[f'{cat_name}_count'] = count
    
    metrics = {
        'total_questions': total_questions,
        'correct_count': correct_count,
        'incorrect_count': len(incorrect_responses),
        'overall_accuracy': round(overall_accuracy, 4),
        'total_f1_sum': round(total_f1, 4),
        **category_metrics
    }
    
    # Add LLM judge metrics if enabled
    if use_llm_judge and llm_judge_count > 0:
        llm_judge_accuracy = total_llm_judge / llm_judge_count
        metrics['llm_judge_accuracy'] = round(llm_judge_accuracy, 4)
        metrics['llm_judge_correct'] = int(total_llm_judge)
        metrics['llm_judge_total'] = llm_judge_count
        
        # Per-category LLM judge accuracy and counts
        for cat, llm_sum in category_llm_judge_sums.items():
            cat_name = category_names.get(cat, f"category_{cat}")
            cat_count = category_counts.get(cat, 0)
            # For cat 5, llm_judge is not used, so cat_count here excludes cat 5
            cat_llm_count = cat_count  # All non-cat-5 questions were judged
            if cat_llm_count > 0:
                metrics[f'{cat_name}_llm_judge_accuracy'] = round(llm_sum / cat_llm_count, 4)
                metrics[f'{cat_name}_llm_judge_correct'] = int(llm_sum)
                metrics[f'{cat_name}_llm_judge_total'] = cat_llm_count
        
        print(f"\n  LLM Judge Accuracy: {llm_judge_accuracy:.4f} ({int(total_llm_judge)}/{llm_judge_count})")
    
    return metrics, incorrect_responses


def save_to_mongodb(
    experiment_name: str,
    sample_id: str,
    sample_index: int,
    metrics: Dict,
    db_name: str,
    connection_string: str,
    execution_time: float = None,
    config: Dict = None,
    incorrect_responses: List[Dict] = None
) -> bool:
    """Save evaluation results to MongoDB."""
    if not MONGODB_AVAILABLE:
        print("Warning: pymongo not available, skipping MongoDB save")
        return False
    
    try:
        # Create document
        mongo_data = {
            "experiment_name": experiment_name,
            "model": "pam",
            "dataset_name": os.environ.get("DATASET_NAME", "locomo@1.0"),
            "task_name": os.environ.get("TASK_NAME", "locomo"),
            "sample_id": sample_id,
            "sample_index": sample_index,
            **metrics
        }
        
        # Add execution time if provided
        if execution_time is not None:
            mongo_data["execution_time_seconds"] = float(execution_time)
        
        # Add config details if provided
        if config:
            mongo_data["max_questions"] = config.get("max_questions", 0)
        
        # Add incorrect responses if provided
        if incorrect_responses:
            mongo_data["incorrect_responses"] = incorrect_responses
        
        # Add timestamp
        timestamp = datetime.utcnow()
        mongo_data["timestamp"] = timestamp
        mongo_data["created_at"] = timestamp.isoformat()
        
        # Connect to MongoDB
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        
        db = client[db_name]
        collection = db["locomo_results"]
        
        # Insert document
        result = collection.insert_one(mongo_data)
        print(f"✓ Results saved to MongoDB: experiment='{experiment_name}', sample='{sample_id}', ID={result.inserted_id}")
        print(f"  Metrics: accuracy={metrics['overall_accuracy']}, correct={metrics['correct_count']}/{metrics['total_questions']}")
        
        client.close()
        return True
    except Exception as e:
        print(f"Warning: Failed to save to MongoDB: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Evaluate PAM answers for LoCoMo')
    parser.add_argument('--pam-answers', type=str, required=True,
                        help='Path to PAM answers JSON file')
    parser.add_argument('--data-file', type=str, default='/task_data/data/locomo10.json',
                        help='Path to LoCoMo data file')
    parser.add_argument('--sample-index', type=int, required=True,
                        help='Sample index that was evaluated')
    parser.add_argument('--max-questions', type=int, default=0,
                        help='Max questions evaluated (0 = all)')
    parser.add_argument('--execution-time', type=float, default=None,
                        help='Execution time in seconds')
    parser.add_argument('--output-file', type=str, default=None,
                        help='Output file for metrics JSON')
    parser.add_argument('--use-llm-judge', action='store_true',
                        help='Enable LLM-as-a-Judge evaluation (requires OPENAI_API_KEY)')
    
    args = parser.parse_args()
    
    # Load secrets for MongoDB
    load_secrets()
    
    # Load sample ID from data
    with open(args.data_file, 'r') as f:
        data = json.load(f)
    sample_id = data[args.sample_index].get('sample_id', f'sample_{args.sample_index}')
    
    print("=" * 60)
    print("PAM Evaluation for LoCoMo")
    print("=" * 60)
    print(f"Sample: {sample_id} (index: {args.sample_index})")
    print(f"PAM Answers: {args.pam_answers}")
    print(f"Max Questions: {args.max_questions if args.max_questions > 0 else 'all'}")
    print(f"LLM Judge: {'enabled' if args.use_llm_judge else 'disabled'}")
    print("")
    
    # Evaluate
    metrics, incorrect_responses = evaluate_pam_answers(
        args.pam_answers,
        args.data_file,
        args.sample_index,
        args.max_questions,
        use_llm_judge=args.use_llm_judge
    )
    
    # Print metrics
    print("Metrics:")
    print(f"  Total Questions: {metrics['total_questions']}")
    print(f"  Correct: {metrics['correct_count']}")
    print(f"  Incorrect: {metrics['incorrect_count']}")
    print(f"  Overall Accuracy (F1): {metrics['overall_accuracy']}")
    print("")
    
    # Print category breakdown
    print("Category Breakdown:")
    for key, value in metrics.items():
        if '_accuracy' in key:
            cat_name = key.replace('_accuracy', '')
            count_key = f'{cat_name}_count'
            count = metrics.get(count_key, 0)
            print(f"  {cat_name}: {value:.4f} ({count} questions)")
    print("")
    
    # Save metrics to file if requested
    if args.output_file:
        output_data = {
            'sample_id': sample_id,
            'sample_index': args.sample_index,
            'metrics': metrics,
            'incorrect_count': len(incorrect_responses)
        }
        with open(args.output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"Metrics saved to: {args.output_file}")
    
    # Save to MongoDB
    experiment_name = os.environ.get("EXPERIMENT_NAME")
    db_name = os.environ.get("DB_NAME")
    connection_string = os.environ.get("CONNECTION_STRING")
    
    if experiment_name and db_name and connection_string:
        print(f"\nSaving to MongoDB (experiment: {experiment_name})...")
        config = {"max_questions": args.max_questions}
        save_to_mongodb(
            experiment_name,
            sample_id,
            args.sample_index,
            metrics,
            db_name,
            connection_string,
            args.execution_time,
            config,
            incorrect_responses
        )
    else:
        if not experiment_name:
            print("\n⚠ EXPERIMENT_NAME not set, skipping MongoDB save")
        elif not db_name or not connection_string:
            print("\n⚠ MongoDB not fully configured, skipping save")
    
    print("")
    print("=" * 60)
    print("PAM Evaluation Complete")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
