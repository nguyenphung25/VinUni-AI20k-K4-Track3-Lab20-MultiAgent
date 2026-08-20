"""Optional deterministic critic for citation and completeness checks."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState


class CriticAgent(BaseAgent):
    """Optional fact-checking and safety-review agent."""

    name = "critic"

    def run(self, state: ResearchState) -> ResearchState:
        """Append review findings without rewriting the answer."""
        findings: list[str] = []
        if not state.final_answer:
            findings.append("No final answer was produced.")
        else:
            cited = sum(
                1 for source in state.sources if source.url and source.url in state.final_answer
            )
            if state.sources and cited == 0:
                findings.append("The answer does not cite any collected source URL.")
            if len(state.final_answer.split()) < 100:
                findings.append("The answer may be too short for a research response.")
        if state.errors:
            findings.append(f"The workflow recorded {len(state.errors)} error(s).")
        review = "No deterministic issues found." if not findings else " ".join(findings)
        state.agent_results.append(
            AgentResult(
                agent=AgentName.CRITIC,
                content=review,
                metadata={"passed": not findings},
            )
        )
        state.add_trace_event("critic", {"findings": findings, "passed": not findings})
        return state
