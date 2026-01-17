"""
Generate HTML reports from MongoDB evaluation results.

Usage:
    python generate_report.py --experiment-name <experiment_name>
    
    Or with environment variables:
    EXPERIMENT_NAME=my_experiment python generate_report.py
"""

import os
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient


# ============================================================================
# HTML TEMPLATE
# ============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Evaluation Report - {experiment_name}</title>
    <style>
        :root {{
            --primary-color: #2563eb;
            --success-color: #16a34a;
            --error-color: #dc2626;
            --warning-color: #ca8a04;
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-color: #1e293b;
            --text-muted: #64748b;
            --border-color: #e2e8f0;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: linear-gradient(135deg, var(--primary-color), #1d4ed8);
            color: white;
            padding: 2rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        
        .header h1 {{
            font-size: 1.875rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}
        
        .header-meta {{
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
            margin-top: 1rem;
            font-size: 0.95rem;
            opacity: 0.95;
        }}
        
        .header-meta-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .header-meta-label {{
            font-weight: 600;
        }}
        
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        
        .summary-card {{
            background: var(--card-bg);
            padding: 1.5rem;
            border-radius: 10px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            text-align: center;
        }}
        
        .summary-card-value {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary-color);
        }}
        
        .summary-card-value.success {{
            color: var(--success-color);
        }}
        
        .summary-card-value.warning {{
            color: var(--warning-color);
        }}
        
        .summary-card-value.error {{
            color: var(--error-color);
        }}
        
        .summary-card-label {{
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }}
        
        .section {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }}
        
        .section-title {{
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 2px solid var(--border-color);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        
        th {{
            background: var(--bg-color);
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }}
        
        tr:hover {{
            background: var(--bg-color);
        }}
        
        .accuracy-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        
        .accuracy-high {{
            background: #dcfce7;
            color: #166534;
        }}
        
        .accuracy-medium {{
            background: #fef9c3;
            color: #854d0e;
        }}
        
        .accuracy-low {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        .incorrect-section {{
            margin-top: 2rem;
        }}
        
        .config-errors {{
            margin-bottom: 2rem;
        }}
        
        .config-errors-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--error-color);
            margin-bottom: 1rem;
            padding: 0.5rem 1rem;
            background: #fee2e2;
            border-radius: 8px;
            display: inline-block;
        }}
        
        .error-card {{
            background: #fef2f2;
            border: 1px solid #fecaca;
            border-radius: 10px;
            padding: 1.25rem;
            margin-bottom: 1rem;
        }}
        
        .error-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}
        
        .error-card-title {{
            font-weight: 600;
            color: var(--error-color);
        }}
        
        .error-card-score {{
            font-size: 0.875rem;
            color: var(--text-muted);
        }}
        
        .error-field {{
            margin-bottom: 0.75rem;
        }}
        
        .error-field-label {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }}
        
        .error-field-value {{
            background: white;
            padding: 0.75rem;
            border-radius: 6px;
            font-size: 0.9rem;
            border: 1px solid #fecaca;
        }}
        
        .reasoning-box {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-radius: 6px;
            padding: 0.75rem;
            font-size: 0.875rem;
            font-style: italic;
            color: #92400e;
        }}
        
        .footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
        }}
        
        .no-errors {{
            text-align: center;
            padding: 2rem;
            color: var(--success-color);
            font-size: 1.1rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Evaluation Report</h1>
            <div class="header-meta">
                <div class="header-meta-item">
                    <span class="header-meta-label">Experiment:</span>
                    <span>{experiment_name}</span>
                </div>
                <div class="header-meta-item">
                    <span class="header-meta-label">Dataset:</span>
                    <span>{dataset_name}</span>
                </div>
                <div class="header-meta-item">
                    <span class="header-meta-label">Agent:</span>
                    <span>{agent_name}</span>
                </div>
                <div class="header-meta-item">
                    <span class="header-meta-label">Generated:</span>
                    <span>{report_generated}</span>
                </div>
            </div>
        </div>
        
        <div class="summary-cards">
            <div class="summary-card">
                <div class="summary-card-value">{total_configs}</div>
                <div class="summary-card-label">Configs Evaluated</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value">{total_questions}</div>
                <div class="summary-card-label">Total Questions</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value {accuracy_class}">{overall_accuracy}%</div>
                <div class="summary-card-label">Overall Accuracy</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value">{total_correct}/{total_questions}</div>
                <div class="summary-card-label">Correct Answers</div>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">Results by Configuration</h2>
            <table>
                <thead>
                    <tr>
                        <th>Config</th>
                        <th>Questions</th>
                        <th>Correct</th>
                        <th>Accuracy</th>
                        <th>Avg Score</th>
                        <th>Execution Time</th>
                        <th>Executed At</th>
                    </tr>
                </thead>
                <tbody>
                    {config_rows}
                </tbody>
            </table>
        </div>
        
        <div class="section incorrect-section">
            <h2 class="section-title">Incorrect Responses</h2>
            {incorrect_responses_html}
        </div>
        
        <div class="footer">
            Generated by PAM Benchmark Report Generator
        </div>
    </div>
</body>
</html>
"""

CONFIG_ROW_TEMPLATE = """
<tr>
    <td><strong>{config_name}</strong></td>
    <td>{total_questions}</td>
    <td>{correct_count}</td>
    <td><span class="accuracy-badge {accuracy_class}">{accuracy}%</span></td>
    <td>{avg_score}</td>
    <td>{execution_time}</td>
    <td>{executed_at}</td>
</tr>
"""

CONFIG_ERRORS_TEMPLATE = """
<div class="config-errors">
    <div class="config-errors-title">❌ {config_name}</div>
    {error_cards}
</div>
"""

ERROR_CARD_TEMPLATE = """
<div class="error-card">
    <div class="error-card-header">
        <span class="error-card-title">Question {question_num}</span>
        <span class="error-card-score">Score: {score}</span>
    </div>
    <div class="error-field">
        <div class="error-field-label">Question</div>
        <div class="error-field-value">{question}</div>
    </div>
    <div class="error-field">
        <div class="error-field-label">Expected Answer</div>
        <div class="error-field-value">{expected_answer}</div>
    </div>
    <div class="error-field">
        <div class="error-field-label">Agent's Answer</div>
        <div class="error-field-value">{agent_answer}</div>
    </div>
    <div class="error-field">
        <div class="error-field-label">Judge Reasoning</div>
        <div class="reasoning-box">{reasoning}</div>
    </div>
</div>
"""


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def connect_to_mongodb(connection_string: str, db_name: str) -> Optional[MongoClient]:
    """Connect to MongoDB and return client"""
    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None


def fetch_experiment_results(client: MongoClient, db_name: str, experiment_name: str) -> List[Dict]:
    """Fetch all results for a given experiment name"""
    db = client[db_name]
    collection = db["evaluation_results"]
    
    results = list(collection.find(
        {"experiment_name": experiment_name}
    ).sort("timestamp", 1))
    
    return results


# ============================================================================
# REPORT GENERATION
# ============================================================================

def get_accuracy_class(accuracy: float) -> str:
    """Get CSS class based on accuracy value"""
    if accuracy >= 80:
        return "accuracy-high"
    elif accuracy >= 50:
        return "accuracy-medium"
    else:
        return "accuracy-low"


def get_summary_class(accuracy: float) -> str:
    """Get CSS class for summary card based on accuracy"""
    if accuracy >= 80:
        return "success"
    elif accuracy >= 50:
        return "warning"
    else:
        return "error"


def format_execution_time(seconds: Optional[float]) -> str:
    """Format execution time in a human-readable way"""
    if seconds is None:
        return "N/A"
    
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_timestamp(timestamp) -> str:
    """Format timestamp for display"""
    if timestamp is None:
        return "N/A"
    
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            return timestamp
    
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def generate_config_rows(results: List[Dict]) -> str:
    """Generate HTML table rows for each config"""
    rows = []
    
    for result in results:
        config_name = result.get("config_name", "Unknown")
        total_questions = result.get("total_questions", 0)
        correct_count = result.get("correct_count", 0)
        accuracy = result.get("accuracy", 0) * 100
        avg_score = result.get("avg_score", 0)
        execution_time = result.get("execution_time_seconds")
        timestamp = result.get("timestamp")
        
        row = CONFIG_ROW_TEMPLATE.format(
            config_name=config_name,
            total_questions=total_questions,
            correct_count=correct_count,
            accuracy=f"{accuracy:.1f}",
            accuracy_class=get_accuracy_class(accuracy),
            avg_score=f"{avg_score:.2f}",
            execution_time=format_execution_time(execution_time),
            executed_at=format_timestamp(timestamp)
        )
        rows.append(row)
    
    return "\n".join(rows)


def generate_incorrect_responses_html(results: List[Dict]) -> str:
    """Generate HTML for incorrect responses section"""
    html_parts = []
    has_errors = False
    
    for result in results:
        config_name = result.get("config_name", "Unknown")
        incorrect_responses = result.get("incorrect_responses", [])
        
        if not incorrect_responses:
            continue
        
        has_errors = True
        error_cards = []
        
        for resp in incorrect_responses:
            card = ERROR_CARD_TEMPLATE.format(
                question_num=resp.get("question_num", "?"),
                score=f"{resp.get('score', 0):.2f}",
                question=resp.get("question", "N/A"),
                expected_answer=resp.get("expected_answer", "N/A"),
                agent_answer=resp.get("agent_answer", "N/A") or "No answer provided",
                reasoning=resp.get("reasoning", "No reasoning provided")
            )
            error_cards.append(card)
        
        config_section = CONFIG_ERRORS_TEMPLATE.format(
            config_name=config_name,
            error_cards="\n".join(error_cards)
        )
        html_parts.append(config_section)
    
    if not has_errors:
        return '<div class="no-errors">✓ All responses were correct!</div>'
    
    return "\n".join(html_parts)


def generate_report(results: List[Dict], experiment_name: str, output_path: Path) -> bool:
    """Generate HTML report from MongoDB results"""
    if not results:
        print(f"No results found for experiment: {experiment_name}")
        return False
    
    # Extract common metadata (same for all results in experiment)
    dataset_name = results[0].get("dataset_name", "Unknown")
    agent_name = results[0].get("agent_name", "Unknown")
    
    # Calculate overall metrics
    total_configs = len(results)
    total_questions = sum(r.get("total_questions", 0) for r in results)
    total_correct = sum(r.get("correct_count", 0) for r in results)
    overall_accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0
    
    # Generate HTML sections
    config_rows = generate_config_rows(results)
    incorrect_responses_html = generate_incorrect_responses_html(results)
    
    # Generate final HTML
    html = HTML_TEMPLATE.format(
        experiment_name=experiment_name,
        dataset_name=dataset_name,
        agent_name=agent_name,
        report_generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_configs=total_configs,
        total_questions=total_questions,
        total_correct=total_correct,
        overall_accuracy=f"{overall_accuracy:.1f}",
        accuracy_class=get_summary_class(overall_accuracy),
        config_rows=config_rows,
        incorrect_responses_html=incorrect_responses_html
    )
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write report
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✓ Report generated: {output_path}")
    return True


# ============================================================================
# MAIN
# ============================================================================

def load_environment():
    """Load environment variables"""
    load_dotenv()
    
    # Also try to load from secrets.env
    secrets_paths = [
        Path("secrets.env"),
        Path("../../secrets.env"),
        Path("../../../secrets.env"),
    ]
    
    for secrets_path in secrets_paths:
        if secrets_path.exists():
            from dotenv import dotenv_values
            secrets = dotenv_values(secrets_path)
            for key, value in secrets.items():
                if value and key not in os.environ:
                    os.environ[key] = value
            break


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML report from MongoDB evaluation results"
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default=None,
        help="Experiment name to generate report for (or use EXPERIMENT_NAME env var)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="tasks/memtrack/reports",
        help="Output directory for reports (default: tasks/memtrack/reports)"
    )
    parser.add_argument(
        "--db-name",
        type=str,
        default=None,
        help="MongoDB database name (or use DB_NAME env var)"
    )
    parser.add_argument(
        "--connection-string",
        type=str,
        default=None,
        help="MongoDB connection string (or use CONNECTION_STRING env var)"
    )
    
    args = parser.parse_args()
    
    # Load environment variables
    load_environment()
    
    # Get configuration
    experiment_name = args.experiment_name or os.environ.get("EXPERIMENT_NAME")
    db_name = args.db_name or os.environ.get("DB_NAME")
    connection_string = args.connection_string or os.environ.get("CONNECTION_STRING")
    
    # Validate required parameters
    if not experiment_name:
        print("Error: Experiment name is required. Use --experiment-name or set EXPERIMENT_NAME env var")
        return 1
    
    if not db_name or not connection_string:
        print("Error: MongoDB configuration is required.")
        print("  Set DB_NAME and CONNECTION_STRING environment variables")
        print("  Or use --db-name and --connection-string arguments")
        return 1
    
    # Connect to MongoDB
    print(f"Connecting to MongoDB (database: {db_name})...")
    client = connect_to_mongodb(connection_string, db_name)
    if not client:
        return 1
    
    try:
        # Fetch results
        print(f"Fetching results for experiment: {experiment_name}")
        results = fetch_experiment_results(client, db_name, experiment_name)
        
        if not results:
            print(f"No results found for experiment: {experiment_name}")
            return 1
        
        print(f"Found {len(results)} config results")
        
        # Generate report
        output_dir = Path(args.output_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"report_{experiment_name}_{timestamp}.html"
        
        success = generate_report(results, experiment_name, output_path)
        
        if success:
            print(f"\n✓ Report successfully generated!")
            print(f"  Location: {output_path}")
            return 0
        else:
            return 1
            
    finally:
        client.close()


if __name__ == "__main__":
    exit(main())
