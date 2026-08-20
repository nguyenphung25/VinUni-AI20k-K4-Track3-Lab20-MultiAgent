"""Reproducible benchmark for single-agent and multi-agent runners."""

from collections.abc import Callable
from time import perf_counter

from multi_agent_research_lab.core.schemas import BenchmarkMetrics, ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.services.llm_client import LLMClient

Runner = Callable[[str], ResearchState]


def single_agent_runner(query: str) -> ResearchState:
    """Single-agent baseline: one LLM does everything."""
    llm = LLMClient()
    state = ResearchState(request=ResearchQuery(query=query))

    system = "You are a research assistant. Research and write a comprehensive answer."
    resp = llm.complete(
        system, f"Research and answer: {query}", observation_name="generate-baseline-report"
    )
    state.final_answer = resp.content
    state.route_history = ["single_agent"]
    state.add_trace_event(
        "single_agent",
        {
            "content_length": len(resp.content),
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cost_usd": resp.cost_usd,
        },
    )
    return state


def multi_agent_runner(query: str) -> ResearchState:
    """Multi-agent workflow."""
    state = ResearchState(request=ResearchQuery(query=query))
    workflow = MultiAgentWorkflow()
    return workflow.run(state)


def run_benchmark(
    run_name: str, query: str, runner: Runner
) -> tuple[ResearchState, BenchmarkMetrics]:
    """Run benchmark and measure latency + cost."""
    started = perf_counter()
    try:
        state = runner(query)
    except Exception as exc:
        state = ResearchState(request=ResearchQuery(query=query), errors=[str(exc)])
    latency = perf_counter() - started

    # Calculate total cost from trace
    total_cost = sum(e.get("payload", {}).get("cost_usd", 0) or 0 for e in state.trace)

    metrics = BenchmarkMetrics(
        run_name=run_name,
        latency_seconds=latency,
        estimated_cost_usd=total_cost or None,
        quality_score=_calc_quality_score(state),
        citation_coverage=_calc_citation_coverage(state),
        failure_rate=0.0 if state.final_answer else 1.0,
        notes=f"Routes: {state.route_history}"
        + (f"; Trace: {state.trace_url}" if state.trace_url else ""),
    )
    return state, metrics


def _calc_citation_coverage(state: ResearchState) -> float:
    """Ratio of claims with sources / total claims."""
    if not state.final_answer:
        return 0.0
    source_urls = {source.url for source in state.sources if source.url}
    if not source_urls:
        return 0.0
    cited_urls = sum(url in state.final_answer for url in source_urls)
    return cited_urls / len(source_urls)


def _calc_quality_score(state: ResearchState) -> float:
    """Transparent structural proxy; human review should replace it for final grading."""
    score = 0.0
    if state.final_answer:
        score += 4.0
        score += min(len(state.final_answer.split()) / 250, 1.0)
    if state.sources:
        score += 1.5
    if state.research_notes:
        score += 1.0
    if state.analysis_notes:
        score += 1.5
    if not state.errors:
        score += 1.0
    return min(round(score, 2), 10.0)


def run_full_benchmark(queries: list[str]) -> list[BenchmarkMetrics]:
    """Run benchmark for multiple queries."""
    results = []

    for i, query in enumerate(queries):
        print(f"\n--- Query {i + 1}/{len(queries)} ---")
        print(f"Q: {query[:80]}...")

        # Single-agent
        _, single_metrics = run_benchmark(f"single-agent-{i + 1}", query, single_agent_runner)
        results.append(single_metrics)
        print(f"  Single: {single_metrics.latency_seconds:.1f}s")

        # Multi-agent
        _, multi_metrics = run_benchmark(f"multi-agent-{i + 1}", query, multi_agent_runner)
        results.append(multi_metrics)
        print(f"  Multi:  {multi_metrics.latency_seconds:.1f}s")

    return results
