import os
import re
import json
import csv
import yaml
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

def load_yaml_files(config_dir: str) -> List[Dict[str, Any]]:
    """Load all YAML files from the test_configs directory."""
    configs = []
    config_path = Path(config_dir)

    if not config_path.exists():
        raise FileNotFoundError(f"Directory {config_dir} does not exist")

    for yaml_file in config_path.glob("*.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                configs.append({
                    'name': yaml_file.stem,
                    'content': config_data
                })
        except Exception as e:
            print(f"Warning: Could not load {yaml_file.name}: {e}")

    return configs

def extract_questions_answers(config_data: Dict) -> Dict[str, List[str]]:
    """Extract questions and expected answers from config."""
    questions = []
    answers = []

    if 'benchmark' in config_data:
        benchmark = config_data['benchmark']

        if 'questions' in benchmark:
            questions = benchmark['questions'] if isinstance(benchmark['questions'], list) else []

        if 'expected_answers' in benchmark:
            answers = benchmark['expected_answers'] if isinstance(benchmark['expected_answers'], list) else []

    return {'questions': questions, 'answers': answers}

def save_qa_to_csv(all_qa_data: List[Dict[str, Any]], filename: str):
    """Save questions and answers to CSV file."""
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)

        # Write header
        writer.writerow(['Config Name', 'Question Index', 'Question', 'Expected Answer'])

        # Write data
        for config_qa in all_qa_data:
            config_name = config_qa['config_name']
            questions = config_qa['questions']
            answers = config_qa['expected_answers']

            # Match questions with answers
            max_items = max(len(questions), len(answers))

            for i in range(max_items):
                question = questions[i] if i < len(questions) else ''
                answer = answers[i] if i < len(answers) else ''

                writer.writerow([
                    config_name,
                    i + 1,
                    question,
                    answer
                ])

def extract_quantitative_data(configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract quantitative metadata from all configurations."""
    metadata = {
        'total_configs': len(configs),
        'models_used': defaultdict(int),
        'evaluators_used': defaultdict(int),
        'evaluator_combinations': defaultdict(int),
        'llm_judge_models': defaultdict(int),
        'agent_names': defaultdict(int),
        'max_turns': defaultdict(int),
        'tools_usage': defaultdict(int),
        'repositories': defaultdict(int),
        'repository_branches': defaultdict(int),
        'teams': defaultdict(int),
        'team_members_count': [],
        'log_levels': defaultdict(int),
        'docker_ports': defaultdict(int),
        'question_count_per_config': [],
        'answer_count_per_config': [],
        'case_sensitive_configs': {'true': 0, 'false': 0, 'not_specified': 0},
        'configs_with_milestones': 0,
        'total_milestones': 0,
        'total_questions': 0,
        'total_answers': 0
    }

    for config in configs:
        data = config['content']

        # Agent configuration
        if 'agent' in data:
            agent = data['agent']

            if 'model' in agent:
                metadata['models_used'][agent['model']] += 1

            if 'name' in agent:
                metadata['agent_names'][agent['name']] += 1

            if 'max_turns' in agent:
                metadata['max_turns'][agent['max_turns']] += 1

            if 'tools' in agent:
                for tool in agent['tools']:
                    metadata['tools_usage'][tool] += 1

        # Repository configuration
        if 'repository' in data:
            repo = data['repository']

            if 'url' in repo:
                metadata['repositories'][repo['url']] += 1

            if 'branch' in repo:
                metadata['repository_branches'][repo['branch']] += 1

        # Linear configuration
        if 'linear' in data:
            linear = data['linear']

            if 'teams' in linear:
                for team in linear['teams']:
                    if 'name' in team:
                        metadata['teams'][team['name']] += 1
                    if 'members' in team:
                        metadata['team_members_count'].append(len(team['members']))

            if 'milestones' in linear and linear['milestones']:
                metadata['configs_with_milestones'] += 1
                metadata['total_milestones'] += len(linear['milestones'])

        # Docker configuration
        if 'docker' in data and 'git_server' in data['docker']:
            if 'expose_port' in data['docker']['git_server']:
                port = data['docker']['git_server']['expose_port']
                metadata['docker_ports'][port] += 1

        # Logging configuration
        if 'logging' in data and 'level' in data['logging']:
            metadata['log_levels'][data['logging']['level']] += 1

        # Evaluation configuration
        if 'evaluation' in data:
            evaluation = data['evaluation']

            if 'evaluators' in evaluation:
                evaluators = evaluation['evaluators']
                for evaluator in evaluators:
                    metadata['evaluators_used'][evaluator] += 1

                eval_combo = ', '.join(sorted(evaluators))
                metadata['evaluator_combinations'][eval_combo] += 1

            if 'exact_match' in evaluation and 'case_sensitive' in evaluation['exact_match']:
                case_val = evaluation['exact_match']['case_sensitive']
                if case_val is True:
                    metadata['case_sensitive_configs']['true'] += 1
                elif case_val is False:
                    metadata['case_sensitive_configs']['false'] += 1
            else:
                metadata['case_sensitive_configs']['not_specified'] += 1

            if 'llm_judge' in evaluation and 'model' in evaluation['llm_judge']:
                metadata['llm_judge_models'][evaluation['llm_judge']['model']] += 1

        # Questions and answers
        qa_data = extract_questions_answers(data)
        q_count = len(qa_data['questions'])
        a_count = len(qa_data['answers'])

        metadata['question_count_per_config'].append(q_count)
        metadata['answer_count_per_config'].append(a_count)
        metadata['total_questions'] += q_count
        metadata['total_answers'] += a_count

    # Convert defaultdicts to regular dicts
    metadata['models_used'] = dict(metadata['models_used'])
    metadata['evaluators_used'] = dict(metadata['evaluators_used'])
    metadata['evaluator_combinations'] = dict(metadata['evaluator_combinations'])
    metadata['llm_judge_models'] = dict(metadata['llm_judge_models'])
    metadata['agent_names'] = dict(metadata['agent_names'])
    metadata['max_turns'] = dict(metadata['max_turns'])
    metadata['tools_usage'] = dict(metadata['tools_usage'])
    metadata['repositories'] = dict(metadata['repositories'])
    metadata['repository_branches'] = dict(metadata['repository_branches'])
    metadata['teams'] = dict(metadata['teams'])
    metadata['log_levels'] = dict(metadata['log_levels'])
    metadata['docker_ports'] = dict(metadata['docker_ports'])

    # Calculate averages
    if metadata['total_configs'] > 0:
        metadata['avg_questions_per_config'] = round(metadata['total_questions'] / metadata['total_configs'], 2)
        metadata['avg_answers_per_config'] = round(metadata['total_answers'] / metadata['total_configs'], 2)
        if metadata['team_members_count']:
            metadata['avg_team_members'] = round(sum(metadata['team_members_count']) / len(metadata['team_members_count']), 2)
        else:
            metadata['avg_team_members'] = 0
    else:
        metadata['avg_questions_per_config'] = 0
        metadata['avg_answers_per_config'] = 0
        metadata['avg_team_members'] = 0

    return metadata

def main():
    config_dir = './test_configs'

    print("Loading YAML configurations from test_configs directory...")
    configs = load_yaml_files(config_dir)
    print(f"Found {len(configs)} configurations\n")

    if len(configs) == 0:
        print("No YAML files found in test_configs directory!")
        return

    all_qa_data = []

    for config in configs:
        qa_data = extract_questions_answers(config['content'])

        config_qa = {
            'config_name': config['name'],
            'questions': qa_data['questions'],
            'expected_answers': qa_data['answers'],
            'question_count': len(qa_data['questions']),
            'answer_count': len(qa_data['answers'])
        }

        all_qa_data.append(config_qa)

    # Sort by config name for consistency
    all_qa_data.sort(key=lambda x: x['config_name'])

    # Save JSON version
    with open('questions_answers.json', 'w', encoding='utf-8') as f:
        json.dump(all_qa_data, f, indent=2, ensure_ascii=False)

    # Save CSV version
    save_qa_to_csv(all_qa_data, 'questions_answers.csv')

    print("Extracting quantitative metadata...")
    metadata = extract_quantitative_data(configs)

    with open('quantitative_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print("\n" + "="*70)
    print("EXTRACTION COMPLETE")
    print("="*70)
    print(f"\nTotal configurations processed: {metadata['total_configs']}")
    print(f"Total questions extracted: {metadata['total_questions']}")
    print(f"Total answers extracted: {metadata['total_answers']}")
    print(f"Average questions per config: {metadata['avg_questions_per_config']}")
    print(f"Average answers per config: {metadata['avg_answers_per_config']}")

    print("\n" + "-"*70)
    print("Agent Models used:")
    for model, count in sorted(metadata['models_used'].items(), key=lambda x: -x[1]):
        print(f"  {model}: {count} times")

    print("\n" + "-"*70)
    print("Evaluators used:")
    for evaluator, count in sorted(metadata['evaluators_used'].items(), key=lambda x: -x[1]):
        print(f"  {evaluator}: {count} times")

    print("\n" + "-"*70)
    print("LLM Judge models:")
    for model, count in sorted(metadata['llm_judge_models'].items(), key=lambda x: -x[1]):
        print(f"  {model}: {count} times")

    print("\n" + "-"*70)
    print("Tools usage:")
    for tool, count in sorted(metadata['tools_usage'].items(), key=lambda x: -x[1]):
        print(f"  {tool}: {count} times")

    print("\n" + "-"*70)
    print("Repository branches:")
    for branch, count in sorted(metadata['repository_branches'].items(), key=lambda x: -x[1]):
        print(f"  {branch}: {count} repos")

    print("\n" + "-"*70)
    print("Log levels:")
    for level, count in sorted(metadata['log_levels'].items(), key=lambda x: -x[1]):
        print(f"  {level}: {count} configs")

    print("\n" + "-"*70)
    print(f"Configs with milestones: {metadata['configs_with_milestones']}")
    print(f"Total milestones across all configs: {metadata['total_milestones']}")

    print("\n" + "-"*70)
    print(f"\nFiles saved:")
    print("  - questions_answers.json")
    print("  - questions_answers.csv")
    print("  - quantitative_metadata.json")

if __name__ == "__main__":
    main()