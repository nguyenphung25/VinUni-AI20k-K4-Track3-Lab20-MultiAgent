"""Analyst agent — extracts insights from research notes."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient


class AnalystAgent(BaseAgent):
    """Turns research notes into structured insights."""

    name = "analyst"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        if not state.research_notes:
            state.errors.append("No research notes to analyze")
            state.add_trace_event("analyst", {"error": "no_research_notes"})
            return state

        system_prompt = (
            "You are a research analyst.\n"
            "Analyze the research notes and produce structured insights:\n"
            "1. Key claims (with evidence strength: strong/medium/weak)\n"
            "2. Competing viewpoints\n"
            "3. Gaps or weak evidence\n"
            "4. Overall assessment"
        )

        user_prompt = f"Query: {state.request.query}\n\nResearch notes:\n{state.research_notes}"

        try:
            resp = self._llm.complete(
                system_prompt, user_prompt, observation_name="analyze-evidence"
            )
            state.analysis_notes = resp.content
            state.agent_results.append(AgentResult(agent=AgentName.ANALYST, content=resp.content))
            usage = {
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "cost_usd": resp.cost_usd,
            }
        except AgentExecutionError as exc:
            state.errors.append(f"Analysis used fallback: {exc}")
            state.analysis_notes = (
                "The collected evidence is preserved below for manual comparison. "
                "Treat claims as provisional and verify them against the linked sources.\n\n"
                f"{state.research_notes}"
            )
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.ANALYST,
                    content=state.analysis_notes,
                    metadata={"fallback": True},
                )
            )
            usage = {"fallback": True}

        state.add_trace_event(
            "analyst",
            {"analysis_length": len(state.analysis_notes or ""), **usage},
        )
        return state
