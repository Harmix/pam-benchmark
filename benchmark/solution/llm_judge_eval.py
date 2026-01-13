#!/usr/bin/env python3
"""
Unified LLM-as-Judge Evaluation Pipeline
Extracts Q/A pairs from configs and runs evaluation automatically
"""

import os
import re
import json
import yaml
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from pymongo import MongoClient
from datetime import datetime


# ============================================================================
# CONFIGURATION LOADING
# ============================================================================

def load_config_yaml(config_path: str) -> Dict:
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_prompt_template(template_path: str) -> str:
    """Load the LLM judge prompt template"""
    with open(template_path, 'r') as f:
        return f.read()


# ============================================================================
# CONFIG DISCOVERY
# ============================================================================

def discover_configs(output_dir: Path, test_configs_dir: Path) -> List[Tuple[str, Path, Path]]:
    """Discover all configs from test_configs and find their questions folders in outputs"""
    configs = []

    # Find all YAML files in test_configs
    for yaml_path in test_configs_dir.glob("*.yaml"):
        config_base = yaml_path.stem  # e.g., "config_1" from "config_1.yaml"

        # Look for matching questions folder in outputs
        questions_folder = None
        for output_subdir in output_dir.iterdir():
            if not output_subdir.is_dir():
                continue

            # Check if this output dir matches the config (with or without timestamp)
            if output_subdir.name == config_base or output_subdir.name.startswith(f"{config_base}_"):
                questions_dir = output_subdir / "questions"
                if questions_dir.exists():
                    questions_folder = output_subdir
                    break

        if questions_folder:
            configs.append((questions_folder.name, yaml_path, questions_folder))
        else:
            print(f"Warning: No questions folder found for {config_base}")

    return sorted(configs)


# ============================================================================
# ANSWER EXTRACTION
# ============================================================================

def extract_agent_answer(log_content: str) -> str:
    """Extract the agent's answer from the log file"""
    # Try to find content in code blocks
    code_block_pattern = r'```(?:\w+)?\s*(.*?)```'
    matches = re.findall(code_block_pattern, log_content, re.DOTALL)

    if matches:
        # Return the last code block content (usually the final answer)
        return matches[-1].strip()

    # If no code blocks, return the entire content
    return log_content.strip()


# ============================================================================
# PYDANTIC MODEL
# ============================================================================

class EvaluationResult(BaseModel):
    """Pydantic model for LLM judge evaluation result"""
    score: float = Field(ge=0.0, le=1.0, description="Score between 0.0 and 1.0")
    is_correct: bool = Field(description="Whether the answer is correct")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the evaluation")
    reasoning: str = Field(description="Brief explanation of the evaluation")


# ============================================================================
# LLM JUDGE
# ============================================================================

def call_openai_judge(
    question: str,
    expected_answer: str,
    agent_answer: str,
    model: str = "gpt-4.1",
    prompt_template: str = None,
    save_raw: bool = False,
    raw_output_dir: Path = None,
    question_num: int = None,
    config_name: str = None
) -> Dict:
    """Call OpenAI Responses API to judge the answer using Pydantic structured output"""

    if prompt_template is None:
        prompt_template = """You are evaluating whether an AI agent correctly answered a memory-related question
about a workplace timeline.

QUESTION: {question}
EXPECTED ANSWER: {expected_answer}
AGENT'S EXTRACTED ANSWER: {extracted_answer}

Your task is to determine if the agent's answer is correct. Consider:
1. Exact matches are obviously correct
2. Semantic equivalence (same meaning, different wording)
3. Partial correctness (got part of a multi-part answer right)
4. Reasonable interpretations of ambiguous questions

Examples:
- If expected "done" and agent said "completed": score 1.0, correct true
- If expected "alice, bob" and agent said "alice": score 0.5, correct false
- If expected "in_progress, charlie" and agent said "in_progress, urgent, charlie": score 1.0, correct true (extra info OK)
- If completely wrong: score 0.0, correct false"""

    system_prompt = prompt_template.format(
        question=question,
        expected_answer=expected_answer,
        extracted_answer=agent_answer
    )

    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        response = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Please evaluate this answer."}
            ],
            text_format=EvaluationResult,
        )

        # Extract the parsed result
        result = response.output_parsed

        # Save raw response if requested
        if save_raw and raw_output_dir and question_num and config_name:
            raw_output_dir.mkdir(parents=True, exist_ok=True)
            raw_file = raw_output_dir / f"question_{question_num}_raw.json"

            raw_data = {
                "config": config_name,
                "question_num": question_num,
                "question": question,
                "expected_answer": expected_answer,
                "agent_answer": agent_answer,
                "model": model,
                "system_prompt": system_prompt,
                "response": {
                    "id": response.id,
                    "created_at": response.created_at,
                    "model": response.model,
                    "status": response.status,
                    "output_parsed": result.model_dump()
                }
            }

            with open(raw_file, 'w') as f:
                json.dump(raw_data, f, indent=2)

        # Convert Pydantic model to dict
        return result.model_dump()

    except Exception as e:
        return {
            "score": 0.0,
            "is_correct": False,
            "confidence": 0.0,
            "reasoning": f"Error calling OpenAI API: {str(e)}"
        }


# ============================================================================
# EVALUATION
# ============================================================================

def evaluate_single_question(
    config_dir: Path,
    question_num: int,
    question: str,
    expected_answer: str,
    model: str,
    prompt_template: str,
    config_name: str,
    save_raw: bool = False
) -> Tuple[int, Dict]:
    """Evaluate a single question"""

    log_file = config_dir / "questions" / f"question_{question_num}.log"

    if not log_file.exists():
        return question_num, {
            "score": 0.0,
            "is_correct": False,
            "confidence": 0.0,
            "reasoning": f"Log file not found: {log_file}",
            "agent_answer": "[LOG FILE NOT FOUND]"
        }

    # Read log file
    with open(log_file, 'r') as f:
        log_content = f.read()

    # Extract agent answer
    agent_answer = extract_agent_answer(log_content)

    # Setup raw output directory if saving
    raw_output_dir = None
    if save_raw:
        raw_output_dir = config_dir / "judge-eval"


    # Call OpenAI judge
    result = call_openai_judge(
        question=question,
        expected_answer=expected_answer,
        agent_answer=agent_answer,
        model=model,
        prompt_template=prompt_template,
        save_raw=save_raw,
        raw_output_dir=raw_output_dir,
        question_num=question_num,
        config_name=config_name
    )

    # Add agent answer to result
    result["agent_answer"] = agent_answer

    return question_num, result


def evaluate_config(
    config_name: str,
    config_dir: Path,
    questions: List[str],
    expected_answers: List[str],
    model: str = "gpt-4o",
    parallel: int = 1,
    prompt_template: str = None,
    save_raw: bool = False
) -> Dict:
    """Evaluate all questions for a configuration"""

    results = {}

    if parallel == 1:
        # Sequential evaluation
        for i, (question, expected) in enumerate(zip(questions, expected_answers), 1):
            print(f"  Question {i}/{len(questions)}...", end=" ", flush=True)
            _, result = evaluate_single_question(
                config_dir, i, question, expected, model, prompt_template, config_name, save_raw
            )
            results[i] = result
            status = "✓" if result.get("is_correct", False) else "✗"
            print(status)
    else:
        # Parallel evaluation
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(
                    evaluate_single_question,
                    config_dir, i, question, expected, model, prompt_template, config_name, save_raw
                ): i
                for i, (question, expected) in enumerate(zip(questions, expected_answers), 1)
            }

            for future in as_completed(futures):
                question_num, result = future.result()
                results[question_num] = result
                status = "✓" if result.get("is_correct", False) else "✗"
                print(f"  Question {question_num}/{len(questions)}... {status}")

    return results


# ============================================================================
# RESULTS OUTPUT
# ============================================================================

def print_config_results(config_name: str, results: Dict, questions: List[str], expected_answers: List[str]):
    """Print results for a single config"""
    total = len(results)
    correct = sum(1 for r in results.values() if r.get("is_correct", False))
    avg_score = sum(r.get("score", 0.0) for r in results.values()) / total if total > 0 else 0.0

    print(f"\n{'=' * 80}")
    print(f"CONFIG: {config_name}")
    print(f"{'=' * 80}")

    for q_num in sorted(results.keys()):
        result = results[q_num]
        status = "✓ CORRECT" if result.get("is_correct", False) else "✗ INCORRECT"

        print(f"\nQuestion {q_num}: {status}")
        print(f"  Q: {questions[q_num - 1]}")
        print(f"  Expected: {expected_answers[q_num - 1]}")
        print(f"  Score: {result.get('score', 0.0):.2f}")
        print(f"  Confidence: {result.get('confidence', 0.0):.2f}")
        print(f"  Reasoning: {result.get('reasoning', 'N/A')}")

    print(f"\n{'-' * 80}")
    print(f"Summary: {correct}/{total} correct ({correct/total*100:.1f}%), Avg Score: {avg_score:.2f}")


def extract_base_config_name(config_name: str) -> str:
    """Extract base config name without timestamp suffix
    
    Examples:
        "config_2_20260113_024345" -> "config_2"
        "config_1" -> "config_1"
    """
    # Pattern: config_name_YYYYMMDD_HHMMSS
    # Try to match timestamp pattern at the end
    # Match pattern: _ followed by 8 digits, underscore, 6 digits at the end
    pattern = r'^(.+)_\d{8}_\d{6}$'
    match = re.match(pattern, config_name)
    if match:
        return match.group(1)
    return config_name


def extract_metadata_from_config(config: Dict, config_name: str, yaml_filename: str = None) -> Dict[str, str]:
    """Extract metadata fields from config YAML"""
    agent_name = config.get("agent", {}).get("name", "unknown")
    
    # Extract dataset name from event_history path
    benchmark = config.get("benchmark", {})
    event_history = benchmark.get("event_history", "")
    dataset_name = "unknown"
    if event_history:
        # Extract filename without extension (e.g., "event_history_1" from "test_event_histories/event_history_1.json")
        dataset_name = Path(event_history).stem
    
    # Extract base config name (without timestamp suffix)
    # Prefer yaml filename if available, otherwise try to extract from config_name
    if yaml_filename:
        base_config_name = Path(yaml_filename).stem  # e.g., "config_2.yaml" -> "config_2"
    else:
        base_config_name = extract_base_config_name(config_name)
    
    # Task name is the Harbor project name (default: "benchmark")
    # Can be overridden via HARBOR_PROJECT_NAME environment variable
    task_name = os.environ.get("HARBOR_PROJECT_NAME", "benchmark")
    
    return {
        "config_name": base_config_name,
        "dataset_name": dataset_name,
        "agent_name": agent_name,
        "task_name": task_name
    }


def save_to_mongodb(experiment_name: str, metadata: Dict[str, str], metrics: Dict, 
                   db_name: str, connection_string: str, execution_time: float = None) -> bool:
    """Save evaluation results to MongoDB - one record per config"""
    try:
        # Create document with experiment name and metadata
        mongo_data = {
            "experiment_name": experiment_name,
            "config_name": metadata["config_name"],
            "dataset_name": metadata["dataset_name"],
            "agent_name": metadata["agent_name"],
            "task_name": metadata["task_name"],
            **metrics  # Include all metrics (total_questions, correct_count, accuracy, etc.)
        }
        
        # Add execution time if provided
        if execution_time is not None:
            mongo_data["execution_time_seconds"] = float(execution_time)
        
        # Add timestamp
        timestamp = datetime.utcnow()
        mongo_data["timestamp"] = timestamp
        mongo_data["created_at"] = timestamp.isoformat()
        
        # Connect to MongoDB
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        
        db = client[db_name]
        collection = db["evaluation_results"]
        
        # Insert document
        result = collection.insert_one(mongo_data)
        print(f"✓ Results saved to MongoDB: experiment='{experiment_name}', config='{metadata['config_name']}', ID={result.inserted_id}")
        
        client.close()
        return True
    except Exception as e:
        print(f"⚠ Warning: Failed to save to MongoDB: {str(e)}")
        print(f"   Database: {db_name}, Connection: {'configured' if connection_string else 'not set'}")
        return False


def calculate_metrics(results: Dict) -> Dict:
    """Calculate evaluation metrics from results"""
    total = len(results)
    correct = sum(1 for r in results.values() if r.get("is_correct", False))
    avg_score = sum(r.get("score", 0.0) for r in results.values()) / total if total > 0 else 0.0
    avg_confidence = sum(r.get("confidence", 0.0) for r in results.values()) / total if total > 0 else 0.0
    
    return {
        "total_questions": total,
        "correct_count": correct,
        "accuracy": correct / total if total > 0 else 0.0,
        "avg_score": avg_score,
        "avg_confidence": avg_confidence
    }


def save_config_results(config_dir: Path, config_name: str, config_yaml: str, model: str,
                       questions: List[str], expected_answers: List[str], results: Dict,
                       experiment_name: str = None, config: Dict = None, execution_time: float = None):
    """Save results to JSON file and optionally to MongoDB"""
    metrics = calculate_metrics(results)

    output_data = {
        "config": config_name,
        "config_yaml": config_yaml,
        "model": model,
        "summary": metrics,
        "questions": questions,
        "expected_answers": expected_answers,
        "results": results
    }
    
    # Add experiment name if provided
    if experiment_name:
        output_data["experiment_name"] = experiment_name
    
    # Add execution time if provided
    if execution_time is not None:
        output_data["execution_time_seconds"] = float(execution_time)

    # Save to JSON file
    results_file = config_dir / "llm_judge_results.json"
    with open(results_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    # Save to MongoDB if connection string is provided
    db_name = os.environ.get("DB_NAME")
    connection_string = os.environ.get("CONNECTION_STRING")
    
    if connection_string and db_name and experiment_name:
        # Extract metadata from config if provided
        if config:
            metadata = extract_metadata_from_config(config, config_name, yaml_filename=config_yaml)
        else:
            # Fallback if config not provided
            base_config_name = extract_base_config_name(config_name)
            task_name = os.environ.get("HARBOR_PROJECT_NAME", "benchmark")
            metadata = {
                "config_name": base_config_name,
                "dataset_name": "unknown",
                "agent_name": "unknown",
                "task_name": task_name
            }
        
        save_to_mongodb(experiment_name, metadata, metrics, db_name, connection_string, execution_time)
    elif connection_string or db_name:
        if not experiment_name:
            print("⚠ Warning: EXPERIMENT_NAME not set, skipping MongoDB save")
        else:
            print("⚠ Warning: MongoDB CONNECTION_STRING or DB_NAME not fully configured, skipping MongoDB save")

    return results_file


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def load_environment_variables():
    """Load environment variables from .env and secrets.env"""
    load_dotenv()  # loads .env from current working directory
    
    # Also try to load from secrets.env if it exists (for Harbor runs)
    secrets_env_path = Path("/workspace/secrets.env")
    if secrets_env_path.exists():
        from dotenv import dotenv_values
        secrets = dotenv_values(secrets_env_path)
        for key, value in secrets.items():
            if value and key not in os.environ:
                os.environ[key] = value


def validate_configuration() -> Tuple[str, str, str]:
    """Validate required configuration and return MongoDB settings and experiment name"""
    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        return None, None, None
    
    # Get experiment name (optional, but recommended for MongoDB)
    experiment_name = os.environ.get("EXPERIMENT_NAME", "")
    if not experiment_name:
        print("⚠ Warning: EXPERIMENT_NAME not set - MongoDB saves will be skipped")
    
    # Check MongoDB configuration (optional, will warn if not set)
    db_name = os.environ.get("DB_NAME")
    connection_string = os.environ.get("CONNECTION_STRING")
    if connection_string and db_name:
        print(f"✓ MongoDB configured: database='{db_name}'")
    elif connection_string or db_name:
        print("⚠ Warning: MongoDB partially configured (missing DB_NAME or CONNECTION_STRING)")
    else:
        print("ℹ MongoDB not configured - results will only be saved to JSON files")
    
    return db_name, connection_string, experiment_name


def process_single_config(config_name: str, yaml_path: Path, config_dir: Path,
                         model: str, parallel: int, prompt_template: str,
                         save_raw: bool, experiment_name: str, summary_only: bool,
                         execution_time: float = None) -> Dict:
    """Process a single config: load, evaluate, save, and return results"""
    print(f"\n{'=' * 80}")
    print(f"Processing: {config_name}")
    print(f"YAML: {yaml_path.name}")
    print(f"{'=' * 80}")

    # Load config YAML
    try:
        config = load_config_yaml(str(yaml_path))
    except Exception as e:
        print(f"Error loading YAML: {e}")
        return None

    # Determine model (use override if provided, otherwise from config)
    model = determine_model_from_config(config, model)

    # Extract questions and expected answers
    benchmark = config.get("benchmark", {})
    questions = benchmark.get("questions", [])
    expected_answers = benchmark.get("expected_answers", [])

    if not questions or not expected_answers:
        print("No questions/answers found in config")
        return None

    if len(questions) != len(expected_answers):
        print("Mismatch between questions and expected answers")
        return None

    print(f"Questions: {len(questions)}")
    print(f"Model: {model}")
    print()

    # Run evaluation
    results = evaluate_config(
        config_name=config_name,
        config_dir=config_dir,
        questions=questions,
        expected_answers=expected_answers,
        model=model,
        parallel=parallel,
        prompt_template=prompt_template,
        save_raw=save_raw
    )

    # Try to read execution time from file if not provided
    if execution_time is None:
        execution_time_file = config_dir / "execution_time.txt"
        if execution_time_file.exists():
            try:
                with open(execution_time_file, 'r') as f:
                    execution_time = float(f.read().strip())
                print(f"Read execution time from file: {execution_time} seconds")
            except (ValueError, IOError) as e:
                print(f"Warning: Could not read execution time from file: {e}")

    # Also check environment variable (set by setup_and_run.sh)
    if execution_time is None:
        env_execution_time = os.environ.get("EXPORT_EXECUTION_TIME")
        if env_execution_time:
            try:
                execution_time = float(env_execution_time)
                print(f"Read execution time from environment: {execution_time} seconds")
            except ValueError:
                pass

    # Save results
    results_file = save_config_results(
        config_dir, config_name, yaml_path.name, model,
        questions, expected_answers, results,
        experiment_name=experiment_name, config=config, execution_time=execution_time
    )

    # Calculate and log metrics
    metrics = calculate_metrics(results)

    # Log metrics for this config
    print(f"\n{'=' * 80}")
    print(f"METRICS FOR CONFIG: {config_name}")
    print(f"{'=' * 80}")
    print(f"  total_questions:  {metrics['total_questions']}")
    print(f"  correct_count:    {metrics['correct_count']}")
    print(f"  accuracy:         {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
    print(f"  avg_score:        {metrics['avg_score']:.4f}")
    print(f"  avg_confidence:   {metrics['avg_confidence']:.4f}")
    if execution_time is not None:
        print(f"  execution_time:   {execution_time:.2f} seconds")
    print(f"{'=' * 80}")
    print(f"\n✓ Results saved to: {results_file}")

    # Print detailed results unless summary-only
    if not summary_only:
        print_config_results(config_name, results, questions, expected_answers)

    return {
        "results": results,
        "questions": questions,
        "expected_answers": expected_answers,
        "model": model,
        "metrics": metrics
    }


def print_overall_summary(all_results: Dict):
    """Print overall summary across all configs"""
    print(f"\n\n{'=' * 80}")
    print("OVERALL SUMMARY")
    print(f"{'=' * 80}")

    total_questions = 0
    total_correct = 0

    for config_name, data in all_results.items():
        if data is None:
            continue
        results = data["results"]
        correct = sum(1 for r in results.values() if r.get("is_correct", False))
        total = len(results)

        total_questions += total
        total_correct += correct

        print(f"{config_name}: {correct}/{total} ({correct/total*100:.1f}%)")

    print(f"\n{'-' * 80}")
    if total_questions > 0:
        print(f"TOTAL: {total_correct}/{total_questions} correct ({total_correct/total_questions*100:.1f}%)")
    else:
        print("TOTAL: No valid results")
    print(f"{'=' * 80}")


def discover_configs_for_evaluation(args, output_dir: Path, test_configs_dir: Path) -> List[Tuple[str, Path, Path]]:
    """Discover configs to evaluate based on arguments"""
    if args.config:
        # Find specific config
        configs = []
        yaml_path = test_configs_dir / f"{args.config}.yaml"
        if not yaml_path.exists():
            print(f"Error: Could not find YAML for config: {args.config}")
            return []

        # Find matching output folder
        for output_subdir in output_dir.iterdir():
            if not output_subdir.is_dir():
                continue
            if output_subdir.name == args.config or output_subdir.name.startswith(f"{args.config}_"):
                questions_dir = output_subdir / "questions"
                if questions_dir.exists():
                    configs = [(output_subdir.name, yaml_path, output_subdir)]
                    break

        if not configs:
            print(f"Error: No questions folder found for config: {args.config}")
            return []
    else:
        configs = discover_configs(output_dir, test_configs_dir)
    
    return configs


def determine_model_from_config(config: Dict, override_model: str = None) -> str:
    """Determine which model to use for evaluation"""
    if override_model:
        return override_model
    
    eval_config = config.get("evaluation", {})
    llm_judge_config = eval_config.get("llm_judge", {})
    model = llm_judge_config.get("model", "gpt-4o")
    if ":" in model:
        model = model.split(":", 1)[1]
    
    return model


def main():
    parser = argparse.ArgumentParser(
        description="Unified LLM-as-Judge Evaluation Pipeline"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./outputs",
        help="Path to the output directory containing config folders"
    )
    parser.add_argument(
        "--test-configs-dir",
        type=str,
        default="./test_configs",
        help="Path to directory containing config YAML files"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Specific config to evaluate (default: all configs)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="OpenAI model to use (overrides config files)"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of parallel evaluations per config (default: 1)"
    )
    parser.add_argument(
        "--prompt-template",
        type=str,
        default=None,
        help="Path to custom prompt template file"
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Show only summary, skip detailed results"
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Save raw OpenAI responses to judge-eval folder"
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default=None,
        help="Experiment name for MongoDB (overrides EXPERIMENT_NAME env var)"
    )

    args = parser.parse_args()
    
    # Load environment variables
    load_environment_variables()
    
    # Validate configuration
    db_name, connection_string, experiment_name_env = validate_configuration()
    if db_name is None and connection_string is None and experiment_name_env is None:
        # This means OPENAI_API_KEY was missing
        return 1
    
    # Use experiment name from command line argument, or environment variable, or generate one
    experiment_name = args.experiment_name or experiment_name_env
    if not experiment_name:
        # Generate a default experiment name if still not set
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_name = f"experiment_{timestamp}"
        print(f"⚠ No experiment name provided, using generated name: {experiment_name}")
    else:
        print(f"✓ Using experiment name: {experiment_name}")

    # Validate paths
    output_dir = Path(args.output_dir)
    test_configs_dir = Path(args.test_configs_dir)

    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        return 1

    if not test_configs_dir.exists():
        print(f"Error: Test configs directory not found: {test_configs_dir}")
        return 1

    # Load custom prompt template if provided
    prompt_template = None
    if args.prompt_template:
        prompt_template = load_prompt_template(args.prompt_template)

    # Discover configs
    configs = discover_configs_for_evaluation(args, output_dir, test_configs_dir)

    if not configs:
        print("No configs found to evaluate")
        return 1

    print(f"{'=' * 80}")
    print(f"LLM-AS-JUDGE EVALUATION PIPELINE")
    print(f"{'=' * 80}")
    print(f"Configs to evaluate: {len(configs)}")
    print(f"Parallel workers: {args.parallel}")
    if experiment_name:
        print(f"Experiment name: {experiment_name}")
    print(f"{'=' * 80}\n")

    # Track overall statistics
    all_results = {}

    # Process each config
    for config_name, yaml_path, config_dir in configs:
        # Try to read execution time from file
        execution_time = None
        execution_time_file = config_dir / "execution_time.txt"
        if execution_time_file.exists():
            try:
                with open(execution_time_file, 'r') as f:
                    execution_time = float(f.read().strip())
            except (ValueError, IOError):
                pass
        
        # Process config (it will load the config internally)
        result = process_single_config(
            config_name=config_name,
            yaml_path=yaml_path,
            config_dir=config_dir,
            model=args.model,  # Pass override model, config loading happens inside
            parallel=args.parallel,
            prompt_template=prompt_template,
            save_raw=args.save_raw,
            experiment_name=experiment_name,
            summary_only=args.summary_only,
            execution_time=execution_time
        )

        if result:
            all_results[config_name] = result

    # Print overall summary
    print_overall_summary(all_results)

    return 0


if __name__ == "__main__":
    exit(main())
