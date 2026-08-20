"""Supervisor/router with deterministic, inspectable transitions."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.state import ResearchState


class SupervisorAgent(BaseAgent):
    """Decides which worker should run next and when to stop."""

    name = "supervisor"

    def __init__(self) -> None:
        self._settings = get_settings()

    def run(self, state: ResearchState) -> ResearchState:
        if state.iteration >= self._settings.max_iterations:
            state.record_route("done")
            message = "Workflow stopped after reaching max_iterations"
            if not state.final_answer and message not in state.errors:
                state.errors.append(message)
            state.add_trace_event(
                "supervisor",
                {"action": "done", "reason": "max_iterations_reached"},
            )
            return state

        if state.final_answer:
            state.record_route("done")
            state.add_trace_event("supervisor", {"action": "done", "reason": "final_answer_ready"})
            return state

        # This policy is deterministic so invalid LLM output cannot skip prerequisites.
        route = self._heuristic_route(state)
        state.record_route(route)
        state.add_trace_event("supervisor", {"action": route, "iteration": state.iteration})

        return state

    def _heuristic_route(self, state: ResearchState) -> str:
        """Select the first incomplete stage in the research pipeline."""
        if not state.sources or not state.research_notes:
            return "researcher"
        if not state.analysis_notes:
            return "analyst"
        if not state.final_answer:
            return "writer"
        return "done"
