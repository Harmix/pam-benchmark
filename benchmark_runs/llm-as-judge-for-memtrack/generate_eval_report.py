#!/usr/bin/env python3
"""
LLM Judge Evaluation Report Generator
Generates charts and detailed reports from evaluation results
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import numpy as np
from datetime import datetime


class ReportGenerator:
    """Generate visual reports from LLM judge evaluation results"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.results_data = {}

    def load_results(self, config_name: str = None) -> int:
        """Load results from all or specific config directories"""
        count = 0

        for config_dir in self.output_dir.iterdir():
            if not config_dir.is_dir() or not config_dir.name.startswith('config_'):
                continue

            if config_name and config_dir.name != config_name:
                continue

            results_file = config_dir / "llm_judge_results.json"
            if results_file.exists():
                with open(results_file, 'r') as f:
                    data = json.load(f)
                    self.results_data[config_dir.name] = data
                    count += 1

        return count

    def generate_accuracy_chart(self, save_path: Path):
        """Generate bar chart comparing accuracy across configs"""
        if not self.results_data:
            return

        configs = sorted(self.results_data.keys())
        accuracies = [self.results_data[c]['summary']['accuracy'] * 100 for c in configs]
        correct_counts = [self.results_data[c]['summary']['correct_count'] for c in configs]
        total_counts = [self.results_data[c]['summary']['total_questions'] for c in configs]

        fig, ax = plt.subplots(figsize=(12, 6))

        bars = ax.bar(range(len(configs)), accuracies, color='steelblue', edgecolor='black', linewidth=1.2)

        # Add value labels on bars
        for i, (bar, correct, total) in enumerate(zip(bars, correct_counts, total_counts)):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                   f'{correct}/{total}\n{height:.1f}%',
                   ha='center', va='bottom', fontsize=9, fontweight='bold')

        ax.set_xlabel('Configuration', fontsize=12, fontweight='bold')
        ax.set_ylabel('Accuracy (%)', fontsize=12, fontweight='bold')
        ax.set_title('LLM Judge Evaluation: Accuracy by Configuration', fontsize=14, fontweight='bold', pad=20)
        ax.set_xticks(range(len(configs)))
        ax.set_xticklabels(configs, rotation=45, ha='right')
        ax.set_ylim(0, 110)
        ax.grid(axis='y', alpha=0.3, linestyle='--')

        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved accuracy chart: {save_path}")

    def generate_metrics_comparison(self, save_path: Path):
        """Generate comparison chart for multiple metrics"""
        if not self.results_data:
            return

        configs = sorted(self.results_data.keys())
        metrics = {
            'Accuracy': [self.results_data[c]['summary']['accuracy'] * 100 for c in configs],
            'Avg Score': [self.results_data[c]['summary']['avg_score'] * 100 for c in configs],
            'Avg Confidence': [self.results_data[c]['summary']['avg_confidence'] * 100 for c in configs]
        }

        fig, ax = plt.subplots(figsize=(14, 7))

        x = np.arange(len(configs))
        width = 0.25

        colors = ['steelblue', 'coral', 'mediumseagreen']

        for i, (metric_name, values) in enumerate(metrics.items()):
            offset = (i - 1) * width
            bars = ax.bar(x + offset, values, width, label=metric_name,
                         color=colors[i], edgecolor='black', linewidth=0.8)

            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                       f'{height:.1f}%',
                       ha='center', va='bottom', fontsize=8)

        ax.set_xlabel('Configuration', fontsize=12, fontweight='bold')
        ax.set_ylabel('Score (%)', fontsize=12, fontweight='bold')
        ax.set_title('LLM Judge Evaluation: Metrics Comparison', fontsize=14, fontweight='bold', pad=20)
        ax.set_xticks(x)
        ax.set_xticklabels(configs, rotation=45, ha='right')
        ax.set_ylim(0, 110)
        ax.legend(loc='upper right', fontsize=10)
        ax.grid(axis='y', alpha=0.3, linestyle='--')

        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved metrics comparison: {save_path}")

    def generate_question_heatmap(self, save_path: Path):
        """Generate heatmap showing which questions were answered correctly"""
        if not self.results_data:
            return

        configs = sorted(self.results_data.keys())

        # Find max questions across all configs
        max_questions = max(len(self.results_data[c]['results']) for c in configs)

        # Build correctness matrix with mask for missing questions
        matrix = np.full((len(configs), max_questions), np.nan)
        for i, config in enumerate(configs):
            results = self.results_data[config]['results']
            for q_num_str, result in results.items():
                q_num = int(q_num_str) - 1
                matrix[i, q_num] = 1 if result['is_correct'] else 0

        # Create masked array where NaN values will be white
        masked_matrix = np.ma.masked_invalid(matrix)

        fig, ax = plt.subplots(figsize=(max(12, max_questions * 0.6), max(6, len(configs) * 0.4)))

        # Create heatmap with white for masked (non-existent) values
        cmap = plt.cm.RdYlGn
        cmap.set_bad(color='white')

        im = ax.imshow(masked_matrix, cmap=cmap, aspect='auto', vmin=0, vmax=1)

        # Set ticks
        ax.set_xticks(np.arange(max_questions))
        ax.set_yticks(np.arange(len(configs)))
        ax.set_xticklabels(np.arange(1, max_questions + 1))
        ax.set_yticklabels(configs)

        # Add grid
        ax.set_xticks(np.arange(max_questions + 1) - 0.5, minor=True)
        ax.set_yticks(np.arange(len(configs) + 1) - 0.5, minor=True)
        ax.grid(which="minor", color="gray", linestyle='-', linewidth=0.5)

        # Labels
        ax.set_xlabel('Question Number', fontsize=12, fontweight='bold')
        ax.set_ylabel('Configuration', fontsize=12, fontweight='bold')
        ax.set_title('Question Correctness Heatmap (Green=Correct, Red=Incorrect, White=N/A)',
                     fontsize=14, fontweight='bold', pad=20)

        # Add text annotations
        for i in range(len(configs)):
            for j in range(max_questions):
                if not np.isnan(matrix[i, j]):
                    if matrix[i, j] == 1:
                        text = ax.text(j, i, '✓', ha="center", va="center",
                                       color="darkgreen", fontsize=12, fontweight='bold')
                    else:
                        text = ax.text(j, i, '✗', ha="center", va="center",
                                       color="darkred", fontsize=12, fontweight='bold')

        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved question heatmap: {save_path}")

    def generate_score_distribution(self, save_path: Path):
        """Generate score distribution histogram for each config"""
        if not self.results_data:
            return

        configs = sorted(self.results_data.keys())
        n_configs = len(configs)

        # Calculate grid layout
        n_cols = min(3, n_configs)
        n_rows = (n_configs + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 4 * n_rows))
        if n_configs == 1:
            axes = np.array([axes])
        axes = axes.flatten()

        for idx, config in enumerate(configs):
            ax = axes[idx]
            results = self.results_data[config]['results']
            scores = [result['score'] for result in results.values()]

            ax.hist(scores, bins=20, range=(0, 1), color='steelblue',
                   edgecolor='black', linewidth=0.8, alpha=0.7)

            ax.set_xlabel('Score', fontsize=10, fontweight='bold')
            ax.set_ylabel('Frequency', fontsize=10, fontweight='bold')
            ax.set_title(f'{config}\nMean: {np.mean(scores):.2f}, Std: {np.std(scores):.2f}',
                        fontsize=10, fontweight='bold')
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_xlim(0, 1)

        # Hide unused subplots
        for idx in range(n_configs, len(axes)):
            axes[idx].set_visible(False)

        fig.suptitle('Score Distribution by Configuration', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved score distribution: {save_path}")

    def generate_confidence_analysis(self, save_path: Path):
        """Generate confidence vs correctness scatter plot"""
        if not self.results_data:
            return

        configs = sorted(self.results_data.keys())

        fig, ax = plt.subplots(figsize=(12, 8))

        colors = plt.cm.tab10(np.linspace(0, 1, len(configs)))

        for idx, config in enumerate(configs):
            results = self.results_data[config]['results']

            correct_conf = [r['confidence'] for r in results.values() if r['is_correct']]
            incorrect_conf = [r['confidence'] for r in results.values() if not r['is_correct']]

            correct_scores = [r['score'] for r in results.values() if r['is_correct']]
            incorrect_scores = [r['score'] for r in results.values() if not r['is_correct']]

            if correct_conf:
                ax.scatter(correct_conf, correct_scores, c=[colors[idx]],
                          marker='o', s=100, alpha=0.6, edgecolors='black', linewidth=1,
                          label=f'{config} (Correct)')

            if incorrect_conf:
                ax.scatter(incorrect_conf, incorrect_scores, c=[colors[idx]],
                          marker='x', s=100, alpha=0.6, linewidth=2,
                          label=f'{config} (Incorrect)')

        ax.set_xlabel('Confidence', fontsize=12, fontweight='bold')
        ax.set_ylabel('Score', fontsize=12, fontweight='bold')
        ax.set_title('Confidence vs Score (○=Correct, ×=Incorrect)',
                    fontsize=14, fontweight='bold', pad=20)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.05, 1.05)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        ax.grid(alpha=0.3, linestyle='--')

        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved confidence analysis: {save_path}")

    def generate_detailed_html_report(self, save_path: Path):
        """Generate detailed HTML report with all results"""
        configs = sorted(self.results_data.keys())

        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Judge Evaluation Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 10px;
        }
        .summary {
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        .summary-item {
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
        }
        .summary-item .value {
            font-size: 28px;
            font-weight: bold;
            color: #2c3e50;
        }
        .summary-item .label {
            font-size: 14px;
            color: #7f8c8d;
            margin-top: 5px;
        }
        .config-section {
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .question {
            border-left: 3px solid #95a5a6;
            padding: 15px;
            margin: 15px 0;
            background-color: #f9f9f9;
            border-radius: 4px;
        }
        .question.correct {
            border-left-color: #27ae60;
            background-color: #eafaf1;
        }
        .question.incorrect {
            border-left-color: #e74c3c;
            background-color: #fadbd8;
        }
        .question-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .question-number {
            font-weight: bold;
            font-size: 16px;
        }
        .status {
            padding: 5px 12px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        }
        .status.correct {
            background-color: #27ae60;
            color: white;
        }
        .status.incorrect {
            background-color: #e74c3c;
            color: white;
        }
        .question-content {
            margin: 10px 0;
        }
        .label {
            font-weight: bold;
            color: #34495e;
            margin-right: 5px;
        }
        .metrics {
            display: flex;
            gap: 20px;
            margin-top: 10px;
            font-size: 14px;
        }
        .metric {
            background-color: white;
            padding: 8px 15px;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        .reasoning {
            margin-top: 10px;
            padding: 10px;
            background-color: white;
            border-radius: 4px;
            font-style: italic;
            color: #555;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            background-color: white;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .timestamp {
            color: #7f8c8d;
            font-size: 14px;
            text-align: right;
            margin-top: 20px;
        }
        .chart-container {
            text-align: center;
            margin: 20px 0;
        }
        .chart-container img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
    </style>
</head>
<body>
"""

        # Header
        html += f"""
    <h1>🎯 LLM Judge Evaluation Report</h1>
    <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
"""

        # Overall summary
        total_questions = sum(len(self.results_data[c]['results']) for c in configs)
        total_correct = sum(self.results_data[c]['summary']['correct_count'] for c in configs)
        overall_accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0

        html += f"""
    <div class="summary">
        <h2>📊 Overall Summary</h2>
        <div class="summary-grid">
            <div class="summary-item">
                <div class="value">{len(configs)}</div>
                <div class="label">Configurations</div>
            </div>
            <div class="summary-item">
                <div class="value">{total_questions}</div>
                <div class="label">Total Questions</div>
            </div>
            <div class="summary-item">
                <div class="value">{total_correct}</div>
                <div class="label">Correct Answers</div>
            </div>
            <div class="summary-item">
                <div class="value">{overall_accuracy:.1f}%</div>
                <div class="label">Overall Accuracy</div>
            </div>
        </div>

        <h3>Configuration Comparison</h3>
        <table>
            <thead>
                <tr>
                    <th>Configuration</th>
                    <th>Model</th>
                    <th>Questions</th>
                    <th>Correct</th>
                    <th>Accuracy</th>
                    <th>Avg Score</th>
                    <th>Avg Confidence</th>
                </tr>
            </thead>
            <tbody>
"""

        for config in configs:
            data = self.results_data[config]
            summary = data['summary']
            html += f"""
                <tr>
                    <td><strong>{config}</strong></td>
                    <td>{data.get('model', 'N/A')}</td>
                    <td>{summary['total_questions']}</td>
                    <td>{summary['correct_count']}</td>
                    <td>{summary['accuracy'] * 100:.1f}%</td>
                    <td>{summary['avg_score']:.2f}</td>
                    <td>{summary['avg_confidence']:.2f}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
    </div>
"""

        # Detailed results for each config
        for config in configs:
            data = self.results_data[config]
            summary = data['summary']

            html += f"""
    <div class="config-section">
        <h2>⚙️ {config}</h2>
        <p><strong>Config File:</strong> {data.get('config_yaml', 'N/A')}</p>
        <p><strong>Model:</strong> {data.get('model', 'N/A')}</p>
        <p><strong>Accuracy:</strong> {summary['correct_count']}/{summary['total_questions']} ({summary['accuracy'] * 100:.1f}%)</p>
"""

            # Questions
            results = data['results']
            questions = data['questions']
            expected_answers = data['expected_answers']

            for q_num_str in sorted(results.keys(), key=int):
                q_num = int(q_num_str)
                result = results[q_num_str]
                question = questions[q_num - 1]
                expected = expected_answers[q_num - 1]

                is_correct = result['is_correct']
                status_class = 'correct' if is_correct else 'incorrect'
                status_text = '✓ CORRECT' if is_correct else '✗ INCORRECT'

                html += f"""
        <div class="question {status_class}">
            <div class="question-header">
                <span class="question-number">Question {q_num}</span>
                <span class="status {status_class}">{status_text}</span>
            </div>
            <div class="question-content">
                <div><span class="label">Q:</span> {question}</div>
                <div><span class="label">Expected:</span> {expected}</div>
                <div><span class="label">Agent Answer:</span> {result.get('agent_answer', 'N/A')}</div>
            </div>
            <div class="metrics">
                <div class="metric">Score: {result['score']:.2f}</div>
                <div class="metric">Confidence: {result['confidence']:.2f}</div>
            </div>
            <div class="reasoning">
                <strong>Reasoning:</strong> {result.get('reasoning', 'N/A')}
            </div>
        </div>
"""

            html += """
    </div>
"""

        html += """
</body>
</html>
"""

        with open(save_path, 'w') as f:
            f.write(html)

        print(f"✓ Saved HTML report: {save_path}")

    def generate_all_reports(self, report_dir: Path):
        """Generate all reports and charts"""
        report_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nGenerating reports in: {report_dir}")
        print("=" * 80)

        # Generate charts
        self.generate_accuracy_chart(report_dir / "accuracy_chart.png")
        self.generate_metrics_comparison(report_dir / "metrics_comparison.png")
        self.generate_question_heatmap(report_dir / "question_heatmap.png")
        self.generate_score_distribution(report_dir / "score_distribution.png")
        self.generate_confidence_analysis(report_dir / "confidence_analysis.png")

        # Generate HTML report
        self.generate_detailed_html_report(report_dir / "evaluation_report.html")

        print("=" * 80)
        print(f"✓ All reports generated successfully!")


def main():
    parser = argparse.ArgumentParser(
        description="Generate charts and reports from LLM judge evaluation results"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./outputs",
        help="Path to the output directory containing config folders with results"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Specific config to generate report for (default: all configs)"
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Directory to save reports (default: outputs/evaluation_reports_TIMESTAMP)"
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        return 1

    # Create report generator
    generator = ReportGenerator(output_dir)

    # Load results
    print("Loading evaluation results...")
    count = generator.load_results(args.config)

    if count == 0:
        print("No evaluation results found!")
        print("Make sure you've run the evaluation pipeline first.")
        return 1

    print(f"✓ Loaded results from {count} configuration(s)")

    # Determine report directory
    if args.report_dir:
        report_dir = Path(args.report_dir)
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_dir = output_dir / f"evaluation_reports_{timestamp}"

    # Generate all reports
    generator.generate_all_reports(report_dir)

    print(f"\n{'=' * 80}")
    print(f"📊 Open the HTML report to view all results:")
    print(f"   {report_dir / 'evaluation_report.html'}")
    print(f"{'=' * 80}")

    return 0


if __name__ == "__main__":
    exit(main())