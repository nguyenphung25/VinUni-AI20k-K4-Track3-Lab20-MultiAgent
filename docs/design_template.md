# System Design

## Problem

The system answers open-ended research questions by collecting web evidence, analyzing
it, and producing a cited report for a specified audience. It must remain observable
and terminate safely when a provider fails.

## Why multi-agent?

Research has separable stages with different failure modes. Role separation makes source
collection, synthesis, and writing independently testable and leaves an auditable handoff
in shared state. A single-agent baseline remains in the project for comparison; multi-agent
is justified only when the quality benefit exceeds its additional latency and cost.

## Agent roles

| Agent | Responsibility | Input | Output | Failure mode |
|---|---|---|---|---|
| Supervisor | Select the first incomplete stage | Shared state | Next route | Stops at iteration limit |
| Researcher | Search and summarize evidence | Query, max sources | Sources, research notes | Search error or LLM fallback |
| Analyst | Compare claims and flag weak evidence | Research notes | Structured analysis | Deterministic evidence fallback |
| Writer | Produce audience-specific cited report | Sources and analysis | Final answer | Deterministic report fallback |

## Shared state

`request` stores validated user intent. `sources`, `research_notes`, `analysis_notes`, and
`final_answer` form explicit handoffs. `route_history` and `iteration` make routing and
termination debuggable. `agent_results` preserves role outputs, while `trace` records timing,
token/cost metadata, and fallback events. `trace_url` links the run to its Langfuse trace.
`errors` distinguishes degraded runs.

## Routing policy

`Supervisor -> Researcher -> Supervisor -> Analyst -> Supervisor -> Writer -> Supervisor -> END`.
The supervisor uses prerequisite-based deterministic routing, preventing a model from skipping
a required stage. Every worker returns to the supervisor.

## Guardrails

- Max iterations: 6 by default; a terminal route and error are recorded at the limit.
- Timeout: 60 seconds by default, checked at node boundaries; provider calls also have timeouts.
- Retry: transient connection/rate-limit failures use three bounded exponential-backoff attempts.
- Fallback: collected evidence becomes notes, analysis, and a cited report if the LLM is unavailable.
- Validation: Pydantic validates queries, state, sources, outputs, and benchmark metrics.
- Observability: Langfuse records one root `agent`, typed role agents, Tavily as a `retriever`,
  and Gemini calls as `generation` observations with model, tokens, latency, and cost.

## Benchmark plan

Three queries from `configs/lab_default.yaml` compare single and multi-agent runs. Metrics are
wall-clock latency, known-model token cost, structural quality (0-10), citation coverage, and
failure rate. Expected outcome: multi-agent generally improves evidence structure and citations,
while single-agent is faster and cheaper. Human peer review remains the final quality judgment.
