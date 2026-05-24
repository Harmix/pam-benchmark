"""Tiny markdown summary — used when --format md is selected."""

from __future__ import annotations

from typing import Any

from reporting.html import build_context


def render_markdown(*, dataset: str, exp_name: str, docs: list[dict[str, Any]]) -> str:
    ctx = build_context(dataset=dataset, exp_name=exp_name, docs=docs)
    h = ctx["headline"]
    lines: list[str] = [
        f"# {dataset.title()} report — {exp_name}",
        "",
        f"- Generated: {ctx['generated_at']}",
        f"- Baselines: {', '.join(ctx['baselines'])}",
        f"- Seeds: {', '.join(str(s) for s in ctx['seeds'])}",
        f"- Judge: {', '.join(ctx['judge_models'])}",
        f"- Samples: {ctx['sample_count']}",
        "",
        "## Headline",
        "",
        f"- LLM-judge accuracy: **{h['judge_accuracy_pct']}%** ({h['judge_correct']}/{h['judge_total']})",
        f"- F1 (weighted): **{h['f1_pct']}%**",
        f"- Total cost: ${h['total_cost_usd']:.4f}",
        f"- Avg latency / question: {h['avg_latency_ms']:.0f} ms",
        "",
        "## Per category",
        "",
        "| Category | N | F1 | LLM-judge |",
        "|---|---:|---:|---:|",
    ]
    for row in ctx["per_category"]:
        lines.append(
            f"| {row['name']} | {row['count']} | "
            f"{row['f1'] * 100:.1f}% | {row['judge_pct']:.1f}% ({row['judge_correct']}/{row['count']}) |"
        )
    lines.extend(
        [
            "",
            "## Per sample",
            "",
            "| Baseline | Seed | Sample | Q | F1 | Judge | Cost | p50/p95 ms | Wall-clock |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in ctx["per_sample"]:
        lines.append(
            f"| {row['baseline']} | {row['seed']} | {row['sample_id']} | "
            f"{row['total_questions']} | "
            f"{row['overall_accuracy'] * 100:.1f}% | {row['judge_accuracy'] * 100:.1f}% | "
            f"${row['total_cost_usd']:.4f} | "
            f"{row['p50_latency_ms']:.0f}/{row['p95_latency_ms']:.0f} | "
            f"{row['execution_time_seconds']:.1f}s |"
        )
    return "\n".join(lines)
