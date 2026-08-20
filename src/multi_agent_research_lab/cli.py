"""Command-line entrypoint for the lab starter."""

from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import LabError
from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.logging import configure_logging
from multi_agent_research_lab.observability.tracing import (
    configure_remote_tracing,
    flush_remote_tracing,
)

app = typer.Typer(help="Multi-Agent Research Lab starter CLI")
console = Console()


def _init() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_remote_tracing(settings)


def _parse_query(query: str) -> ResearchQuery:
    try:
        return ResearchQuery(query=query)
    except ValidationError as exc:
        console.print(
            Panel.fit(
                f"Invalid query: {exc.errors()[0]['msg']}",
                title="Input Error",
                style="red",
            )
        )
        raise typer.Exit(code=1) from exc


@app.command()
def baseline(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run a minimal single-agent baseline."""
    _init()
    from multi_agent_research_lab.services.llm_client import LLMClient

    request = _parse_query(query)
    state = ResearchState(request=request)

    console.print("[bold]Running single-agent baseline...[/bold]")
    try:
        llm = LLMClient()
        resp = llm.complete(
            "You are a research assistant. Research and write a comprehensive answer.",
            f"Research and answer: {query}",
            observation_name="generate-baseline-report",
        )
    except LabError as exc:
        flush_remote_tracing()
        console.print(Panel.fit(str(exc), title="Execution Error", style="red"))
        raise typer.Exit(code=2) from exc
    state.final_answer = resp.content
    state.route_history = ["single_agent"]

    console.print(Panel.fit(state.final_answer, title="Single-Agent Baseline"))
    console.print(f"\n[dim]Tokens: {resp.input_tokens} in / {resp.output_tokens} out[/dim]")
    flush_remote_tracing()


@app.command("multi-agent")
def multi_agent(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run the multi-agent workflow."""
    _init()
    state = ResearchState(request=_parse_query(query))
    workflow = MultiAgentWorkflow()

    console.print("[bold]Running multi-agent workflow...[/bold]")
    try:
        result = workflow.run(state)
    except LabError as exc:
        console.print(Panel.fit(str(exc), title="Execution Error", style="red"))
        raise typer.Exit(code=2) from exc

    if result.final_answer:
        console.print(Panel.fit(result.final_answer, title="Multi-Agent Answer"))
    else:
        console.print(Panel.fit("No final answer produced.", title="Error", style="red"))

    console.print(f"\n[dim]Route history: {result.route_history}[/dim]")
    console.print(f"[dim]Iterations: {result.iteration}[/dim]")
    if result.trace_url:
        console.print(f"[dim]Langfuse trace: {result.trace_url}[/dim]")
    if result.errors:
        console.print(f"[red]Errors: {result.errors}[/red]")
    from multi_agent_research_lab.services.storage import LocalArtifactStore

    trace_path = LocalArtifactStore().write_text(
        "latest_trace.json", result.model_dump_json(indent=2)
    )
    console.print(f"[dim]Trace saved to {trace_path}[/dim]")


@app.command()
def benchmark() -> None:
    """Run single vs multi-agent benchmark."""
    _init()
    from multi_agent_research_lab.evaluation.benchmark import run_full_benchmark
    from multi_agent_research_lab.evaluation.report import render_markdown_report
    from multi_agent_research_lab.services.storage import LocalArtifactStore

    queries = [
        "Research GraphRAG state-of-the-art and write a 500-word summary",
        "Compare single-agent and multi-agent workflows for customer support",
        "Summarize production guardrails for LLM agents",
        "Compare RAG evaluation methods for factuality and citation grounding",
        "Explain when agentic search is worth its latency and cost overhead",
    ]

    console.print("[bold]Running benchmark: single-agent vs multi-agent[/bold]")
    metrics = run_full_benchmark(queries)
    flush_remote_tracing()
    report = render_markdown_report(metrics)

    store = LocalArtifactStore()
    path = store.write_text("benchmark_report.md", report)
    console.print(Panel.fit(f"Report saved to {path}", title="Benchmark Complete"))
    console.print(report)


if __name__ == "__main__":
    app()
