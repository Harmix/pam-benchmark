#!/usr/bin/env python3
"""
Unified LLM-as-Judge Evaluation Pipeline
Extracts Q/A pairs from configs and runs evaluation automatically
"""

import os
import json
import re
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
import yaml
from openai import OpenAI
from pydantic import BaseModel, Field


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


def save_config_results(config_dir: Path, config_name: str, config_yaml: str, model: str,
                       questions: List[str], expected_answers: List[str], results: Dict):
    """Save results to JSON file"""
    total = len(results)
    correct = sum(1 for r in results.values() if r.get("is_correct", False))
    avg_score = sum(r.get("score", 0.0) for r in results.values()) / total if total > 0 else 0.0
    avg_confidence = sum(r.get("confidence", 0.0) for r in results.values()) / total if total > 0 else 0.0

    output_data = {
        "config": config_name,
        "config_yaml": config_yaml,
        "model": model,
        "summary": {
            "total_questions": total,
            "correct_count": correct,
            "accuracy": correct / total if total > 0 else 0.0,
            "avg_score": avg_score,
            "avg_confidence": avg_confidence
        },
        "questions": questions,
        "expected_answers": expected_answers,
        "results": results
    }

    results_file = config_dir / "llm_judge_results.json"
    with open(results_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    return results_file


# ============================================================================
# MAIN PIPELINE
# ============================================================================

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

    args = parser.parse_args()

    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        return 1

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
    if args.config:
        # Find specific config
        configs = []
        yaml_path = test_configs_dir / f"{args.config}.yaml"
        if not yaml_path.exists():
            print(f"Error: Could not find YAML for config: {args.config}")
            return 1

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
            return 1
    else:
        configs = discover_configs(output_dir, test_configs_dir)

    if not configs:
        print("No configs found to evaluate")
        return 1

    print(f"{'=' * 80}")
    print(f"LLM-AS-JUDGE EVALUATION PIPELINE")
    print(f"{'=' * 80}")
    print(f"Configs to evaluate: {len(configs)}")
    print(f"Parallel workers: {args.parallel}")
    print(f"{'=' * 80}\n")

    # Track overall statistics
    all_results = {}

    # Process each config
    for config_name, yaml_path, config_dir in configs:
        print(f"\n{'=' * 80}")
        print(f"Processing: {config_name}")
        print(f"YAML: {yaml_path.name}")
        print(f"{'=' * 80}")

        # Load config YAML
        try:
            config = load_config_yaml(str(yaml_path))
        except Exception as e:
            print(f"Error loading YAML: {e}")
            continue

        # Extract questions and expected answers
        benchmark = config.get("benchmark", {})
        questions = benchmark.get("questions", [])
        expected_answers = benchmark.get("expected_answers", [])

        if not questions or not expected_answers:
            print("No questions/answers found in config")
            continue

        if len(questions) != len(expected_answers):
            print("Mismatch between questions and expected answers")
            continue

        print(f"Questions: {len(questions)}")

        # Determine model
        if args.model:
            model = args.model
        else:
            eval_config = config.get("evaluation", {})
            llm_judge_config = eval_config.get("llm_judge", {})
            model = 'gpt-4.1'# llm_judge_config.get("model", "gpt-4o")
            if ":" in model:
                model = model.split(":", 1)[1]

        print(f"Model: {model}")
        print()

        # Run evaluation
        results = evaluate_config(
            config_name=config_name,
            config_dir=config_dir,
            questions=questions,
            expected_answers=expected_answers,
            model=model,
            parallel=args.parallel,
            prompt_template=prompt_template,
            save_raw=args.save_raw
        )

        # Save results
        results_file = save_config_results(
            config_dir, config_name, yaml_path.name, model,
            questions, expected_answers, results
        )

        print(f"\n✓ Results saved to: {results_file}")

        # Store for overall summary
        all_results[config_name] = {
            "results": results,
            "questions": questions,
            "expected_answers": expected_answers,
            "model": model
        }

        # Print detailed results unless summary-only
        if not args.summary_only:
            print_config_results(config_name, results, questions, expected_answers)

    # Print overall summary
    print(f"\n\n{'=' * 80}")
    print("OVERALL SUMMARY")
    print(f"{'=' * 80}")

    total_questions = 0
    total_correct = 0

    for config_name, data in all_results.items():
        results = data["results"]
        correct = sum(1 for r in results.values() if r.get("is_correct", False))
        total = len(results)

        total_questions += total
        total_correct += correct

        print(f"{config_name}: {correct}/{total} ({correct/total*100:.1f}%)")

    print(f"\n{'-' * 80}")
    print(f"TOTAL: {total_correct}/{total_questions} correct ({total_correct/total_questions*100:.1f}%)")
    print(f"{'=' * 80}")

    return 0


if __name__ == "__main__":
    exit(main())