"""Routing tests replacing the starter repository's intentional TODO guard."""

from multi_agent_research_lab.agents import SupervisorAgent
from multi_agent_research_lab.core.schemas import ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState


def test_supervisor_routes_through_required_stages() -> None:
    supervisor = SupervisorAgent()
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))

    assert supervisor.run(state).route_history[-1] == "researcher"

    state.sources = [SourceDocument(title="Source", url="https://example.com", snippet="Notes")]
    state.research_notes = "Research notes"
    assert supervisor.run(state).route_history[-1] == "analyst"

    state.analysis_notes = "Analysis"
    assert supervisor.run(state).route_history[-1] == "writer"

    state.final_answer = "Final answer"
    assert supervisor.run(state).route_history[-1] == "done"


def test_supervisor_stops_at_iteration_guardrail() -> None:
    supervisor = SupervisorAgent()
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        iteration=supervisor._settings.max_iterations,
    )

    supervisor.run(state)

    assert state.route_history[-1] == "done"
    assert any("max_iterations" in error for error in state.errors)
