"""LangGraph workflow — orchestrates the multi-agent graph."""

from collections.abc import Callable
from time import perf_counter
from typing import Any, cast

from langgraph.graph import END, StateGraph

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.quality import evaluate_quality
from multi_agent_research_lab.observability.tracing import (
    current_trace_url,
    flush_remote_tracing,
    remote_observation,
    remote_trace_attributes,
    score_current_trace,
)


def _route_after_supervisor(state: ResearchState) -> str:
    """Đọc route cuối cùng từ supervisor."""
    if not state.route_history:
        return "done"
    last_route = state.route_history[-1]
    if last_route in ("researcher", "analyst", "writer", "done"):
        return last_route
    return "done"


class MultiAgentWorkflow:
    """Builds and runs the multi-agent graph."""

    def __init__(
        self,
        supervisor: BaseAgent | None = None,
        researcher: BaseAgent | None = None,
        analyst: BaseAgent | None = None,
        writer: BaseAgent | None = None,
        tracing_enabled: bool = True,
    ) -> None:
        self._supervisor = supervisor or SupervisorAgent()
        self._researcher = researcher or ResearcherAgent()
        self._analyst = analyst or AnalystAgent()
        self._writer = writer or WriterAgent()
        self._settings = get_settings()
        self._deadline: float | None = None
        self._tracing_enabled = tracing_enabled

    @staticmethod
    def _agent_input(state: ResearchState) -> dict[str, Any]:
        return {
            "query": state.request.query,
            "iteration": state.iteration,
            "source_count": len(state.sources),
            "has_research_notes": bool(state.research_notes),
            "has_analysis_notes": bool(state.analysis_notes),
            "has_final_answer": bool(state.final_answer),
        }

    @staticmethod
    def _agent_output(state: ResearchState) -> dict[str, Any]:
        return {
            "route": state.route_history[-1] if state.route_history else None,
            "source_count": len(state.sources),
            "has_research_notes": bool(state.research_notes),
            "has_analysis_notes": bool(state.analysis_notes),
            "has_final_answer": bool(state.final_answer),
            "error_count": len(state.errors),
        }

    def _timed(self, agent: BaseAgent) -> Callable[[ResearchState], ResearchState]:
        def run_node(state: ResearchState) -> ResearchState:
            started = perf_counter()
            with remote_observation(
                name=f"run-{agent.name}",
                as_type="agent",
                input=self._agent_input(state),
                metadata={"role": agent.name, "framework": "langgraph"},
                enabled=self._tracing_enabled,
            ) as observation:
                try:
                    result = agent.run(state)
                except Exception as exc:
                    if observation is not None:
                        observation.update(level="ERROR", status_message=type(exc).__name__)
                    raise
                duration = perf_counter() - started
                if observation is not None:
                    observation.update(
                        output=self._agent_output(result),
                        metadata={"role": agent.name, "duration_seconds": duration},
                    )
            result.add_trace_event(
                "node_timing",
                {"agent": agent.name, "duration_seconds": duration},
            )
            if self._deadline is not None and perf_counter() >= self._deadline:
                message = f"Workflow exceeded timeout of {self._settings.timeout_seconds}s"
                if message not in result.errors:
                    result.errors.append(message)
                result.iteration = self._settings.max_iterations
            return result

        return run_node

    def build(self) -> Any:
        """Create the LangGraph workflow."""
        graph = StateGraph(ResearchState)

        # Add nodes
        graph.add_node("supervisor", cast(Any, self._timed(self._supervisor)))
        graph.add_node("researcher", cast(Any, self._timed(self._researcher)))
        graph.add_node("analyst", cast(Any, self._timed(self._analyst)))
        graph.add_node("writer", cast(Any, self._timed(self._writer)))

        # Entry point
        graph.set_entry_point("supervisor")

        # Conditional routing from supervisor
        graph.add_conditional_edges(
            "supervisor",
            _route_after_supervisor,
            {
                "researcher": "researcher",
                "analyst": "analyst",
                "writer": "writer",
                "done": END,
            },
        )

        # After worker completes → back to supervisor
        graph.add_edge("researcher", "supervisor")
        graph.add_edge("analyst", "supervisor")
        graph.add_edge("writer", "supervisor")

        return graph.compile()

    def run(self, state: ResearchState) -> ResearchState:
        """Execute the graph and return final state."""
        graph = self.build()
        self._deadline = perf_counter() + self._settings.timeout_seconds
        try:
            with remote_observation(
                name="run-multi-agent-research",
                as_type="agent",
                input={"query": state.request.query, "audience": state.request.audience},
                metadata={"max_sources": state.request.max_sources, "framework": "langgraph"},
                enabled=self._tracing_enabled,
            ) as root_observation:
                with remote_trace_attributes(
                    trace_name="multi-agent-research",
                    tags=["multi-agent", "langgraph", "research"],
                    metadata={"app_env": self._settings.app_env},
                    enabled=self._tracing_enabled,
                ):
                    result = graph.invoke(
                        state,
                        config={"recursion_limit": self._settings.max_iterations * 2 + 2},
                    )
                if isinstance(result, dict):
                    final_state = ResearchState(**result)
                elif isinstance(result, ResearchState):
                    final_state = result
                else:
                    raise ValueError(f"Unexpected graph result type: {type(result)}")
                if root_observation is not None:
                    quality = evaluate_quality(final_state)
                    root_observation.update(
                        output={
                            "answer": final_state.final_answer,
                            "routes": final_state.route_history,
                            "source_count": len(final_state.sources),
                            "error_count": len(final_state.errors),
                        }
                    )
                    score_current_trace(
                        name="structural-quality",
                        value=quality.structural_quality,
                        data_type="NUMERIC",
                        comment=(
                            "Deterministic 0-10 output rubric: answer, depth, source evidence, "
                            "citation coverage, and error-free completion."
                        ),
                    )
                    score_current_trace(
                        name="citation-coverage",
                        value=quality.citation_coverage,
                        data_type="NUMERIC",
                        comment="Fraction of retrieved source URLs cited in the final answer.",
                    )
                    score_current_trace(
                        name="run-success",
                        value=float(quality.run_success),
                        data_type="BOOLEAN",
                        comment="True when the workflow produced a non-empty final answer.",
                    )
                    final_state.trace_url = current_trace_url()
                return final_state
        finally:
            self._deadline = None
            if self._tracing_enabled:
                flush_remote_tracing()
