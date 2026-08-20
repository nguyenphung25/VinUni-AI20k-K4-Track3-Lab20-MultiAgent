"""Researcher agent — collects sources and creates research notes."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.search_client import SearchClient


class ResearcherAgent(BaseAgent):
    """Collects sources and creates concise research notes."""

    name = "researcher"

    def __init__(self, llm: LLMClient | None = None, search: SearchClient | None = None) -> None:
        self._llm = llm or LLMClient()
        self._search = search or SearchClient()

    def run(self, state: ResearchState) -> ResearchState:
        try:
            sources = self._search.search(
                state.request.query,
                max_results=state.request.max_sources,
            )
            state.sources = sources
        except AgentExecutionError as exc:
            state.errors.append(str(exc))
            state.add_trace_event("researcher", {"error": str(exc)})
            return state

        if not sources:
            state.errors.append("Search returned no sources")
            state.add_trace_event("researcher", {"sources_found": 0})
            return state

        system_prompt = (
            "You are a research assistant.\n"
            "Summarize the following sources into concise research notes.\n"
            "Include key findings, claims, and cite sources by title."
        )

        sources_text = "\n\n".join(f"[{s.title}]({s.url}): {s.snippet}" for s in state.sources)
        user_prompt = f"Query: {state.request.query}\n\nSources:\n{sources_text}"

        try:
            resp = self._llm.complete(
                system_prompt, user_prompt, observation_name="summarize-sources"
            )
            state.research_notes = resp.content
            state.agent_results.append(
                AgentResult(agent=AgentName.RESEARCHER, content=resp.content)
            )
            usage = {
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "cost_usd": resp.cost_usd,
            }
        except AgentExecutionError as exc:
            state.errors.append(f"Research summarization used fallback: {exc}")
            state.research_notes = "\n\n".join(
                f"## {source.title}\n{source.snippet}\nSource: {source.url or 'N/A'}"
                for source in sources
            )
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.RESEARCHER,
                    content=state.research_notes,
                    metadata={"fallback": True},
                )
            )
            usage = {"fallback": True}

        state.add_trace_event(
            "researcher",
            {
                "sources_found": len(sources),
                "notes_length": len(state.research_notes or ""),
                **usage,
            },
        )
        return state
