# LLM Judge Evaluation Report Generator

Generates comprehensive visual charts and HTML reports from your LLM judge evaluation results.

## Features

The report generator creates:

1. **Accuracy Bar Chart** - Compare accuracy across all configurations
2. **Metrics Comparison** - Compare accuracy, average score, and confidence
3. **Question Heatmap** - Visual matrix showing which questions were answered correctly
4. **Score Distribution** - Histograms showing score distributions for each config
5. **Confidence Analysis** - Scatter plot analyzing confidence vs correctness
6. **Interactive HTML Report** - Detailed report with all questions, answers, and reasoning

## Installation

Install the required dependencies:

```bash
pip install -r report_requirements.txt
```

## Usage

### Generate Reports for All Configurations

```bash
python generate_eval_report.py --output-dir ./outputs
```

This will:
- Load all `llm_judge_results.json` files from config directories
- Generate all charts and reports
- Save to `./outputs/evaluation_reports_TIMESTAMP/`

### Generate Report for Specific Configuration

```bash
python generate_eval_report.py --output-dir ./outputs --config config_1_20251029_130807
```

### Specify Custom Report Directory

```bash
python generate_eval_report.py --output-dir ./outputs --report-dir ./my_reports
```

## Output Structure

The report generator creates:

```
evaluation_reports_TIMESTAMP/
├── accuracy_chart.png           # Bar chart comparing accuracy
├── metrics_comparison.png       # Multi-metric comparison
├── question_heatmap.png         # Correctness heatmap
├── score_distribution.png       # Score distribution histograms
├── confidence_analysis.png      # Confidence vs score scatter plot
└── evaluation_report.html       # Interactive HTML report
```

## Chart Descriptions

### 1. Accuracy Chart
- Bar chart showing accuracy percentage for each configuration
- Labels show correct/total counts and percentage
- Easy comparison across configurations

### 2. Metrics Comparison
- Side-by-side comparison of three metrics:
    - Accuracy (% correct answers)
    - Average Score (mean score from LLM judge)
    - Average Confidence (mean confidence from LLM judge)
- Grouped bars for easy visual comparison

### 3. Question Heatmap
- Matrix visualization showing correctness per question
- Green ✓ = correct, Red ✗ = incorrect
- Quickly identify which questions are problematic across configs
- Identify patterns in question difficulty

### 4. Score Distribution
- Histogram for each configuration showing score distribution
- Includes mean and standard deviation
- Helps understand scoring patterns
- Multiple subplots for comparing distributions

### 5. Confidence Analysis
- Scatter plot showing confidence vs score
- Circles (○) = correct answers
- Crosses (×) = incorrect answers
- Color-coded by configuration
- Helps identify if confidence correlates with correctness

### 6. HTML Report
- Complete interactive report with all details
- Overall summary with key metrics
- Configuration comparison table
- Detailed question-by-question breakdown
- Includes all answers and reasoning
- Color-coded for easy scanning

## HTML Report Features

The HTML report includes:

- **Overall Summary**: Total stats across all configurations
- **Comparison Table**: Side-by-side config metrics
- **Detailed Results**: Every question with:
    - Question text
    - Expected answer
    - Agent's answer
    - Score and confidence
    - LLM judge reasoning
    - Color coding (green = correct, red = incorrect)

## Examples

### Example 1: Weekly Evaluation
```bash
# Run evaluation first
python unified_llm_judge.py --output-dir ./outputs

# Generate reports
python generate_eval_report.py --output-dir ./outputs --report-dir ./reports/week_43

# Open the HTML report
open ./reports/week_43/evaluation_report.html
```

### Example 2: Compare Single Config
```bash
python generate_eval_report.py \
  --output-dir ./outputs \
  --config config_1_20251029_130807 \
  --report-dir ./single_config_report
```

### Example 3: Automated Workflow
```bash
#!/bin/bash
# Run evaluation and generate reports automatically

python unified_llm_judge.py --output-dir ./outputs --parallel 4

python generate_eval_report.py --output-dir ./outputs

# Open the latest report
LATEST_REPORT=$(ls -td ./outputs/evaluation_reports_* | head -1)
open "$LATEST_REPORT/evaluation_report.html"
```

## Integration with Evaluation Pipeline

The report generator works seamlessly with `unified_llm_judge.py`:

1. Run the evaluation pipeline to generate `llm_judge_results.json` files
2. Run the report generator to visualize results
3. Open the HTML report to review findings

## Tips

1. **Regular Reports**: Generate reports after each evaluation run to track progress
2. **Compare Configs**: Use the heatmap to identify consistently difficult questions
3. **Review Reasoning**: Check the HTML report's reasoning section to understand judge decisions
4. **Track Trends**: Save reports with timestamps to compare performance over time
5. **Share Results**: The HTML report is self-contained and easy to share with team members

## Troubleshooting

**No results found:**
- Make sure you've run `unified_llm_judge.py` first
- Check that `llm_judge_results.json` files exist in config directories

**Import errors:**
- Install dependencies: `pip install -r report_requirements.txt`

**Charts not displaying:**
- Ensure matplotlib backend is properly configured
- Try running in a terminal with display support

## Requirements

- Python 3.7+
- matplotlib
- numpy

## Author

Generated for LLM judge evaluation pipeline analysis and reporting.