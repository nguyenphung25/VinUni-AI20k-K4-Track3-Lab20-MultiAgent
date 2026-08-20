"""Benchmark report rendering."""

from multi_agent_research_lab.core.schemas import BenchmarkMetrics


def render_markdown_report(metrics: list[BenchmarkMetrics]) -> str:
    """Render detailed runs and aggregate comparison to markdown."""

    lines = [
        "# Benchmark Report",
        "",
        "| Run | Latency (s) | Cost (USD) | Quality | Citation cov. | Failure rate | Notes |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in metrics:
        cost = "" if item.estimated_cost_usd is None else f"{item.estimated_cost_usd:.4f}"
        quality = "" if item.quality_score is None else f"{item.quality_score:.1f}"
        citation = "" if item.citation_coverage is None else f"{item.citation_coverage:.0%}"
        failure = "" if item.failure_rate is None else f"{item.failure_rate:.0%}"
        lines.append(
            f"| {item.run_name} | {item.latency_seconds:.2f} | {cost} | {quality} "
            f"| {citation} | {failure} | {item.notes} |"
        )
    lines.extend(["", "## Aggregate summary", ""])
    for family in ("single-agent", "multi-agent"):
        group = [item for item in metrics if item.run_name.startswith(family)]
        if not group:
            continue
        latency = sum(item.latency_seconds for item in group) / len(group)
        quality_values = [item.quality_score for item in group if item.quality_score is not None]
        failures = [item.failure_rate for item in group if item.failure_rate is not None]
        mean_quality = sum(quality_values) / len(quality_values) if quality_values else 0.0
        mean_failure = sum(failures) / len(failures) if failures else 0.0
        lines.append(
            f"- **{family}**: mean latency {latency:.2f}s, "
            f"mean structural quality {mean_quality:.2f}/10, "
            f"failure rate {mean_failure:.0%}."
        )
    lines.extend(
        [
            "",
            "> Quality is a transparent structural proxy (answer, evidence, analysis, "
            "and errors), not an LLM-as-judge score. Use the peer-review rubric for final grading.",
        ]
    )
    return "\n".join(lines) + "\n"
