"""
Generate HTML reports from MongoDB LongMemEval evaluation results.

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
    <title>LongMemEval Report - {experiment_name}</title>
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

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 2rem;
        }}

        .container {{ max-width: 1200px; margin: 0 auto; }}

        .header {{
            background: linear-gradient(135deg, #7c3aed, #4f46e5);
            color: white;
            padding: 2rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}

        .header h1 {{ font-size: 1.875rem; font-weight: 700; margin-bottom: 0.5rem; }}

        .header-meta {{
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
            margin-top: 1rem;
            font-size: 0.95rem;
            opacity: 0.95;
        }}

        .header-meta-item {{ display: flex; align-items: center; gap: 0.5rem; }}
        .header-meta-label {{ font-weight: 600; }}

        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .summary-card {{
            background: var(--card-bg);
            padding: 1.5rem;
            border-radius: 10px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}

        .summary-card-value {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary-color);
            white-space: nowrap;
            line-height: 2.5rem;
            min-height: 2.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .summary-card-value.fraction {{ font-size: 1.6rem; }}
        .summary-card-value.success {{ color: var(--success-color); }}
        .summary-card-value.warning {{ color: var(--warning-color); }}
        .summary-card-value.error {{ color: var(--error-color); }}

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

        tr:hover {{ background: var(--bg-color); }}

        .accuracy-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .accuracy-high {{ background: #dcfce7; color: #166534; }}
        .accuracy-medium {{ background: #fef9c3; color: #854d0e; }}
        .accuracy-low {{ background: #fee2e2; color: #991b1b; }}

        .category-badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
            background: #e0e7ff;
            color: #3730a3;
        }}

        .status-badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
        }}

        .status-correct {{ background: #dcfce7; color: #166534; }}
        .status-incorrect {{ background: #fee2e2; color: #991b1b; }}

        .responses-section {{ margin-top: 2rem; }}

        .filter-bar {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }}

        .filter-bar-label {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-right: 0.25rem;
        }}

        .filter-btn {{
            padding: 0.35rem 0.9rem;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: var(--card-bg);
            color: var(--text-muted);
            font-size: 0.8rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .filter-btn:hover {{ border-color: var(--primary-color); color: var(--primary-color); }}

        .filter-btn.active {{
            background: var(--primary-color);
            color: white;
            border-color: var(--primary-color);
        }}

        .filter-count {{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-left: 0.5rem;
        }}

        .answer-card {{
            border-radius: 10px;
            padding: 1.25rem;
            margin-bottom: 1rem;
        }}

        .answer-card.incorrect {{
            background: #fef2f2;
            border: 1px solid #fecaca;
        }}

        .answer-card.correct {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
        }}

        .answer-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}

        .answer-card-title {{ font-weight: 600; }}
        .answer-card-title.incorrect {{ color: var(--error-color); }}
        .answer-card-title.correct {{ color: var(--success-color); }}

        .answer-card-meta {{
            display: flex;
            gap: 1rem;
            font-size: 0.875rem;
            color: var(--text-muted);
        }}

        .answer-field {{ margin-bottom: 0.75rem; }}

        .answer-field-label {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }}

        .answer-field-value {{
            background: white;
            padding: 0.75rem;
            border-radius: 6px;
            font-size: 0.9rem;
        }}

        .answer-card.incorrect .answer-field-value {{ border: 1px solid #fecaca; }}
        .answer-card.correct .answer-field-value {{ border: 1px solid #bbf7d0; }}

        .explanation-box {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-radius: 6px;
            padding: 0.75rem;
            font-size: 0.85rem;
            color: #92400e;
        }}

        .no-results {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 1.1rem;
        }}

        .footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>LongMemEval Evaluation Report</h1>
            <div class="header-meta">
                <div class="header-meta-item">
                    <span class="header-meta-label">Experiment:</span>
                    <span>{experiment_name}</span>
                </div>
                <div class="header-meta-item">
                    <span class="header-meta-label">Model:</span>
                    <span>{model_name}</span>
                </div>
                <div class="header-meta-item">
                    <span class="header-meta-label">Eval Model:</span>
                    <span>{eval_model}</span>
                </div>
                <div class="header-meta-item">
                    <span class="header-meta-label">Generated:</span>
                    <span>{report_generated}</span>
                </div>
            </div>
        </div>

        <div class="summary-cards">
            <div class="summary-card">
                <div class="summary-card-value {accuracy_class}">{overall_accuracy}%</div>
                <div class="summary-card-label">Overall Accuracy</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value fraction">{total_correct}/{total_questions}</div>
                <div class="summary-card-label">Correct Answers</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value">{total_questions}</div>
                <div class="summary-card-label">Total Questions</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value">{execution_time}</div>
                <div class="summary-card-label">Total Time</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">Accuracy by Question Category</h2>
            <table>
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Questions</th>
                        <th>Correct</th>
                        <th>Incorrect</th>
                        <th>Accuracy</th>
                        <th>Total Duration</th>
                        <th>Avg Duration / Question</th>
                    </tr>
                </thead>
                <tbody>
                    {category_rows}
                </tbody>
            </table>
        </div>

        <div class="section responses-section" id="responses-section">
            <h2 class="section-title">All Responses ({total_all_responses})</h2>
            <div class="filter-bar">
                <span class="filter-bar-label">Status:</span>
                <button class="filter-btn active" data-group="status" data-filter="all" onclick="setFilter('status','all')">All ({total_all_responses})</button>
                <button class="filter-btn" data-group="status" data-filter="correct" onclick="setFilter('status','correct')">Correct ({total_correct})</button>
                <button class="filter-btn" data-group="status" data-filter="incorrect" onclick="setFilter('status','incorrect')">Incorrect ({total_incorrect})</button>
            </div>
            <div class="filter-bar">
                <span class="filter-bar-label">Category:</span>
                <button class="filter-btn active" data-group="category" data-filter="all" onclick="setFilter('category','all')">All</button>
                {filter_buttons}
                <span class="filter-count" id="filter-count"></span>
            </div>
            {responses_html}
        </div>

        <div class="footer">
            Generated by LongMemEval Benchmark Report Generator<br>
            <a href="https://github.com/xiaowu0162/LongMemEval" target="_blank">
                LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory
            </a>
        </div>
    </div>
    <script>
    var activeFilters = {{ status: 'all', category: 'all' }};

    function setFilter(group, value) {{
        activeFilters[group] = value;
        document.querySelectorAll('.filter-btn[data-group="' + group + '"]').forEach(function(btn) {{
            btn.classList.remove('active');
        }});
        document.querySelector('.filter-btn[data-group="' + group + '"][data-filter="' + value + '"]').classList.add('active');
        applyFilters();
    }}

    function applyFilters() {{
        var cards = document.querySelectorAll('.answer-card');
        var shown = 0;
        cards.forEach(function(card) {{
            var statusMatch = (activeFilters.status === 'all' || card.getAttribute('data-status') === activeFilters.status);
            var catMatch = (activeFilters.category === 'all' || card.getAttribute('data-category') === activeFilters.category);
            if (statusMatch && catMatch) {{
                card.style.display = '';
                shown++;
            }} else {{
                card.style.display = 'none';
            }}
        }});
        var countEl = document.getElementById('filter-count');
        if (activeFilters.status === 'all' && activeFilters.category === 'all') {{
            countEl.textContent = '';
        }} else {{
            countEl.textContent = 'Showing ' + shown + ' of ' + cards.length;
        }}
    }}
    </script>
</body>
</html>
"""


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def connect_to_mongodb(connection_string: str) -> Optional[MongoClient]:
    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None


def fetch_experiment_results(client: MongoClient, db_name: str, experiment_name: str) -> List[Dict]:
    db = client[db_name]
    collection = db["longmemeval_results"]
    return list(collection.find(
        {"experiment_name": experiment_name}
    ).sort("timestamp", 1))


# ============================================================================
# REPORT GENERATION HELPERS
# ============================================================================

CATEGORY_DISPLAY_NAMES = {
    'single-session-user': 'Single-Session (User)',
    'single-session-assistant': 'Single-Session (Assistant)',
    'single-session-preference': 'Single-Session (Preference)',
    'multi-session': 'Multi-Session',
    'temporal-reasoning': 'Temporal Reasoning',
    'knowledge-update': 'Knowledge Update',
}

CATEGORY_ORDER = [
    'single-session-user',
    'single-session-assistant',
    'single-session-preference',
    'multi-session',
    'temporal-reasoning',
    'knowledge-update',
]


def get_accuracy_class(accuracy_pct: float) -> str:
    if accuracy_pct >= 70:
        return "accuracy-high"
    elif accuracy_pct >= 40:
        return "accuracy-medium"
    return "accuracy-low"


def get_summary_class(accuracy_pct: float) -> str:
    if accuracy_pct >= 70:
        return "success"
    elif accuracy_pct >= 40:
        return "warning"
    return "error"


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def format_timestamp(timestamp) -> str:
    if timestamp is None:
        return "N/A"
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            return timestamp
    if timestamp.tzinfo is not None:
        return timestamp.strftime("%Y-%m-%d %H:%M:%S %Z")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")


# ============================================================================
# HTML BUILDERS
# ============================================================================

def generate_category_rows(results: List[Dict]) -> str:
    """Generate table rows for the category breakdown table."""
    cat_map = {r['question_category']: r for r in results}
    rows = []

    for cat_key in CATEGORY_ORDER:
        rec = cat_map.get(cat_key)
        if not rec:
            continue

        display = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key)
        accuracy_pct = rec['accuracy'] * 100
        acc_class = get_accuracy_class(accuracy_pct)

        rows.append(f"""
        <tr>
            <td><strong>{display}</strong></td>
            <td>{rec['total_questions']}</td>
            <td>{rec['correct_count']}</td>
            <td>{rec['incorrect_count']}</td>
            <td><span class="accuracy-badge {acc_class}">{accuracy_pct:.1f}%</span></td>
            <td>{format_duration(rec.get('total_duration_sec'))}</td>
            <td>{format_duration(rec.get('avg_duration_sec'))}</td>
        </tr>""")

    total_q = sum(r.get('total_questions', 0) for r in results)
    total_c = sum(r.get('correct_count', 0) for r in results)
    total_i = sum(r.get('incorrect_count', 0) for r in results)
    total_dur = sum(r.get('total_duration_sec', 0) for r in results)
    overall_acc = (total_c / total_q * 100) if total_q else 0
    avg_dur = total_dur / total_q if total_q else 0

    rows.append(f"""
    <tr style="font-weight: 700; background: var(--bg-color);">
        <td>Total</td>
        <td>{total_q}</td>
        <td>{total_c}</td>
        <td>{total_i}</td>
        <td><span class="accuracy-badge {get_accuracy_class(overall_acc)}">{overall_acc:.1f}%</span></td>
        <td>{format_duration(total_dur)}</td>
        <td>{format_duration(avg_dur)}</td>
    </tr>""")

    return "\n".join(rows)


def generate_filter_buttons(results: List[Dict]) -> str:
    """Generate category filter buttons."""
    buttons = []
    for cat_key in CATEGORY_ORDER:
        rec = next((r for r in results if r['question_category'] == cat_key), None)
        if rec and rec.get('total_questions', 0) > 0:
            display = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key)
            buttons.append(
                f'<button class="filter-btn" data-group="category" data-filter="{cat_key}" '
                f'onclick="setFilter(\'category\',\'{cat_key}\')">'
                f'{display} ({rec["total_questions"]})</button>'
            )
    return "\n".join(buttons)


def _render_answer_card(item: Dict, cat_key: str, display: str, is_correct: bool) -> str:
    """Render a single answer card (correct or incorrect)."""
    status = "correct" if is_correct else "incorrect"
    status_label = "CORRECT" if is_correct else "INCORRECT"
    status_css = "status-correct" if is_correct else "status-incorrect"

    explanation_html = ""
    if not is_correct:
        explanation = item.get('judge_explanation', '')
        if explanation:
            explanation_html = f"""
    <div class="answer-field">
        <div class="answer-field-label">Judge Explanation</div>
        <div class="explanation-box">{explanation}</div>
    </div>"""

    gen_dur = item.get('generation_duration_sec')
    dur_str = f" | Gen: {gen_dur:.1f}s" if gen_dur else ""

    return f"""
<div class="answer-card {status}" data-status="{status}" data-category="{cat_key}">
    <div class="answer-card-header">
        <span class="answer-card-title {status}">{item.get('question_id', '?')}</span>
        <div class="answer-card-meta">
            <span class="status-badge {status_css}">{status_label}</span>
            <span class="category-badge">{display}</span>
            <span>{dur_str}</span>
        </div>
    </div>
    <div class="answer-field">
        <div class="answer-field-label">Question</div>
        <div class="answer-field-value">{item.get('question', 'N/A')}</div>
    </div>
    <div class="answer-field">
        <div class="answer-field-label">Expected Answer</div>
        <div class="answer-field-value">{item.get('expected_answer', 'N/A')}</div>
    </div>
    <div class="answer-field">
        <div class="answer-field-label">Model Answer</div>
        <div class="answer-field-value">{item.get('model_answer', 'N/A')}</div>
    </div>
    {explanation_html}
</div>"""


def generate_responses_html(results: List[Dict]) -> str:
    """Generate HTML cards for all answers (correct + incorrect) across categories."""
    cards = []

    for cat_key in CATEGORY_ORDER:
        rec = next((r for r in results if r['question_category'] == cat_key), None)
        if not rec:
            continue

        display = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key)

        for item in rec.get('incorrect_answers', []):
            cards.append(_render_answer_card(item, cat_key, display, is_correct=False))

        for item in rec.get('correct_answers', []):
            cards.append(_render_answer_card(item, cat_key, display, is_correct=True))

    if not cards:
        return '<div class="no-results">No responses to display.</div>'

    return "\n".join(cards)


# ============================================================================
# MAIN REPORT GENERATION
# ============================================================================

def generate_report(results: List[Dict], experiment_name: str, output_path: Path) -> bool:
    if not results:
        print(f"No results found for experiment: {experiment_name}")
        return False

    model_name = results[0].get('model', 'Unknown')
    eval_model = results[0].get('eval_model', 'Unknown')

    total_questions = sum(r.get('total_questions', 0) for r in results)
    total_correct = sum(r.get('correct_count', 0) for r in results)
    total_incorrect = sum(r.get('incorrect_count', 0) for r in results)
    total_exec_time = results[0].get('total_execution_time_sec', 0)
    overall_acc = (total_correct / total_questions * 100) if total_questions else 0

    category_rows = generate_category_rows(results)
    filter_buttons = generate_filter_buttons(results)
    responses_html = generate_responses_html(results)

    html = HTML_TEMPLATE.format(
        experiment_name=experiment_name,
        model_name=model_name,
        eval_model=eval_model,
        report_generated=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        overall_accuracy=f"{overall_acc:.1f}",
        accuracy_class=get_summary_class(overall_acc),
        total_correct=total_correct,
        total_questions=total_questions,
        total_incorrect=total_incorrect,
        total_all_responses=total_questions,
        execution_time=format_duration(total_exec_time),
        category_rows=category_rows,
        filter_buttons=filter_buttons,
        responses_html=responses_html,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Report generated: {output_path}")
    return True


# ============================================================================
# CLI
# ============================================================================

def load_environment():
    load_dotenv()

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
        description="Generate HTML report from MongoDB LongMemEval results"
    )
    parser.add_argument(
        "--experiment-name", type=str, default=None,
        help="Experiment name (or use EXPERIMENT_NAME env var)"
    )
    parser.add_argument(
        "--output-dir", type=str, default="tasks/longmemeval/reports",
        help="Output directory for reports"
    )
    parser.add_argument(
        "--db-name", type=str, default=None,
        help="MongoDB database name (or use DB_NAME env var)"
    )
    parser.add_argument(
        "--connection-string", type=str, default=None,
        help="MongoDB connection string (or use CONNECTION_STRING env var)"
    )

    args = parser.parse_args()
    load_environment()

    experiment_name = args.experiment_name or os.environ.get("EXPERIMENT_NAME")
    db_name = args.db_name or os.environ.get("DB_NAME")
    connection_string = args.connection_string or os.environ.get("CONNECTION_STRING")

    if not experiment_name:
        print("Error: --experiment-name or EXPERIMENT_NAME env var is required")
        return 1
    if not db_name or not connection_string:
        print("Error: DB_NAME and CONNECTION_STRING are required "
              "(via args or env vars / secrets.env)")
        return 1

    print(f"Connecting to MongoDB (database: {db_name})...")
    client = connect_to_mongodb(connection_string)
    if not client:
        return 1

    try:
        print(f"Fetching results for experiment: {experiment_name}")
        results = fetch_experiment_results(client, db_name, experiment_name)

        if not results:
            print(f"No results found for experiment: {experiment_name}")
            return 1

        print(f"Found {len(results)} category records")

        output_dir = Path(args.output_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"report_{experiment_name}_{timestamp}.html"

        success = generate_report(results, experiment_name, output_path)
        if success:
            print(f"\nReport successfully generated!")
            print(f"  Location: {output_path}")
            return 0
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    exit(main())
