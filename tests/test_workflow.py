from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.core.schemas import ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow


class StubAgent(BaseAgent):
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, state: ResearchState) -> ResearchState:
        if self.name == "researcher":
            state.sources = [
                SourceDocument(title="Evidence", url="https://example.com", snippet="Fact")
            ]
            state.research_notes = "Evidence notes"
        elif self.name == "analyst":
            state.analysis_notes = "Supported analysis"
        elif self.name == "writer":
            state.final_answer = "Answer citing https://example.com"
        return state


def test_workflow_reaches_final_answer_with_trace() -> None:
    workflow = MultiAgentWorkflow(
        supervisor=SupervisorAgent(),
        researcher=StubAgent("researcher"),
        analyst=StubAgent("analyst"),
        writer=StubAgent("writer"),
        tracing_enabled=False,
    )
    initial = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))

    result = workflow.run(initial)

    assert result.final_answer
    assert result.route_history == ["researcher", "analyst", "writer", "done"]
    assert any(event["name"] == "node_timing" for event in result.trace)
