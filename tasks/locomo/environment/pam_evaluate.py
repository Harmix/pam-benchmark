#!/usr/bin/env python3
"""
PAM Evaluation Script for LoCoMo

Evaluates PAM answers against ground truth, calculates metrics, and saves to MongoDB.
This is run after PAM answers all questions for a sample.
"""

import os
import sys
import json
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
    max_questions: int = 0
) -> Tuple[Dict, List[Dict]]:
    """
    Evaluate PAM answers against ground truth.
    
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
        
        # Calculate F1
        f1_score = calculate_f1_score(pam_answer, expected_answer)
        total_f1 += f1_score
        
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
            incorrect_responses.append({
                'question_num': i + 1,
                'question': question,
                'expected_answer': expected_answer,
                'pam_answer': pam_answer,
                'f1_score': round(f1_score, 4),
                'category': category,
                'category_name': category_names.get(category, f"category_{category}")
            })
    
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
    print("")
    
    # Evaluate
    metrics, incorrect_responses = evaluate_pam_answers(
        args.pam_answers,
        args.data_file,
        args.sample_index,
        args.max_questions
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
