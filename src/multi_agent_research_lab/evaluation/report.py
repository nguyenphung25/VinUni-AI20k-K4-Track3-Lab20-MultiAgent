"""Benchmark report rendering."""

from statistics import median

from multi_agent_research_lab.core.schemas import BenchmarkMetrics


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _aggregate(group: list[BenchmarkMetrics]) -> dict[str, float]:
    latencies = [item.latency_seconds for item in group]
    return {
        "mean_latency": _mean(latencies),
        "median_latency": median(latencies) if latencies else 0.0,
        "mean_cost": _mean([item.estimated_cost_usd or 0.0 for item in group]),
        "mean_quality": _mean(
            [item.quality_score for item in group if item.quality_score is not None]
        ),
        "mean_citation": _mean(
            [item.citation_coverage for item in group if item.citation_coverage is not None]
        ),
        "failure_rate": _mean(
            [item.failure_rate for item in group if item.failure_rate is not None]
        ),
    }


def _percent_delta(candidate: float, baseline: float) -> str:
    if baseline == 0:
        return "n/a"
    return f"{((candidate - baseline) / baseline):+.0%}"


def render_markdown_report(metrics: list[BenchmarkMetrics]) -> str:
    """Render detailed runs and aggregate comparison to markdown."""

    queries = list(dict.fromkeys(item.query for item in metrics if item.query))
    lines = [
        "# Benchmark Report",
        "",
        "## Benchmark design",
        "",
        f"This exploratory benchmark uses {len(queries)} matched queries: each query is run once "
        "with the single-agent baseline and once with the multi-agent workflow. Both variants use "
        "the same configured Gemini model and environment.",
        "",
    ]
    lines.extend(f"{index}. {query}" for index, query in enumerate(queries, start=1))
    lines.extend(
        [
            "",
            "## Per-run results",
            "",
            "| Run | Latency (s) | Cost (USD) | Quality | Citation cov. | Failure rate | Notes |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in metrics:
        cost = "" if item.estimated_cost_usd is None else f"{item.estimated_cost_usd:.4f}"
        quality = "" if item.quality_score is None else f"{item.quality_score:.1f}"
        citation = "" if item.citation_coverage is None else f"{item.citation_coverage:.0%}"
        failure = "" if item.failure_rate is None else f"{item.failure_rate:.0%}"
        lines.append(
            f"| {item.run_name} | {item.latency_seconds:.2f} | {cost} | {quality} "
            f"| {citation} | {failure} | {item.notes} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate summary",
            "",
            "| Architecture | Runs | Mean latency | Median latency | Mean cost/run | "
            "Mean quality | Mean citation coverage | Failure rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    aggregates: dict[str, dict[str, float]] = {}
    for family in ("single-agent", "multi-agent"):
        group = [item for item in metrics if item.run_name.startswith(family)]
        if not group:
            continue
        aggregate = _aggregate(group)
        aggregates[family] = aggregate
        lines.append(
            f"| {family} | {len(group)} | {aggregate['mean_latency']:.2f}s | "
            f"{aggregate['median_latency']:.2f}s | ${aggregate['mean_cost']:.4f} | "
            f"{aggregate['mean_quality']:.2f}/10 | {aggregate['mean_citation']:.0%} | "
            f"{aggregate['failure_rate']:.0%} |"
        )
    lines.extend(
        [
            "",
            "## Quality rubric and limitations",
            "",
            "Quality is a deterministic, architecture-neutral output proxy (0-10): non-empty "
            "answer 5 points, answer depth up to 1, retrieved source evidence 1, citation coverage "
            "up to 2, and error-free completion 1. It does not reward private research or analysis "
            "notes, so both architectures are judged on observable output properties.",
            "",
            "Citation coverage is the fraction of retrieved source URLs reproduced in the final "
            "answer; it measures source usage, not factual correctness. The suite is an "
            "exploratory matched sample with one run per query, not a statistically powered "
            "production eval. Human review with the peer-review rubric remains the final quality "
            "check.",
        ]
    )
    single = aggregates.get("single-agent")
    multi = aggregates.get("multi-agent")
    lines.extend(["", "## Trade-off analysis", ""])
    if single is not None and multi is not None:
        lines.extend(
            [
                f"Compared with the single-agent baseline, multi-agent changed mean latency by "
                f"{_percent_delta(multi['mean_latency'], single['mean_latency'])} and mean cost "
                f"by {_percent_delta(multi['mean_cost'], single['mean_cost'])}. Quality changed "
                f"by {multi['mean_quality'] - single['mean_quality']:+.2f}/10, citation coverage "
                f"by {(multi['mean_citation'] - single['mean_citation']):+.0%}, and failure rate "
                f"by {(multi['failure_rate'] - single['failure_rate']):+.0%}.",
                "",
                "**Decision:** prefer multi-agent for evidence-heavy research where traceable "
                "sources, staged failure recovery, and output quality justify extra latency and "
                "cost. Prefer single-agent for short, low-risk requests where speed and cost "
                "matter more than explicit retrieval and specialist handoffs.",
            ]
        )
    else:
        lines.append("Both architecture families are required for a trade-off comparison.")
    failed_runs = [item.run_name for item in metrics if (item.failure_rate or 0) > 0]
    lines.extend(["", "## Failure mode and remediation", ""])
    if failed_runs:
        lines.append(
            f"Failures were observed in: {', '.join(failed_runs)}. Provider-side 5xx, "
            "rate-limit, or connection errors can interrupt an LLM call. The client uses bounded "
            "exponential-backoff retries for transient failures; worker agents fall back to "
            "evidence-preserving deterministic output so the multi-agent workflow can degrade "
            "gracefully instead of looping indefinitely."
        )
    else:
        lines.append(
            "No run failed in this sample. The principal residual risk is a transient provider "
            "or search outage; bounded retries, timeouts, max iterations, and deterministic "
            "worker fallbacks prevent an unbounded or silent failure. A successful end-to-end "
            "run can still contain a recovered request-level error, so individual trace attempts "
            "and citation coverage must also be reviewed."
        )
    return "\n".join(lines) + "\n"
