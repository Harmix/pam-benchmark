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

# Add task_data to path for imports
sys.path.insert(0, '/task_data')

from global_methods import set_openai_key, set_anthropic_key, set_gemini_key
from task_eval.evaluation import eval_question_answering
from task_eval.evaluation_stats import analyze_aggr_acc
from task_eval.gpt_utils import get_gpt_answers
from task_eval.claude_utils import get_claude_answers
from task_eval.gemini_utils import get_gemini_answers

import google.generativeai as genai


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
    return parser.parse_args()


def main():
    # Load API keys from secrets.env
    load_secrets()
    
    # Parse arguments
    args = parse_args()
    
    print("=" * 60)
    print(f"LoCoMo Benchmark Evaluation")
    print(f"Model: {args.model}")
    print(f"Data file: {args.data_file}")
    print(f"Output file: {args.out_file}")
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
        
        out_data = {'sample_id': data['sample_id']}
        if data['sample_id'] in out_samples:
            out_data['qa'] = out_samples[data['sample_id']]['qa'].copy()
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
    
    print("\n" + "=" * 60)
    print("LoCoMo evaluation completed successfully!")
    print("=" * 60)


if __name__ == '__main__':
    main()
