"""Deterministic, architecture-neutral quality proxies for benchmark runs."""

from dataclasses import dataclass

from multi_agent_research_lab.core.state import ResearchState


@dataclass(frozen=True)
class QualityEvaluation:
    """Transparent output-quality signals shared by reports and tracing."""

    structural_quality: float
    citation_coverage: float
    run_success: bool


def calculate_citation_coverage(state: ResearchState) -> float:
    """Return the fraction of retrieved source URLs cited in the final answer."""
    if not state.final_answer:
        return 0.0
    source_urls = {source.url for source in state.sources if source.url}
    if not source_urls:
        return 0.0
    cited_urls = sum(url in state.final_answer for url in source_urls)
    return round(cited_urls / len(source_urls), 4)


def evaluate_quality(state: ResearchState) -> QualityEvaluation:
    """Score observable output properties without rewarding hidden agent internals.

    Rubric (0-10): answer present 5, answer depth 1, source evidence 1,
    retrieved-source citation coverage 2, and error-free completion 1.
    """
    answer = state.final_answer or ""
    citation_coverage = calculate_citation_coverage(state)
    score = 0.0
    if answer:
        score += 5.0
        score += min(len(answer.split()) / 250, 1.0)
    if state.sources:
        score += 1.0
    score += 2.0 * citation_coverage
    if answer and not state.errors:
        score += 1.0
    return QualityEvaluation(
        structural_quality=min(round(score, 2), 10.0),
        citation_coverage=citation_coverage,
        run_success=bool(answer),
    )
