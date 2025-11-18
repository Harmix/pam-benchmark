#!/usr/bin/env python3
"""
Extract Question/Answer Pairs from Config Outputs
Shows questions, agent answers, and expected answers for all configs
"""

import os
import re
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import yaml
import json


def load_config_yaml(config_path: str) -> Dict:
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def extract_agent_answer(log_content: str) -> str:
    """Extract the agent's answer from the log file"""
    # Try to find content in code blocks
    code_block_pattern = r'```(?:\w+)?\s*(.*?)```'
    matches = re.findall(code_block_pattern, log_content, re.DOTALL)

    if matches:
        # Return the last code block content (usually the final answer)
        return matches[-1].strip()

    # If no code blocks, return the entire content (truncated for display)
    content = log_content.strip()
    if len(content) > 500:
        return content[:500] + "..."
    return content


def find_config_yaml(config_name: str, test_configs_dir: Path) -> Path:
    """Find the corresponding config YAML file for a config directory"""
    # Extract base config name (e.g., "config_1" from "config_1_20251029_130807")
    base_name = config_name.split('_')[0] + '_' + config_name.split('_')[1]

    # Try exact match first
    exact_match = test_configs_dir / f"{base_name}.yaml"
    if exact_match.exists():
        return exact_match

    # Try without timestamp
    base_name_simple = '_'.join(config_name.split('_')[:2])
    simple_match = test_configs_dir / f"{base_name_simple}.yaml"
    if simple_match.exists():
        return simple_match

    return None


def extract_qa_pairs(
    output_dir: Path,
    config_name: str,
    test_configs_dir: Path
) -> List[Dict]:
    """Extract question/answer pairs for a single config"""

    config_dir = output_dir / config_name
    if not config_dir.exists():
        return []

    questions_dir = config_dir / "questions"
    if not questions_dir.exists():
        return []

    # Find corresponding config YAML
    config_yaml_path = find_config_yaml(config_name, test_configs_dir)
    if not config_yaml_path:
        print(f"Warning: Could not find config YAML for {config_name}")
        return []

    # Load config to get questions and expected answers
    try:
        config = load_config_yaml(str(config_yaml_path))
        benchmark = config.get("benchmark", {})
        questions = benchmark.get("questions", [])
        expected_answers = benchmark.get("expected_answers", [])
    except Exception as e:
        print(f"Error loading config {config_yaml_path}: {e}")
        return []

    if not questions or not expected_answers:
        return []

    # Extract pairs
    pairs = []
    for i, (question, expected) in enumerate(zip(questions, expected_answers), 1):
        log_file = questions_dir / f"question_{i}.log"

        if log_file.exists():
            with open(log_file, 'r') as f:
                log_content = f.read()
            agent_answer = extract_agent_answer(log_content)
        else:
            agent_answer = "[LOG FILE NOT FOUND]"

        pairs.append({
            "config": config_name,
            "config_yaml": str(config_yaml_path.name),
            "question_num": i,
            "question": question,
            "expected_answer": expected,
            "agent_answer": agent_answer
        })

    return pairs


def format_pair(pair: Dict, verbose: bool = False) -> str:
    """Format a single Q/A pair for display"""
    output = []
    output.append("=" * 80)
    output.append(f"Config: {pair['config']}")
    output.append(f"Config YAML: {pair['config_yaml']}")
    output.append(f"Question #{pair['question_num']}")
    output.append("-" * 80)
    output.append(f"QUESTION:")
    output.append(f"  {pair['question']}")
    output.append("")
    output.append(f"EXPECTED ANSWER:")
    output.append(f"  {pair['expected_answer']}")
    output.append("")
    output.append(f"AGENT ANSWER:")

    # Format agent answer with indentation
    agent_lines = pair['agent_answer'].split('\n')
    for line in agent_lines[:20]:  # Limit lines unless verbose
        output.append(f"  {line}")

    if not verbose and len(agent_lines) > 20:
        output.append(f"  ... ({len(agent_lines) - 20} more lines, use --verbose to see all)")

    output.append("")
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and display question/answer pairs from all configs"
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
        help="Specific config to process (default: all configs)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full agent answers without truncation"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Save results to JSON file"
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    test_configs_dir = Path(args.test_configs_dir)

    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        return 1

    if not test_configs_dir.exists():
        print(f"Error: Test configs directory not found: {test_configs_dir}")
        return 1

    # Determine which configs to process
    if args.config:
        config_names = [args.config]
    else:
        # Find all config directories
        config_names = [d.name for d in output_dir.iterdir() if d.is_dir() and d.name.startswith('config_')]
        config_names.sort()

    print(f"Processing {len(config_names)} config(s)...")
    print()

    # Extract all pairs
    all_pairs = []
    for config_name in config_names:
        pairs = extract_qa_pairs(output_dir, config_name, test_configs_dir)
        all_pairs.extend(pairs)
        print(f"✓ {config_name}: {len(pairs)} question(s)")

    print()
    print(f"Total: {len(all_pairs)} question/answer pairs")
    print()

    # Display pairs
    for pair in all_pairs:
        print(format_pair(pair, verbose=args.verbose))

    # Save to JSON if requested
    if args.output_json:
        output_file = Path(args.output_json)
        with open(output_file, 'w') as f:
            json.dump(all_pairs, f, indent=2)
        print(f"\n✓ Results saved to: {output_file}")

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    configs_processed = len(set(p['config'] for p in all_pairs))
    total_questions = len(all_pairs)

    print(f"Configs processed: {configs_processed}")
    print(f"Total questions: {total_questions}")

    # Count by config
    print("\nQuestions per config:")
    config_counts = {}
    for pair in all_pairs:
        config = pair['config']
        config_counts[config] = config_counts.get(config, 0) + 1

    for config, count in sorted(config_counts.items()):
        print(f"  {config}: {count}")

    return 0


if __name__ == "__main__":
    exit(main())