#!/usr/bin/env python3
"""
LoCoMo Benchmark Runner

This script runs the LoCoMo (Long Context Memory) benchmark evaluation.
It loads API keys from secrets.env and evaluates LLM models on the LoCoMo dataset.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add task_data to path for imports
sys.path.insert(0, '/task_data')

from global_methods import set_openai_key, set_anthropic_key, set_gemini_key
from task_eval.evaluation import eval_question_answering
from task_eval.evaluation_stats import analyze_aggr_acc
from task_eval.gpt_utils import get_gpt_answers
from task_eval.claude_utils import get_claude_answers
from task_eval.gemini_utils import get_gemini_answers

import google.generativeai as genai

# MongoDB import (optional)
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not installed, MongoDB saving disabled")


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
    parser = argparse.ArgumentParser(description='Run LoCoMo benchmark evaluation')
    parser.add_argument('--data-file', type=str, default='/task_data/data/locomo10.json',
                        help='Path to LoCoMo data file')
    parser.add_argument('--out-file', type=str, default='/outputs/locomo10_qa.json',
                        help='Path to output file')
    parser.add_argument('--model', type=str, default='gpt-4-turbo',
                        help='Model to evaluate (gpt-4-turbo, gpt-3.5-turbo, claude-sonnet, gemini-pro-1.0)')
    parser.add_argument('--batch-size', type=int, default=20,
                        help='Batch size for evaluation')
    parser.add_argument('--use-rag', action='store_true',
                        help='Use RAG-based evaluation')
    parser.add_argument('--use-4bit', action='store_true',
                        help='Use 4-bit quantization (for HF models)')
    parser.add_argument('--rag-mode', type=str, default='',
                        help='RAG mode (summary, dialog, observation)')
    parser.add_argument('--emb-dir', type=str, default='/outputs',
                        help='Directory for embeddings')
    parser.add_argument('--top-k', type=int, default=5,
                        help='Top-k for RAG retrieval')
    parser.add_argument('--retriever', type=str, default='contriever',
                        help='Retriever model for RAG')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing predictions')
    parser.add_argument('--max-questions', type=int, default=0,
                        help='Maximum number of questions per sample (0 = all questions)')
    return parser.parse_args()


def calculate_metrics(out_samples: Dict, model_key: str) -> Dict:
    """Calculate aggregate metrics from evaluation results."""
    total_questions = 0
    total_f1 = 0.0
    category_counts = {}
    category_f1_sums = {}
    
    for sample_id, sample in out_samples.items():
        for qa in sample.get('qa', []):
            total_questions += 1
            f1_score = qa.get(f'{model_key}_f1', 0.0)
            total_f1 += f1_score
            
            category = qa.get('category', 0)
            if category not in category_counts:
                category_counts[category] = 0
                category_f1_sums[category] = 0.0
            category_counts[category] += 1
            category_f1_sums[category] += f1_score
    
    # Calculate overall metrics
    overall_accuracy = total_f1 / total_questions if total_questions > 0 else 0.0
    
    # Calculate per-category accuracy
    category_accuracy = {}
    for cat, count in category_counts.items():
        category_accuracy[f'category_{cat}_accuracy'] = category_f1_sums[cat] / count if count > 0 else 0.0
        category_accuracy[f'category_{cat}_count'] = count
    
    return {
        'total_questions': total_questions,
        'overall_accuracy': round(overall_accuracy, 4),
        'total_f1_sum': round(total_f1, 4),
        **category_accuracy
    }


def save_to_mongodb(experiment_name: str, model: str, metrics: Dict, 
                   db_name: str, connection_string: str,
                   execution_time: float = None,
                   config: Dict = None) -> bool:
    """Save evaluation results to MongoDB."""
    if not MONGODB_AVAILABLE:
        print("⚠ Warning: pymongo not available, skipping MongoDB save")
        return False
    
    try:
        # Create document
        mongo_data = {
            "experiment_name": experiment_name,
            "model": model,
            "dataset_name": os.environ.get("DATASET_NAME", "locomo@1.0"),
            "task_name": os.environ.get("TASK_NAME", "locomo"),
            **metrics
        }
        
        # Add execution time if provided
        if execution_time is not None:
            mongo_data["execution_time_seconds"] = float(execution_time)
        
        # Add config details if provided
        if config:
            mongo_data["batch_size"] = config.get("batch_size", 20)
            mongo_data["use_rag"] = config.get("use_rag", False)
            mongo_data["max_questions"] = config.get("max_questions", 0)
        
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
        print(f"✓ Results saved to MongoDB: experiment='{experiment_name}', model='{model}', ID={result.inserted_id}")
        
        client.close()
        return True
    except Exception as e:
        print(f"⚠ Warning: Failed to save to MongoDB: {str(e)}")
        print(f"   Database: {db_name}, Connection: {'configured' if connection_string else 'not set'}")
        return False


def main():
    import time
    start_time = time.time()
    
    # Load API keys from secrets.env
    load_secrets()
    
    # Parse arguments
    args = parse_args()
    
    print("=" * 60)
    print(f"LoCoMo Benchmark Evaluation")
    print(f"Model: {args.model}")
    print(f"Data file: {args.data_file}")
    print(f"Output file: {args.out_file}")
    if args.max_questions > 0:
        print(f"Max questions per sample: {args.max_questions}")
    print("=" * 60)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.out_file), exist_ok=True)
    
    # Initialize model-specific settings
    gemini_model = None
    
    if 'gpt' in args.model:
        set_openai_key()
        print(f"Initialized OpenAI API for model: {args.model}")
        
    elif 'claude' in args.model:
        set_anthropic_key()
        print(f"Initialized Anthropic API for model: {args.model}")
        
    elif 'gemini' in args.model:
        set_gemini_key()
        if args.model == "gemini-pro-1.0":
            model_name = "models/gemini-1.0-pro-latest"
        else:
            model_name = args.model
        gemini_model = genai.GenerativeModel(model_name)
        print(f"Initialized Gemini API for model: {model_name}")
    else:
        raise NotImplementedError(f"Model {args.model} is not supported")
    
    # Load conversations/samples
    print(f"\nLoading data from {args.data_file}...")
    samples = json.load(open(args.data_file))
    print(f"Loaded {len(samples)} samples")
    
    # Set up prediction keys
    prediction_key = f"{args.model}_prediction" if not args.use_rag else f"{args.model}_{args.rag_mode}_top_{args.top_k}_prediction"
    model_key = args.model if not args.use_rag else f"{args.model}_{args.rag_mode}_top_{args.top_k}"
    
    # Load existing output file if it exists
    if os.path.exists(args.out_file):
        out_samples = {d['sample_id']: d for d in json.load(open(args.out_file))}
        print(f"Loaded {len(out_samples)} existing results from {args.out_file}")
    else:
        out_samples = {}
    
    # Process each sample
    for data in samples:
        print(f"\nProcessing sample: {data['sample_id']}")
        
        # Limit questions if max_questions is specified
        if args.max_questions > 0:
            data['qa'] = data['qa'][:args.max_questions]
            print(f"  Limited to {len(data['qa'])} questions (max_questions={args.max_questions})")
        
        out_data = {'sample_id': data['sample_id']}
        if data['sample_id'] in out_samples:
            out_data['qa'] = out_samples[data['sample_id']]['qa'].copy()
            if args.max_questions > 0:
                out_data['qa'] = out_data['qa'][:args.max_questions]
        else:
            out_data['qa'] = data['qa'].copy()
        
        # Get answers based on model type
        if 'gpt' in args.model:
            answers = get_gpt_answers(data, out_data, prediction_key, args)
        elif 'claude' in args.model:
            answers = get_claude_answers(data, out_data, prediction_key, args)
        elif 'gemini' in args.model:
            answers = get_gemini_answers(gemini_model, data, out_data, prediction_key, args)
        else:
            raise NotImplementedError(f"Model {args.model} is not supported")
        
        # Evaluate individual QA samples and save the score
        exact_matches, lengths, recall = eval_question_answering(answers['qa'], prediction_key)
        for i in range(len(answers['qa'])):
            answers['qa'][i][model_key + '_f1'] = round(exact_matches[i], 3)
            if args.use_rag and len(recall) > 0:
                answers['qa'][i][model_key + '_recall'] = round(recall[i], 3)
        
        out_samples[data['sample_id']] = answers
    
    # Save results
    print(f"\nSaving results to {args.out_file}...")
    with open(args.out_file, 'w') as f:
        json.dump(list(out_samples.values()), f, indent=2)
    
    # Analyze and save statistics
    stats_file = args.out_file.replace('.json', '_stats.json')
    print(f"Analyzing results and saving statistics to {stats_file}...")
    analyze_aggr_acc(
        args.data_file, 
        args.out_file, 
        stats_file,
        model_key, 
        model_key + '_f1', 
        rag=args.use_rag
    )
    
    # Calculate execution time
    execution_time = time.time() - start_time
    
    # Calculate metrics for MongoDB
    metrics = calculate_metrics(out_samples, model_key)
    print(f"\nMetrics Summary:")
    print(f"  Total questions: {metrics['total_questions']}")
    print(f"  Overall accuracy (F1): {metrics['overall_accuracy']}")
    
    # Save to MongoDB if configured
    experiment_name = os.environ.get("EXPERIMENT_NAME")
    db_name = os.environ.get("DB_NAME")
    connection_string = os.environ.get("CONNECTION_STRING")
    
    if experiment_name and db_name and connection_string:
        print(f"\nSaving to MongoDB (experiment: {experiment_name})...")
        config = {
            "batch_size": args.batch_size,
            "use_rag": args.use_rag,
            "max_questions": args.max_questions
        }
        save_to_mongodb(experiment_name, args.model, metrics, db_name, connection_string,
                       execution_time, config)
    else:
        if not experiment_name:
            print("\n⚠ EXPERIMENT_NAME not set, skipping MongoDB save")
        elif not db_name or not connection_string:
            print("\n⚠ MongoDB not fully configured (missing DB_NAME or CONNECTION_STRING), skipping save")
    
    print("\n" + "=" * 60)
    print(f"LoCoMo evaluation completed successfully!")
    print(f"Execution time: {execution_time:.2f} seconds")
    print("=" * 60)


if __name__ == '__main__':
    main()
