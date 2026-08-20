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
            state.agent_results.append(AgentResult(agent=AgentName.WRITER, content=resp.content))
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
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.WRITER,
                    content=state.final_answer,
                    metadata={"fallback": True},
                )
            )
            usage = {"fallback": True}

        state.add_trace_event(
            "writer",
            {"answer_length": len(state.final_answer or ""), **usage},
        )
        return state
