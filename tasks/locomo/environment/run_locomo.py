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
import subprocess

# MongoDB import (optional)
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not installed, MongoDB saving disabled")


# PAM Agent Functions
def run_pam_for_sample(sample: Dict, sample_index: int, args, data_file: str) -> Dict:
    """
    Run PAM agent for a single sample.
    
    PAM processes the conversation history into a memory structure,
    then answers questions based on that memory.
    """
    sample_id = sample.get('sample_id', f'sample_{sample_index}')
    
    print(f"\n{'='*60}")
    print(f"Running PAM Agent for sample: {sample_id}")
    print(f"{'='*60}")
    
    # Set environment variables for PAM scripts
    env = os.environ.copy()
    env['DATA_FILE'] = data_file
    env['SAMPLE_INDEX'] = str(sample_index)
    env['MAX_QUESTIONS'] = str(args.max_questions)
    
    # Run the main PAM orchestrator script
    pam_script = '/task_data/run_pam_locomo.sh'
    
    if os.path.exists(pam_script):
        try:
            result = subprocess.run(
                ['bash', pam_script],
                env=env,
                cwd='/workspace',
                capture_output=False,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                print(f"Warning: PAM script returned non-zero exit code: {result.returncode}")
        except subprocess.TimeoutExpired:
            print("Error: PAM script timed out")
        except Exception as e:
            print(f"Error running PAM script: {e}")
    else:
        print(f"Error: PAM script not found at {pam_script}")
        return None
    
    # Find and read PAM answers
    answers = load_pam_answers(sample_id)
    
    return answers


def load_pam_answers(sample_id: str) -> Optional[Dict]:
    """Load PAM answers from the output file."""
    import glob
    
    # Find the latest answers file for this sample
    pattern = f'/task_logs/{sample_id}_*/pam_answers.json'
    answer_files = sorted(glob.glob(pattern), reverse=True)
    
    if not answer_files:
        print(f"Warning: No PAM answers file found for sample {sample_id}")
        return None
    
    answers_file = answer_files[0]
    print(f"Loading PAM answers from: {answers_file}")
    
    try:
        with open(answers_file, 'r') as f:
            answers = json.load(f)
        return answers
    except Exception as e:
        print(f"Error loading PAM answers: {e}")
        return None


def get_pam_answers(data: Dict, out_data: Dict, prediction_key: str, args, sample_index: int, data_file: str) -> Dict:
    """
    Get answers from PAM agent for a locomo sample.
    
    This is the PAM equivalent of get_gpt_answers().
    """
    sample_id = data.get('sample_id', f'sample_{sample_index}')
    
    # Run PAM for this sample
    pam_answers = run_pam_for_sample(data, sample_index, args, data_file)
    
    if pam_answers is None:
        print("Warning: PAM returned no answers, using empty predictions")
        pam_answers = []
    
    # Map PAM answers to the out_data format
    for i, qa in enumerate(out_data['qa']):
        # Find matching PAM answer by question number
        pam_answer = None
        for pa in pam_answers:
            if pa.get('question_num') == i + 1:
                pam_answer = pa.get('pam_answer', '')
                break
        
        if pam_answer is None:
            pam_answer = ''
            print(f"Warning: No PAM answer found for question {i + 1}")
        
        # Store the PAM prediction
        out_data['qa'][i][prediction_key] = pam_answer
    
    return out_data


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
                        help='Model to evaluate (gpt-4-turbo, gpt-3.5-turbo, claude-sonnet, gemini-pro-1.0, pam)')
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
    parser.add_argument('--sample-index', type=int, default=-1,
                        help='Process only this sample index (-1 = all samples)')
    return parser.parse_args()


def calculate_metrics(out_samples: Dict, model_key: str, prediction_key: str) -> tuple:
    """Calculate aggregate metrics from evaluation results and extract incorrect responses."""
    total_questions = 0
    total_f1 = 0.0
    correct_count = 0
    category_counts = {}
    category_f1_sums = {}
    incorrect_responses = []
    question_num = 0
    
    # F1 threshold for considering an answer "correct"
    F1_THRESHOLD = 0.5
    
    for sample_id, sample in out_samples.items():
        for qa in sample.get('qa', []):
            question_num += 1
            total_questions += 1
            f1_score = qa.get(f'{model_key}_f1', 0.0)
            total_f1 += f1_score
            
            # Count as correct if F1 >= threshold
            if f1_score >= F1_THRESHOLD:
                correct_count += 1
            else:
                # Extract incorrect response for report
                incorrect_responses.append({
                    "question_num": question_num,
                    "sample_id": sample_id,
                    "question": qa.get('question', 'N/A'),
                    "expected_answer": str(qa.get('answer', 'N/A')),
                    "model_answer": qa.get(prediction_key, 'N/A'),
                    "f1_score": round(f1_score, 3),
                    "category": qa.get('category', 0),
                    "evidence": qa.get('evidence', [])
                })
            
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
        category_accuracy[f'category_{cat}_accuracy'] = round(category_f1_sums[cat] / count, 4) if count > 0 else 0.0
        category_accuracy[f'category_{cat}_count'] = count
    
    metrics = {
        'total_questions': total_questions,
        'correct_count': correct_count,
        'incorrect_count': len(incorrect_responses),
        'overall_accuracy': round(overall_accuracy, 4),
        'total_f1_sum': round(total_f1, 4),
        **category_accuracy
    }
    
    return metrics, incorrect_responses


def save_to_mongodb(experiment_name: str, model: str, metrics: Dict, 
                   db_name: str, connection_string: str,
                   execution_time: float = None,
                   config: Dict = None,
                   incorrect_responses: List[Dict] = None) -> bool:
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
        
        # Add incorrect responses if provided (for report generation)
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
        print(f"✓ Results saved to MongoDB: experiment='{experiment_name}', model='{model}', ID={result.inserted_id}")
        print(f"  Saved {len(incorrect_responses) if incorrect_responses else 0} incorrect responses for report generation")
        
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
    
    if args.model == 'pam':
        # PAM uses Claude Code - no special API initialization needed
        print(f"Initialized PAM agent (using Claude Code)")
        print("Note: PAM processes conversations into memory structure before answering")
        
    elif 'gpt' in args.model:
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
    
    # Filter samples if sample-index is specified
    if args.sample_index >= 0:
        if args.sample_index >= len(samples):
            print(f"Error: sample-index {args.sample_index} out of range (max: {len(samples) - 1})")
            return
        samples_to_process = [(args.sample_index, samples[args.sample_index])]
        print(f"Processing only sample index {args.sample_index}")
    else:
        samples_to_process = list(enumerate(samples))
    
    # Process each sample
    for sample_index, data in samples_to_process:
        print(f"\nProcessing sample: {data['sample_id']} (index: {sample_index})")
        
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
        if args.model == 'pam':
            answers = get_pam_answers(data, out_data, prediction_key, args, sample_index, args.data_file)
        elif 'gpt' in args.model:
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
    
    # Calculate metrics and extract incorrect responses for MongoDB
    metrics, incorrect_responses = calculate_metrics(out_samples, model_key, prediction_key)
    print(f"\nMetrics Summary:")
    print(f"  Total questions: {metrics['total_questions']}")
    print(f"  Correct answers: {metrics['correct_count']}")
    print(f"  Incorrect answers: {metrics['incorrect_count']}")
    print(f"  Overall accuracy (F1): {metrics['overall_accuracy']}")
    
    # Save to MongoDB if configured (skip for PAM - it saves via pam_evaluate.py)
    if args.model == 'pam':
        print("\n⚠ Skipping MongoDB save in run_locomo.py (PAM saves via pam_evaluate.py)")
    else:
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
                           execution_time, config, incorrect_responses)
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
