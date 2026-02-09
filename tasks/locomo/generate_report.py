"""
Generate HTML reports from MongoDB LoCoMo evaluation results.

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
    <title>LoCoMo Evaluation Report - {experiment_name}</title>
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
        
        .summary-card-value.fraction {{
            font-size: 1.6rem;
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
        
        .category-badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
            background: #e0e7ff;
            color: #3730a3;
        }}
        
        .incorrect-section {{
            margin-top: 2rem;
        }}
        
        .model-errors {{
            margin-bottom: 2rem;
        }}
        
        .model-errors-title {{
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
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        
        .error-card-title {{
            font-weight: 600;
            color: var(--error-color);
        }}
        
        .error-card-meta {{
            display: flex;
            gap: 1rem;
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
        
        .evidence-box {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            font-size: 0.8rem;
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
        
        .filter-btn:hover {{
            border-color: var(--primary-color);
            color: var(--primary-color);
        }}
        
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
        
        .no-errors {{
            text-align: center;
            padding: 2rem;
            color: var(--success-color);
            font-size: 1.1rem;
        }}
        
        .category-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.75rem;
            margin-top: 1rem;
        }}
        
        .category-stat {{
            background: var(--bg-color);
            padding: 0.75rem;
            border-radius: 6px;
            text-align: center;
        }}
        
        .category-stat-label {{
            font-size: 0.75rem;
            color: var(--text-muted);
        }}
        
        .category-stat-value {{
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--primary-color);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>LoCoMo Evaluation Report</h1>
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
                    <span class="header-meta-label">Model:</span>
                    <span>{model_name}</span>
                </div>
                <div class="header-meta-item">
                    <span class="header-meta-label">Generated:</span>
                    <span>{report_generated}</span>
                </div>
            </div>
        </div>
        
        <div class="summary-cards">
            <div class="summary-card">
                <div class="summary-card-value">{total_samples}</div>
                <div class="summary-card-label">Samples Evaluated</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value">{execution_time}</div>
                <div class="summary-card-label">Total Time</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value {accuracy_class}">{overall_accuracy}%</div>
                <div class="summary-card-label">Overall F1 Score</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value fraction">{total_correct}/{total_questions}</div>
                <div class="summary-card-label">Correct Answers (F1)</div>
            </div>
            {llm_judge_summary_card}
        </div>
        
        {category_stats_html}
        
        <div class="section">
            <h2 class="section-title">Results by Sample</h2>
            <table>
                <thead>
                    <tr>
                        <th>Model</th>
                        <th>Sample</th>
                        <th>Correct (F1)</th>
                        <th>F1 Score</th>
                        <th>LLM Judge Correct</th>
                        <th>LLM Judge</th>
                        <th>Execution Time</th>
                        <th>Executed At</th>
                    </tr>
                </thead>
                <tbody>
                    {result_rows}
                </tbody>
            </table>
        </div>
        
        <div class="section incorrect-section" id="incorrect-section">
            <h2 class="section-title">Incorrect Responses ({total_incorrect} errors)</h2>
            <div class="filter-bar">
                <span class="filter-bar-label">LLM Judge:</span>
                <button class="filter-btn active" data-filter-group="llm" data-filter="all" onclick="setFilter('llm','all')">All</button>
                <button class="filter-btn" data-filter-group="llm" data-filter="correct" onclick="setFilter('llm','correct')">CORRECT</button>
                <button class="filter-btn" data-filter-group="llm" data-filter="wrong" onclick="setFilter('llm','wrong')">WRONG</button>
            </div>
            <div class="filter-bar">
                <span class="filter-bar-label">Category:</span>
                <button class="filter-btn active" data-filter-group="category" data-filter="all" onclick="setFilter('category','all')">All</button>
                <button class="filter-btn" data-filter-group="category" data-filter="1" onclick="setFilter('category','1')">1 Single-hop</button>
                <button class="filter-btn" data-filter-group="category" data-filter="2" onclick="setFilter('category','2')">2 Temporal</button>
                <button class="filter-btn" data-filter-group="category" data-filter="3" onclick="setFilter('category','3')">3 Open-domain</button>
                <button class="filter-btn" data-filter-group="category" data-filter="4" onclick="setFilter('category','4')">4 Multi-hop</button>
                <button class="filter-btn" data-filter-group="category" data-filter="5" onclick="setFilter('category','5')">5 Adversarial</button>
                <span class="filter-count" id="filter-count"></span>
            </div>
            {incorrect_responses_html}
        </div>
        
        <div class="footer">
            Generated by LoCoMo Benchmark Report Generator<br>
            <a href="https://github.com/snap-research/locomo" target="_blank">LoCoMo: Evaluating Very Long-Term Conversational Memory of LLM Agents</a>
        </div>
    </div>
    <script>
    var activeFilters = {{ llm: 'all', category: 'all' }};
    
    function setFilter(group, value) {{
        activeFilters[group] = value;
        // Update active button in this group
        document.querySelectorAll('.filter-btn[data-filter-group="' + group + '"]').forEach(function(btn) {{
            btn.classList.remove('active');
        }});
        document.querySelector('.filter-btn[data-filter-group="' + group + '"][data-filter="' + value + '"]').classList.add('active');
        applyFilters();
    }}
    
    function applyFilters() {{
        var cards = document.querySelectorAll('.error-card');
        var shown = 0;
        var total = cards.length;
        cards.forEach(function(card) {{
            var llmStatus = card.getAttribute('data-llm-judge');
            var catStatus = card.getAttribute('data-category');
            var llmMatch = (activeFilters.llm === 'all' || llmStatus === activeFilters.llm);
            var catMatch = (activeFilters.category === 'all' || catStatus === activeFilters.category);
            if (llmMatch && catMatch) {{
                card.style.display = '';
                shown++;
            }} else {{
                card.style.display = 'none';
            }}
        }});
        var countEl = document.getElementById('filter-count');
        if (activeFilters.llm === 'all' && activeFilters.category === 'all') {{
            countEl.textContent = '';
        }} else {{
            countEl.textContent = 'Showing ' + shown + ' of ' + total;
        }}
    }}
    </script>
</body>
</html>
"""

RESULT_ROW_TEMPLATE = """
<tr>
    <td><strong>{model}</strong></td>
    <td>{sample_id}</td>
    <td>{correct_f1}</td>
    <td><span class="accuracy-badge {accuracy_class}">{accuracy}%</span></td>
    <td>{llm_judge_correct}</td>
    <td>{llm_judge_cell}</td>
    <td>{execution_time}</td>
    <td>{executed_at}</td>
</tr>
"""

MODEL_ERRORS_TEMPLATE = """
<div class="model-errors">
    <div class="model-errors-title">❌ {model} - {error_count} errors</div>
    {error_cards}
</div>
"""

ERROR_CARD_TEMPLATE = """
<div class="error-card" data-llm-judge="{llm_judge_status}" data-category="{category_num}">
    <div class="error-card-header">
        <span class="error-card-title">Question {question_num}</span>
        <div class="error-card-meta">
            <span>F1: {f1_score}</span>
            {llm_judge_html}
            <span class="category-badge">Category {category}</span>
            <span>Sample: {sample_id}</span>
        </div>
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
        <div class="error-field-label">Model's Answer</div>
        <div class="error-field-value">{model_answer}</div>
    </div>
    {evidence_html}
</div>
"""

CATEGORY_STATS_TEMPLATE = """
<div class="section">
    <h2 class="section-title">Accuracy by Question Category</h2>
    <p style="text-align: center; color: var(--text-muted); margin-top: -8px; margin-bottom: 16px; font-size: 0.9rem;">F1 Score (<span style="color: var(--primary-color); font-weight: 600;">blue</span>) &amp; LLM Judge (<span style="color: var(--text-muted); font-weight: 600;">gray</span>)</p>
    <div class="category-stats">
        {category_items}
    </div>
</div>
"""

CATEGORY_ITEM_TEMPLATE = """
<div class="category-stat">
    <div class="category-stat-label">{category_name}</div>
    <div class="category-stat-value">{accuracy}%</div>
    <div class="category-stat-value">({f1_correct}/{count})</div>
    {llm_judge_line}
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
    collection = db["locomo_results"]
    
    results = list(collection.find(
        {"experiment_name": experiment_name}
    ).sort("timestamp", 1))
    
    return results


# ============================================================================
# REPORT GENERATION
# ============================================================================

CATEGORY_NAMES = {
    1: "Single-hop",
    2: "Temporal",
    3: "Open-domain",
    4: "Multi-hop",
    5: "Adversarial"
}


def get_accuracy_class(accuracy: float) -> str:
    """Get CSS class based on accuracy value"""
    if accuracy >= 70:
        return "accuracy-high"
    elif accuracy >= 40:
        return "accuracy-medium"
    else:
        return "accuracy-low"


def get_summary_class(accuracy: float) -> str:
    """Get CSS class for summary card based on accuracy"""
    if accuracy >= 70:
        return "success"
    elif accuracy >= 40:
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


def generate_result_rows(results: List[Dict]) -> str:
    """Generate HTML table rows for each result"""
    rows = []
    
    for result in results:
        model = result.get("model", "Unknown")
        sample_id = result.get("sample_id", "N/A")
        total_questions = result.get("total_questions", 0)
        correct_count = result.get("correct_count", 0)
        accuracy = result.get("overall_accuracy", 0) * 100
        execution_time = result.get("execution_time_seconds")
        timestamp = result.get("timestamp")
        
        # LLM Judge metrics
        llm_correct = result.get("llm_judge_correct", None)
        llm_total = result.get("llm_judge_total", None)
        if llm_correct is not None and llm_total is not None and llm_total > 0:
            llm_accuracy = (llm_correct / llm_total) * 100
            llm_judge_correct = f"{llm_correct}/{llm_total}"
            llm_judge_cell = f'<span class="accuracy-badge {get_accuracy_class(llm_accuracy)}">{llm_accuracy:.1f}%</span>'
        else:
            llm_judge_correct = "N/A"
            llm_judge_cell = "N/A"
        
        row = RESULT_ROW_TEMPLATE.format(
            model=model,
            sample_id=sample_id,
            correct_f1=f"{correct_count}/{total_questions}",
            accuracy=f"{accuracy:.1f}",
            accuracy_class=get_accuracy_class(accuracy),
            llm_judge_correct=llm_judge_correct,
            llm_judge_cell=llm_judge_cell,
            execution_time=format_execution_time(execution_time),
            executed_at=format_timestamp(timestamp)
        )
        rows.append(row)
    
    return "\n".join(rows)


def generate_category_stats_html(results: List[Dict]) -> str:
    """Generate HTML for category statistics (F1 and LLM Judge)"""
    # Aggregate category stats across all results
    # Handle both numbered categories (category_1_accuracy) and named categories (single_hop_accuracy)
    category_totals = {}
    category_counts = {}
    category_question_counts = {}
    
    # F1 per-category correct count (derived from incorrect_responses)
    category_f1_incorrect = {}
    
    # LLM Judge per-category tracking
    category_llm_totals = {}
    category_llm_counts = {}
    category_llm_correct = {}
    category_llm_question_counts = {}
    
    # Named category mapping
    NAMED_CATEGORIES = {
        "single_hop": "Single-hop",
        "temporal": "Temporal",
        "open_domain": "Open-domain", 
        "multi_hop": "Multi-hop",
        "adversarial": "Adversarial"
    }
    
    for result in results:
        for key, value in result.items():
            # Skip LLM judge keys in this loop (handled separately below)
            if '_llm_judge_accuracy' in key:
                continue
            
            if key.endswith("_accuracy"):
                # Handle numbered categories (category_1_accuracy)
                if key.startswith("category_"):
                    cat_name = key.replace("category_", "").replace("_accuracy", "")
                    if cat_name.isdigit():
                        cat_int = int(cat_name)
                        display_name = CATEGORY_NAMES.get(cat_int, f"Category {cat_name}")
                    else:
                        display_name = cat_name.replace("_", " ").title()
                    count_key = f"category_{cat_name}_count"
                # Handle named categories (single_hop_accuracy, multi_hop_accuracy)
                else:
                    cat_name = key.replace("_accuracy", "")
                    if cat_name in NAMED_CATEGORIES:
                        display_name = NAMED_CATEGORIES[cat_name]
                        count_key = f"{cat_name}_count"
                    else:
                        continue  # Skip unknown categories
                
                if display_name not in category_totals:
                    category_totals[display_name] = 0.0
                    category_counts[display_name] = 0
                    category_question_counts[display_name] = 0
                
                category_totals[display_name] += value
                category_counts[display_name] += 1
                category_question_counts[display_name] += result.get(count_key, 0)
        
        # Collect LLM judge per-category metrics (e.g., single_hop_llm_judge_accuracy)
        for key, value in result.items():
            if key.endswith("_llm_judge_accuracy"):
                cat_name = key.replace("_llm_judge_accuracy", "")
                if cat_name in NAMED_CATEGORIES:
                    display_name = NAMED_CATEGORIES[cat_name]
                else:
                    continue
                
                if display_name not in category_llm_totals:
                    category_llm_totals[display_name] = 0.0
                    category_llm_counts[display_name] = 0
                    category_llm_correct[display_name] = 0
                    category_llm_question_counts[display_name] = 0
                
                category_llm_totals[display_name] += value
                category_llm_counts[display_name] += 1
                category_llm_correct[display_name] += result.get(f"{cat_name}_llm_judge_correct", 0)
                category_llm_question_counts[display_name] += result.get(f"{cat_name}_llm_judge_total", 0)
        
        # Count F1 incorrect responses per category
        for resp in result.get("incorrect_responses", []):
            cat_name = resp.get("category_name", "")
            if cat_name in NAMED_CATEGORIES:
                disp = NAMED_CATEGORIES[cat_name]
            else:
                cat_num = resp.get("category", 0)
                disp = CATEGORY_NAMES.get(cat_num, f"Category {cat_num}")
            category_f1_incorrect[disp] = category_f1_incorrect.get(disp, 0) + 1
    
    if not category_totals:
        return ""
    
    # Sort categories in a logical order
    category_order = ["Single-hop", "Temporal", "Open-domain", "Multi-hop", "Adversarial"]
    sorted_categories = []
    for cat in category_order:
        if cat in category_totals:
            sorted_categories.append(cat)
    # Add any remaining categories not in the predefined order
    for cat in category_totals.keys():
        if cat not in sorted_categories:
            sorted_categories.append(cat)
    
    # Generate category items
    items = []
    for display_name in sorted_categories:
        avg_accuracy = (category_totals[display_name] / category_counts[display_name] * 100) if category_counts[display_name] > 0 else 0
        total_count = category_question_counts[display_name]
        
        # Build LLM judge line if data is available for this category
        if display_name in category_llm_totals and category_llm_counts[display_name] > 0:
            llm_avg = (category_llm_totals[display_name] / category_llm_counts[display_name] * 100)
            llm_correct = category_llm_correct.get(display_name, 0)
            llm_total = category_llm_question_counts.get(display_name, 0)
            if llm_total > 0:
                llm_count_str = f' ({llm_correct}/{llm_total})'
            else:
                llm_count_str = ''
            llm_judge_line = (
                f'<div class="category-stat-value" style="font-size: 1.1rem; color: var(--text-muted);">'
                f'LLM Judge: {llm_avg:.1f}%{llm_count_str}</div>'
            )
        else:
            llm_judge_line = ""
        
        f1_incorrect = category_f1_incorrect.get(display_name, 0)
        f1_correct = total_count - f1_incorrect
        
        item = CATEGORY_ITEM_TEMPLATE.format(
            category_name=display_name,
            accuracy=f"{avg_accuracy:.1f}",
            f1_correct=f1_correct,
            llm_judge_line=llm_judge_line,
            count=total_count
        )
        items.append(item)
    
    return CATEGORY_STATS_TEMPLATE.format(category_items="\n".join(items))


def generate_incorrect_responses_html(results: List[Dict]) -> str:
    """Generate HTML for incorrect responses section"""
    html_parts = []
    has_errors = False
    
    for result in results:
        model = result.get("model", "Unknown")
        result_sample_id = result.get("sample_id", "?")  # Sample ID at result level
        incorrect_responses = result.get("incorrect_responses", [])
        
        if not incorrect_responses:
            continue
        
        has_errors = True
        error_cards = []
        
        for resp in incorrect_responses:
            # Generate evidence HTML if available
            evidence = resp.get("evidence", [])
            evidence_html = ""
            if evidence:
                evidence_str = ", ".join(evidence)
                evidence_html = f'''
    <div class="error-field">
        <div class="error-field-label">Evidence</div>
        <div class="evidence-box">{evidence_str}</div>
    </div>'''
            
            # Get sample_id from response or from result level
            sample_id = resp.get("sample_id", result_sample_id)
            
            # Get model answer - handle both 'model_answer' and 'pam_answer' keys
            model_answer = resp.get("model_answer") or resp.get("pam_answer") or "No answer provided"
            
            # Get category - handle both numbered and named
            category = resp.get("category", "?")
            category_name = resp.get("category_name", "")
            if category_name:
                category_display = f"{category} ({category_name})"
            else:
                category_display = str(category)
            
            # LLM judge badge if available
            llm_judge_score = resp.get("llm_judge_score")
            if llm_judge_score is not None:
                llm_label = "CORRECT" if llm_judge_score == 1 else "WRONG"
                llm_color = "color: var(--success-color)" if llm_judge_score == 1 else "color: var(--error-color)"
                llm_judge_html = f'<span style="{llm_color}; font-weight: 600">LLM Judge: {llm_label}</span>'
                llm_judge_status = "correct" if llm_judge_score == 1 else "wrong"
            else:
                llm_judge_html = ""
                llm_judge_status = "unknown"
            
            card = ERROR_CARD_TEMPLATE.format(
                question_num=resp.get("question_num", "?"),
                f1_score=f"{resp.get('f1_score', 0):.3f}",
                llm_judge_html=llm_judge_html,
                llm_judge_status=llm_judge_status,
                category_num=resp.get("category", "0"),
                category=category_display,
                sample_id=sample_id,
                question=resp.get("question", "N/A"),
                expected_answer=resp.get("expected_answer", "N/A"),
                model_answer=model_answer,
                evidence_html=evidence_html
            )
            error_cards.append(card)
        
        # Include sample_id in the model errors title for PAM
        model_display = f"{model} ({result_sample_id})" if result_sample_id != "?" else model
        
        model_section = MODEL_ERRORS_TEMPLATE.format(
            model=model_display,
            error_count=len(incorrect_responses),
            error_cards="\n".join(error_cards)
        )
        html_parts.append(model_section)
    
    if not has_errors:
        return '<div class="no-errors">✓ All responses were correct!</div>'
    
    return "\n".join(html_parts)


def generate_report(results: List[Dict], experiment_name: str, output_path: Path) -> bool:
    """Generate HTML report from MongoDB results"""
    if not results:
        print(f"No results found for experiment: {experiment_name}")
        return False
    
    # Extract metadata
    dataset_name = results[0].get("dataset_name", "locomo@1.0")
    model_name = results[0].get("model", "Unknown")
    
    # Get list of samples processed
    sample_ids = [r.get("sample_id", "N/A") for r in results]
    unique_samples = len(set(sample_ids))
    
    # Calculate overall metrics
    total_runs = len(results)
    total_questions = sum(r.get("total_questions", 0) for r in results)
    total_correct = sum(r.get("correct_count", 0) for r in results)
    total_incorrect = sum(r.get("incorrect_count", 0) for r in results)
    total_execution_time = sum(r.get("execution_time_seconds", 0) or 0 for r in results)
    
    # Calculate weighted average accuracy (by number of questions per sample)
    if total_questions > 0:
        # Weighted average: sum of (accuracy * questions) / total questions
        weighted_sum = sum(r.get("overall_accuracy", 0) * r.get("total_questions", 0) for r in results)
        avg_accuracy = (weighted_sum / total_questions) * 100
    else:
        avg_accuracy = 0
    
    print(f"  Samples: {unique_samples}")
    print(f"  Total questions: {total_questions}")
    print(f"  Total correct: {total_correct}")
    print(f"  Weighted average accuracy: {avg_accuracy:.2f}%")
    
    # Generate HTML sections
    result_rows = generate_result_rows(results)
    category_stats_html = generate_category_stats_html(results)
    incorrect_responses_html = generate_incorrect_responses_html(results)
    
    # Generate LLM Judge summary card if data is available
    llm_judge_total = sum(r.get("llm_judge_total", 0) for r in results)
    llm_judge_correct = sum(r.get("llm_judge_correct", 0) for r in results)
    if llm_judge_total > 0:
        llm_judge_accuracy = (llm_judge_correct / llm_judge_total) * 100
        llm_judge_class = get_summary_class(llm_judge_accuracy)
        llm_judge_summary_card = f"""
            <div class="summary-card">
                <div class="summary-card-value {llm_judge_class}">{llm_judge_accuracy:.1f}%</div>
                <div class="summary-card-label">LLM Judge Score</div>
            </div>
            <div class="summary-card">
                <div class="summary-card-value fraction">{llm_judge_correct}/{llm_judge_total}</div>
                <div class="summary-card-label">LLM Judge Correct</div>
            </div>"""
    else:
        llm_judge_summary_card = ""
    
    # Generate final HTML
    html = HTML_TEMPLATE.format(
        experiment_name=experiment_name,
        dataset_name=dataset_name,
        model_name=model_name,
        report_generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_samples=unique_samples,
        total_questions=total_questions,
        total_correct=total_correct,
        total_incorrect=total_incorrect,
        overall_accuracy=f"{avg_accuracy:.1f}",
        accuracy_class=get_summary_class(avg_accuracy),
        execution_time=format_execution_time(total_execution_time),
        category_stats_html=category_stats_html,
        result_rows=result_rows,
        incorrect_responses_html=incorrect_responses_html,
        llm_judge_summary_card=llm_judge_summary_card
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
        description="Generate HTML report from MongoDB LoCoMo evaluation results"
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
        default="tasks/locomo/reports",
        help="Output directory for reports (default: tasks/locomo/reports)"
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
        
        print(f"Found {len(results)} evaluation results")
        
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
