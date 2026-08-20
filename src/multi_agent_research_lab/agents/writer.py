"""Writer agent — produces final answer from research and analysis notes."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient


class WriterAgent(BaseAgent):
    """Produces final answer from research and analysis notes."""

    name = "writer"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        if not state.analysis_notes:
            state.errors.append("No analysis notes to write from")
            state.add_trace_event("writer", {"error": "no_analysis_notes"})
            return state

        system_prompt = (
            "You are a technical writer.\n"
            "Write a clear, well-structured final answer based on the research and analysis.\n"
            "Include citations to sources where available.\n"
            f"Target audience: {state.request.audience}."
        )

        sources_text = "\n".join(f"- [{s.title}]({s.url})" for s in state.sources)

        user_prompt = (
            f"Query: {state.request.query}\n"
            f"Audience: {state.request.audience}\n\n"
            f"Sources:\n{sources_text}\n\n"
            f"Research notes:\n{state.research_notes}\n\n"
            f"Analysis:\n{state.analysis_notes}\n\n"
            "Write the final answer."
        )

        try:
            resp = self._llm.complete(system_prompt, user_prompt, observation_name="write-report")
            state.final_answer = resp.content
            result_metadata: dict[str, bool] = {}
            usage = {
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "cost_usd": resp.cost_usd,
            }
        except AgentExecutionError as exc:
            state.errors.append(f"Writing used fallback: {exc}")
            state.final_answer = (
                f"# Research report\n\n## Question\n{state.request.query}\n\n"
                f"## Evidence and analysis\n{state.analysis_notes}\n\n"
                f"## Sources\n{sources_text}\n\n"
                "_Generated with the deterministic fallback because the configured "
                "language model was unavailable._"
            )
            result_metadata = {"fallback": True}
            usage = {"fallback": True}

        missing_sources = [
            source
            for source in state.sources
            if source.url and source.url not in (state.final_answer or "")
        ]
        if missing_sources:
            source_appendix = "\n".join(
                f"- [{source.title}]({source.url})" for source in missing_sources
            )
            state.final_answer = (
                f"{state.final_answer or ''}\n\n## Sources\n{source_appendix}"
            ).strip()

        state.agent_results.append(
            AgentResult(
                agent=AgentName.WRITER,
                content=state.final_answer or "",
                metadata=result_metadata,
            )
        )
        state.add_trace_event(
            "writer",
            {
                "answer_length": len(state.final_answer or ""),
                "citation_repair_count": len(missing_sources),
                **usage,
            },
        )
        return state
