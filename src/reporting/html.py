"""Render an HTML report from Mongo documents.

Consumes the new schema (`qa_responses` nested array on each doc). Pure
functions — no Mongo, no FS — except for the final write in `render_to_file`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from datasets.locomo.schemas import CATEGORY_NAMES

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _accuracy_class(pct: float) -> str:
    if pct >= 80:
        return "good"
    if pct >= 50:
        return "warn"
    return "bad"


def _aggregate_headline(docs: list[dict[str, Any]]) -> dict[str, Any]:
    total_q = sum(d.get("total_questions", 0) for d in docs)
    judge_correct = sum(d.get("judge_correct_count", 0) for d in docs)
    f1_sum = sum(d.get("total_f1_sum", 0.0) for d in docs)
    # Latency is stored per question; present it per batch (one model call) at
    # the report level. Total answering time = avg_latency_ms * questions
    # (summed across docs); divide by total batches.
    total_latency_time = sum(
        (d.get("avg_latency_ms", 0) or 0) * (d.get("total_questions", 0) or 0) for d in docs
    )
    total_batches = sum(_num_batches(d) for d in docs)
    judge_pct = (judge_correct / total_q * 100) if total_q else 0.0
    f1_pct = (f1_sum / total_q * 100) if total_q else 0.0
    avg_latency = total_latency_time / total_batches if total_batches else 0.0
    return {
        "total_questions": total_q,
        "judge_correct": judge_correct,
        "judge_total": total_q,
        "judge_accuracy_pct": round(judge_pct, 1),
        "judge_class": _accuracy_class(judge_pct),
        "f1_pct": round(f1_pct, 1),
        "f1_class": _accuracy_class(f1_pct),
        "avg_latency_ms": avg_latency,
    }


def _per_category(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate per-category from the `qa_responses` arrays."""
    f1_sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    judge_correct: dict[str, int] = defaultdict(int)
    for d in docs:
        for qa in d.get("qa_responses", []):
            name = qa.get("category_name") or CATEGORY_NAMES.get(
                qa.get("category", 0), str(qa.get("category"))
            )
            f1_sums[name] += qa.get("f1_score", 0.0)
            counts[name] += 1
            if qa.get("judge_correct"):
                judge_correct[name] += 1
    rows: list[dict[str, Any]] = []
    # Stable order mirroring LoCoMo paper
    for name in ["single_hop", "temporal", "open_domain", "multi_hop", "adversarial"]:
        if name not in counts:
            continue
        n = counts[name]
        judge_pct = judge_correct[name] / n * 100 if n else 0.0
        rows.append(
            {
                "name": name.replace("_", " ").title(),
                "count": n,
                "f1": f1_sums[name] / n if n else 0.0,
                "judge_correct": judge_correct[name],
                "judge_pct": judge_pct,
                "judge_class": _accuracy_class(judge_pct),
            }
        )
    # Any custom categories not in the canonical list
    for name in counts:
        if name in {"single_hop", "temporal", "open_domain", "multi_hop", "adversarial"}:
            continue
        n = counts[name]
        judge_pct = judge_correct[name] / n * 100 if n else 0.0
        rows.append(
            {
                "name": name,
                "count": n,
                "f1": f1_sums[name] / n if n else 0.0,
                "judge_correct": judge_correct[name],
                "judge_pct": judge_pct,
                "judge_class": _accuracy_class(judge_pct),
            }
        )
    return rows


def _per_sample(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in docs:
        judge_acc = d.get("judge_accuracy", 0.0) or 0.0
        # Stored p50/p95 are per question; scale to per batch (per model call) by
        # the average batch size (questions / batches).
        batches = _num_batches(d)
        total_q = d.get("total_questions", 0) or 0
        batch_factor = (total_q / batches) if batches else 1.0
        rows.append(
            {
                "baseline": d.get("baseline", "?"),
                "sample_id": d.get("sample_id", "?"),
                "total_questions": d.get("total_questions", 0),
                "overall_accuracy": d.get("overall_accuracy", 0.0) or 0.0,
                "judge_accuracy": judge_acc,
                "judge_class": _accuracy_class(judge_acc * 100),
                "p50_latency_ms": (d.get("p50_latency_ms", 0.0) or 0.0) * batch_factor,
                "p95_latency_ms": (d.get("p95_latency_ms", 0.0) or 0.0) * batch_factor,
                "execution_time_seconds": d.get("execution_time_seconds", 0.0) or 0.0,
                "memory_creation_duration_sec": d.get("memory_creation_duration_sec", 0.0) or 0.0,
                "total_cost_usd": d.get("total_cost_usd", 0.0) or 0.0,
                "avg_context_tokens": _avg_context_tokens(d),
            }
        )
    return rows


def _num_batches(doc: dict[str, Any]) -> int:
    """Number of batched model calls for a sample = ceil(questions / batch_size).

    The comparison unit is one model call (one batch). MCP baselines store
    `batch_size`, Pam stores `pam_batch_size`; single-call baselines (LiteLLM)
    have neither, so batch_size = 1 and per-batch == per-question.
    """
    total_q = doc.get("total_questions", 0) or 0
    if total_q <= 0:
        return 0
    bs = doc.get("batch_size") or doc.get("pam_batch_size") or 1
    return (total_q + bs - 1) // bs


def _avg_context_tokens(doc: dict[str, Any]) -> float:
    """Average context tokens per batch for one sample doc.

    Normally `total_context_tokens / batches`, but Pam doesn't report
    `context_tokens` (it stays 0), so for Pam we approximate the injected
    context as `total_enriched_user_prompt_tokens - total_prompt_tokens`.
    """
    batches = _num_batches(doc)
    if not batches:
        return 0.0
    if doc.get("baseline") == "pam":
        ctx_total = (doc.get("total_enriched_user_prompt_tokens", 0) or 0) - (
            doc.get("total_prompt_tokens", 0) or 0
        )
    else:
        ctx_total = doc.get("total_context_tokens", 0) or 0
    return ctx_total / batches


def _avg_per_batch(doc: dict[str, Any], total_field: str) -> float:
    """`doc[total_field] / num_batches`, 0 when there are no batches."""
    batches = _num_batches(doc)
    if not batches:
        return 0.0
    return (doc.get(total_field, 0) or 0) / batches


def _avg_input_tokens(doc: dict[str, Any]) -> float:
    """Average input tokens per batch. Pam doesn't report `input_tokens`, so its
    input is taken as the agent's enriched user prompt."""
    field = (
        "total_enriched_user_prompt_tokens"
        if doc.get("baseline") == "pam"
        else ("total_input_tokens")
    )
    return _avg_per_batch(doc, field)


def _per_sample_tokens(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-batch token averages (one batched model call) for each sample doc."""
    rows: list[dict[str, Any]] = []
    for d in docs:
        rows.append(
            {
                "baseline": d.get("baseline", "?"),
                "sample_id": d.get("sample_id", "?"),
                "avg_input": _avg_input_tokens(d),
                "avg_output": _avg_per_batch(d, "total_output_tokens"),
                "avg_context": _avg_context_tokens(d),
                "avg_prompt": _avg_per_batch(d, "total_prompt_tokens"),
                "avg_agent_input": _avg_per_batch(d, "total_agent_input_tokens"),
                "avg_agent_output": _avg_per_batch(d, "total_agent_output_tokens"),
                "avg_agent_cache_read": _avg_per_batch(d, "total_agent_cache_read_tokens"),
                "avg_agent_cache_write": _avg_per_batch(d, "total_agent_cache_write_tokens"),
            }
        )
    return rows


def _incorrect(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter qa_responses to LLM-judge-incorrect entries."""
    out: list[dict[str, Any]] = []
    for d in docs:
        sample_id = d.get("sample_id", "?")
        for qa in d.get("qa_responses", []):
            if qa.get("judge_correct"):
                continue
            out.append({**qa, "sample_id": sample_id})
    return out


# Canonical category order, mirroring the LoCoMo paper.
_CATEGORY_ORDER = ["single_hop", "temporal", "open_domain", "multi_hop", "adversarial"]


def _incorrect_categories(incorrect: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distinct question types present in the incorrect set, with counts — used
    to build the Incorrect-responses filter buttons."""
    counts: dict[str, int] = {}
    for r in incorrect:
        name = r.get("category_name") or "unknown"
        counts[name] = counts.get(name, 0) + 1
    ordered = [n for n in _CATEGORY_ORDER if n in counts]
    ordered += [n for n in counts if n not in _CATEGORY_ORDER]
    return [{"name": n, "count": counts[n]} for n in ordered]


def build_context(*, dataset: str, exp_name: str, docs: list[dict[str, Any]]) -> dict[str, Any]:
    baselines = sorted({d.get("baseline", "?") for d in docs})
    seeds = sorted({d.get("seed", "?") for d in docs}, key=lambda x: (x is None, x))
    judges = sorted({d.get("judge_model", "?") for d in docs})
    samples = sorted({d.get("sample_id", "?") for d in docs})
    dataset_names = sorted({d.get("dataset_name", dataset) for d in docs})
    # Distinct batch size(s) across the runs (MCP `batch_size` / Pam
    # `pam_batch_size`; single-call baselines = 1). Shown once at the top.
    batch_sizes = sorted({d.get("batch_size") or d.get("pam_batch_size") or 1 for d in docs})
    incorrect = _incorrect(docs)
    return {
        "dataset": dataset,
        "exp_name": exp_name,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "dataset_name": ", ".join(dataset_names) or dataset,
        "baselines": baselines,
        "seeds": seeds,
        "batch_sizes": batch_sizes,
        "judge_models": judges,
        "sample_count": len(samples),
        "headline": _aggregate_headline(docs),
        "per_category": _per_category(docs),
        "per_sample": _per_sample(docs),
        "per_sample_tokens": _per_sample_tokens(docs),
        # Cost column is shown only when some run reports a real cost (harness
        # experiments); Pam reports it as 0 and the column stays hidden.
        "show_cost": any((d.get("total_cost_usd") or 0) > 0 for d in docs),
        "incorrect": incorrect,
        "incorrect_categories": _incorrect_categories(incorrect),
    }


# ---------------------------------------------------------------------------
# Harmix: judge-only report (no token-F1, no LoCoMo categories). Each persona
# (environment) is a sample; open/draft cases (null expected_answer) are
# recorded but not judged, so accuracy is over the JUDGED count.
# ---------------------------------------------------------------------------


def _aggregate_headline_harmix(docs: list[dict[str, Any]]) -> dict[str, Any]:
    total_q = sum(d.get("total_questions", 0) for d in docs)
    judged = sum(d.get("judged_count", 0) for d in docs)
    unjudged = sum(d.get("unjudged_count", 0) for d in docs)
    judge_correct = sum(d.get("judge_correct_count", 0) for d in docs)
    total_latency_time = sum(
        (d.get("avg_latency_ms", 0) or 0) * (d.get("total_questions", 0) or 0) for d in docs
    )
    total_batches = sum(_num_batches(d) for d in docs)
    judge_pct = (judge_correct / judged * 100) if judged else 0.0
    avg_latency = total_latency_time / total_batches if total_batches else 0.0
    return {
        "total_questions": total_q,
        "judged": judged,
        "unjudged": unjudged,
        "judge_correct": judge_correct,
        "judge_accuracy_pct": round(judge_pct, 1),
        "judge_class": _accuracy_class(judge_pct),
        "avg_latency_ms": avg_latency,
        "total_cost_usd": sum(d.get("total_cost_usd", 0.0) or 0.0 for d in docs),
    }


def _per_sample_harmix(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in docs:
        judge_acc = d.get("judge_accuracy", 0.0) or 0.0
        batches = _num_batches(d)
        total_q = d.get("total_questions", 0) or 0
        batch_factor = (total_q / batches) if batches else 1.0
        rows.append(
            {
                "baseline": d.get("baseline", "?"),
                "sample_id": d.get("sample_id", "?"),
                "total_questions": total_q,
                "judged": d.get("judged_count", 0),
                "unjudged": d.get("unjudged_count", 0),
                "judge_accuracy": judge_acc,
                "judge_accuracy_std": d.get("judge_accuracy_std", 0.0) or 0.0,
                "samples_per_question": d.get("samples_per_question", 1) or 1,
                "judge_class": _accuracy_class(judge_acc * 100),
                "p50_latency_ms": (d.get("p50_latency_ms", 0.0) or 0.0) * batch_factor,
                "p95_latency_ms": (d.get("p95_latency_ms", 0.0) or 0.0) * batch_factor,
                "execution_time_seconds": d.get("execution_time_seconds", 0.0) or 0.0,
                "memory_creation_duration_sec": d.get("memory_creation_duration_sec", 0.0) or 0.0,
                "total_cost_usd": d.get("total_cost_usd", 0.0) or 0.0,
                "avg_context_tokens": _avg_context_tokens(d),
            }
        )
    return rows


def _verdict(qa: dict[str, Any]) -> str:
    """Judge verdict bucket for a qa row: correct | incorrect | unjudged.

    `unjudged` = an open/draft case with no gold answer (never scored).
    """
    if not qa.get("judged"):
        return "unjudged"
    return "correct" if qa.get("judge_correct") else "incorrect"


def _responses_harmix(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """All qa rows across docs, each tagged with `sample_id` and `verdict`."""
    out: list[dict[str, Any]] = []
    for d in docs:
        sample_id = d.get("sample_id", "?")
        for qa in d.get("qa_responses", []):
            out.append({**qa, "sample_id": sample_id, "verdict": _verdict(qa)})
    return out


# Verdict filter buttons are shown in this fixed order (only when non-empty).
_VERDICT_ORDER = ["correct", "incorrect", "unjudged"]


def _verdict_filters(responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for r in responses:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return [{"name": v, "count": counts[v]} for v in _VERDICT_ORDER if v in counts]


def _persona_filters(responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for r in responses:
        counts[r["sample_id"]] = counts.get(r["sample_id"], 0) + 1
    return [{"name": n, "count": counts[n]} for n in sorted(counts)]


def build_context_harmix(
    *, dataset: str, exp_name: str, docs: list[dict[str, Any]]
) -> dict[str, Any]:
    baselines = sorted({d.get("baseline", "?") for d in docs})
    judges = sorted({d.get("judge_model", "?") for d in docs})
    samples = sorted({d.get("sample_id", "?") for d in docs})
    dataset_names = sorted({d.get("dataset_name", dataset) for d in docs})
    batch_sizes = sorted({d.get("batch_size") or d.get("pam_batch_size") or 1 for d in docs})
    # avg@k: max K across docs (>1 ⇒ the report shows avg@k + the closest-to-mean answer).
    samples_per_question = max((d.get("samples_per_question", 1) or 1) for d in docs) if docs else 1
    responses = _responses_harmix(docs)
    return {
        "is_harmix": True,
        "dataset": dataset,
        "exp_name": exp_name,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "dataset_name": ", ".join(dataset_names) or dataset,
        "baselines": baselines,
        "batch_sizes": batch_sizes,
        "judge_models": judges,
        "sample_count": len(samples),
        "samples_per_question": samples_per_question,
        "headline": _aggregate_headline_harmix(docs),
        "per_sample": _per_sample_harmix(docs),
        "per_sample_tokens": _per_sample_tokens(docs),
        "show_cost": any((d.get("total_cost_usd") or 0) > 0 for d in docs),
        # All responses (correct + incorrect + unjudged), filterable by verdict
        # and persona; default view shows everything.
        "responses": responses,
        "verdict_filters": _verdict_filters(responses),
        "persona_filters": _persona_filters(responses),
    }


def render(context: dict[str, Any]) -> str:
    template_name = "report_harmix.html.j2" if context.get("is_harmix") else "report.html.j2"
    template = _env.get_template(template_name)
    return template.render(**context)


def build_report_context(
    *, dataset: str, exp_name: str, docs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Pick the right context builder for the dataset (harmix is judge-only)."""
    if dataset == "harmix":
        return build_context_harmix(dataset=dataset, exp_name=exp_name, docs=docs)
    return build_context(dataset=dataset, exp_name=exp_name, docs=docs)


def render_to_file(
    *, dataset: str, exp_name: str, docs: list[dict[str, Any]], output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render(build_report_context(dataset=dataset, exp_name=exp_name, docs=docs))
    output_path.write_text(html, encoding="utf-8")
    return output_path
