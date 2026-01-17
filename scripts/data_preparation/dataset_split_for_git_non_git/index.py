"""
Verify that questions in config files match those in split.json.
If mismatches are found, save corrected configs to output directory.
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any
import sys


class QuestionVerifier:
    def __init__(self, config_dir: str, split_json_path: str, output_dir: str, git_output_dir: str):
        self.config_dir = Path(config_dir)
        self.split_json_path = Path(split_json_path)
        self.output_dir = Path(output_dir)
        self.git_output_dir = Path(git_output_dir)
        self.mismatches = []

    def load_split_json(self) -> Dict[str, Any]:
        """Load and return the split.json data."""
        with open(self.split_json_path, 'r') as f:
            return json.load(f)

    def load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load and return a YAML config file."""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def extract_questions_from_config(self, config: Dict[str, Any]) -> List[str]:
        """Extract questions from config benchmark section."""
        questions = []
        benchmark = config.get('benchmark', {})

        # Handle both single question and multiple questions format
        if 'question' in benchmark:
            questions.append(benchmark['question'])

        if 'questions' in benchmark:
            questions.extend(benchmark['questions'])

        return questions

    def extract_questions_from_split(self, config_name: str, split_data: Dict[str, Any]) -> List[str]:
        """Extract questions for a specific config from split.json."""
        for config_entry in split_data.get('configs', []):
            if config_entry.get('config_name') == config_name:
                questions = []
                for q_dict in config_entry.get('questions', []):
                    # Get the actual question text from each question dict
                    for key, value in q_dict.items():
                        if key.startswith('question_') and isinstance(value, str):
                            questions.append(value)
                return questions
        return []

    def normalize_question(self, question: str) -> str:
        """Normalize question text for comparison."""
        return ' '.join(question.strip().split())

    def verify_config(self, config_name: str, split_data: Dict[str, Any]) -> bool:
        """Verify questions in a config match split.json."""
        config_path = self.config_dir / config_name

        if not config_path.exists():
            print(f"WARNING: Config file not found: {config_name}")
            return False

        config = self.load_config(config_path)
        config_questions = self.extract_questions_from_config(config)
        split_questions = self.extract_questions_from_split(config_name, split_data)

        # Normalize questions for comparison
        config_questions_norm = [self.normalize_question(q) for q in config_questions]
        split_questions_norm = [self.normalize_question(q) for q in split_questions]

        if config_questions_norm != split_questions_norm:
            self.mismatches.append({
                'config_name': config_name,
                'config_questions': config_questions,
                'split_questions': split_questions,
                'config': config
            })
            return False

        return True

    def save_corrected_config(self, config_name: str, config: Dict[str, Any], correct_questions: List[str]):
        """Save corrected config with proper questions."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Update config with correct questions
        if 'benchmark' not in config:
            config['benchmark'] = {}

        # Clear old question formats
        if 'question' in config['benchmark']:
            del config['benchmark']['question']

        # Set correct questions
        config['benchmark']['questions'] = correct_questions

        # Save to output directory
        output_path = self.output_dir / config_name
        with open(output_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"Saved corrected config: {output_path}")

    def save_non_git_config(self, config_name: str, config: Dict[str, Any], questions: List[str]):
        """Save config that doesn't require git with proper questions."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Update config with correct questions
        if 'benchmark' not in config:
            config['benchmark'] = {}

        # Clear old question formats
        if 'question' in config['benchmark']:
            del config['benchmark']['question']

        # Set correct questions
        config['benchmark']['questions'] = questions

        # Save to output directory
        output_path = self.output_dir / config_name
        with open(output_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def save_git_config(self, config_name: str, config: Dict[str, Any], questions: List[str]):
        """Save config that requires git with proper questions."""
        self.git_output_dir.mkdir(parents=True, exist_ok=True)

        # Update config with correct questions
        if 'benchmark' not in config:
            config['benchmark'] = {}

        # Clear old question formats
        if 'question' in config['benchmark']:
            del config['benchmark']['question']

        # Set correct questions
        config['benchmark']['questions'] = questions

        # Save to git output directory
        output_path = self.git_output_dir / config_name
        with open(output_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def extract_non_git_configs(self, split_data: Dict[str, Any]) -> int:
        """Extract and save configs that have only Slack/Linear questions."""
        print("\nExtracting configs with Slack/Linear-only questions...")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        non_git_count = 0

        for config_entry in split_data.get('configs', []):
            config_name = config_entry.get('config_name')
            questions_list = config_entry.get('questions', [])

            # Check if all questions are Slack/Linear only (no git required)
            all_slack_linear = all(
                not q.get('has_git_required_to_answer', False)
                for q in questions_list
            )

            if all_slack_linear and questions_list:
                # Load the original config
                config_path = self.config_dir / config_name
                if not config_path.exists():
                    print(f"WARNING: Config file not found: {config_name}")
                    continue

                config = self.load_config(config_path)

                # Extract just the question text
                questions_text = []
                for q_dict in questions_list:
                    for key, value in q_dict.items():
                        if key.startswith('question_') and isinstance(value, str):
                            questions_text.append(value)

                # Save config with only Slack/Linear questions
                self.save_non_git_config(config_name, config, questions_text)
                non_git_count += 1
                print(f"✓ Saved non-git config: {config_name}")

        return non_git_count

    def extract_git_configs(self, split_data: Dict[str, Any]) -> int:
        """Extract and save configs that have at least one git-required question."""
        print("\nExtracting configs with git-required questions...")
        self.git_output_dir.mkdir(parents=True, exist_ok=True)

        git_count = 0

        for config_entry in split_data.get('configs', []):
            config_name = config_entry.get('config_name')
            questions_list = config_entry.get('questions', [])

            # Check if any question requires git
            has_git_question = any(
                q.get('has_git_required_to_answer', False)
                for q in questions_list
            )

            if has_git_question and questions_list:
                # Load the original config
                config_path = self.config_dir / config_name
                if not config_path.exists():
                    print(f"WARNING: Config file not found: {config_name}")
                    continue

                config = self.load_config(config_path)

                # Extract just the question text
                questions_text = []
                for q_dict in questions_list:
                    for key, value in q_dict.items():
                        if key.startswith('question_') and isinstance(value, str):
                            questions_text.append(value)

                # Save config with git-required questions
                self.save_git_config(config_name, config, questions_text)
                git_count += 1
                print(f"✓ Saved git config: {config_name}")

        return git_count

    def calculate_metrics(self, split_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate metrics from split.json data."""
        total_configs = len(split_data.get('configs', []))
        total_questions = 0
        questions_requiring_git = 0

        for config_entry in split_data.get('configs', []):
            questions = config_entry.get('questions', [])
            total_questions += len(questions)

            for question_dict in questions:
                # Check if any question requires git
                if question_dict.get('has_git_required_to_answer', False):
                    questions_requiring_git += 1

        questions_slack_linear_only = total_questions - questions_requiring_git
        percentage_slack_linear_only = round(
            (questions_slack_linear_only / total_questions * 100) if total_questions > 0 else 0)

        return {
            "total_configs": total_configs,
            "total_questions": total_questions,
            "questions_requiring_git": questions_requiring_git,
            "questions_slack_linear_only": questions_slack_linear_only,
            "percentage_slack_linear_only": percentage_slack_linear_only
        }

    def run_verification(self) -> bool:
        """Run verification on all configs in split.json."""
        print("Loading split.json...")
        split_data = self.load_split_json()

        total_configs = len(split_data.get('configs', []))
        print(f"Verifying {total_configs} configs...\n")

        verified_count = 0
        for config_entry in split_data.get('configs', []):
            config_name = config_entry.get('config_name')

            if self.verify_config(config_name, split_data):
                verified_count += 1
                print(f"✓ {config_name}: Questions match")
            else:
                print(f"✗ {config_name}: Questions DO NOT match")

        print(f"\n{'=' * 60}")
        print(f"Verification Summary:")
        print(f"Total configs: {total_configs}")
        print(f"Verified: {verified_count}")
        print(f"Mismatches: {len(self.mismatches)}")
        print(f"{'=' * 60}\n")

        if self.mismatches:
            print("Mismatches found:\n")
            for mismatch in self.mismatches:
                print(f"\nConfig: {mismatch['config_name']}")
                print(f"Config questions count: {len(mismatch['config_questions'])}")
                print(f"Split.json questions count: {len(mismatch['split_questions'])}")

                print("\nConfig questions:")
                for i, q in enumerate(mismatch['config_questions'], 1):
                    print(f"  {i}. {q[:100]}...")

                print("\nSplit.json questions:")
                for i, q in enumerate(mismatch['split_questions'], 1):
                    print(f"  {i}. {q[:100]}...")
                print("-" * 60)

            # Save corrected configs
            print("\nSaving corrected configs to output directory...")
            for mismatch in self.mismatches:
                self.save_corrected_config(
                    mismatch['config_name'],
                    mismatch['config'],
                    mismatch['split_questions']
                )

            success = False
        else:
            print("All questions are correctly mapped!")
            success = True

        # Extract and save non-git configs
        non_git_count = self.extract_non_git_configs(split_data)

        # Extract and save git configs
        git_count = self.extract_git_configs(split_data)

        # Calculate and display metrics
        print(f"\n{'=' * 60}")
        print("Dataset Metrics:")
        print(f"{'=' * 60}")
        metrics = self.calculate_metrics(split_data)
        print(json.dumps(metrics, indent=2))
        print(f"\n{'=' * 60}")
        print(f"Configs Output Summary:")
        print(f"{'=' * 60}")
        print(f"Non-Git configs (Slack/Linear only): {non_git_count}")
        print(f"  Saved to: {self.output_dir}")
        print(f"\nGit-related configs: {git_count}")
        print(f"  Saved to: {self.git_output_dir}")
        print(f"\nTotal configs processed: {non_git_count + git_count}")
        print(f"{'=' * 60}\n")

        return success


def main():
    # Configuration
    config_dir = "test_configs"
    split_json_path = "input/split.json"
    output_dir = "output/test_configs_without_git"
    git_output_dir = "output/test_configs_git"

    verifier = QuestionVerifier(config_dir, split_json_path, output_dir, git_output_dir)

    success = verifier.run_verification()

    if not success:
        print("\n⚠️  Verification failed. Check corrected configs in output directory.")
        sys.exit(1)
    else:
        print("\n✅ Verification passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()