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
        f"- Batch size: {', '.join(str(b) for b in ctx['batch_sizes'])}",
        f"- Judge: {', '.join(ctx['judge_models'])}",
        f"- Samples: {ctx['sample_count']}",
        "",
        "## Headline",
        "",
        f"- LLM-judge accuracy: **{h['judge_accuracy_pct']}%** ({h['judge_correct']}/{h['judge_total']})",
        f"- F1 (weighted): **{h['f1_pct']}%**",
        f"- Avg latency / batch: {h['avg_latency_ms']:.0f} ms",
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
            "| Baseline | Sample | Q | F1 | Judge | Avg. Context Tokens | p50/p95 ms | "
            "Memory Creation | Answer+Judge |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    show_cost = ctx["show_cost"]
    if show_cost:
        # Append a Cost column header for harness experiments.
        lines[-2] = lines[-2].rstrip(" |") + " | Cost (USD) |"
        lines[-1] = lines[-1].rstrip(" |") + "|---:|"
    for row in ctx["per_sample"]:
        cost = f" ${row['total_cost_usd']:.4f} |" if show_cost else ""
        lines.append(
            f"| {row['baseline']} | {row['sample_id']} | "
            f"{row['total_questions']} | "
            f"{row['overall_accuracy'] * 100:.1f}% | {row['judge_accuracy'] * 100:.1f}% | "
            f"{row['avg_context_tokens']:.0f} | "
            f"{row['p50_latency_ms']:.0f}/{row['p95_latency_ms']:.0f} | "
            f"{row['memory_creation_duration_sec']:.1f}s | "
            f"{row['execution_time_seconds']:.1f}s |" + cost
        )
    lines.extend(
        [
            "",
            "## Per-sample token metrics",
            "",
            "Per-batch token averages (one batched model call). Avg Input is total input "
            "(fresh + cache read + cache write). For Pam, Avg Input uses the enriched user "
            "prompt and Avg Context is enriched minus prompt.",
            "",
            "| Baseline | Sample | Avg Input | Avg Output | Avg Context | Avg Prompt | "
            "Avg Agent Input | Avg Agent Output | Avg Agent Cache Read | Avg Agent Cache Write |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in ctx["per_sample_tokens"]:
        lines.append(
            f"| {row['baseline']} | {row['sample_id']} | "
            f"{row['avg_input']:.0f} | {row['avg_output']:.0f} | "
            f"{row['avg_context']:.0f} | {row['avg_prompt']:.0f} | "
            f"{row['avg_agent_input']:.0f} | {row['avg_agent_output']:.0f} | "
            f"{row['avg_agent_cache_read']:.0f} | {row['avg_agent_cache_write']:.0f} |"
        )
    return "\n".join(lines)
