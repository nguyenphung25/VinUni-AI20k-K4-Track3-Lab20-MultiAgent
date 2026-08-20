# Benchmark Report

## Benchmark design

This exploratory benchmark uses 5 matched queries: each query is run once with the single-agent baseline and once with the multi-agent workflow. Both variants use the same configured Gemini model and environment.

1. Research GraphRAG state-of-the-art and write a 500-word summary
2. Compare single-agent and multi-agent workflows for customer support
3. Summarize production guardrails for LLM agents
4. Compare RAG evaluation methods for factuality and citation grounding
5. Explain when agentic search is worth its latency and cost overhead

## Per-run results

| Run | Latency (s) | Cost (USD) | Quality | Citation cov. | Failure rate | Notes |
|---|---:|---:|---:|---:|---:|---|
| single-agent-1 | 24.34 | 0.0012 | 7.0 | 0% | 0% | Routes: ['single_agent'] |
| multi-agent-1 | 18.41 | 0.0044 | 8.0 | 0% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done']; Trace: https://jp.cloud.langfuse.com/project/cmt1bkvne004uad0hlsr0m2y6/traces/ee80ebbbf6210effabba7665ae828801 |
| single-agent-2 | 5.57 | 0.0016 | 7.0 | 0% | 0% | Routes: ['single_agent'] |
| multi-agent-2 | 33.07 | 0.0045 | 10.0 | 100% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done']; Trace: https://jp.cloud.langfuse.com/project/cmt1bkvne004uad0hlsr0m2y6/traces/7ae2d9f1670d5ab43705499857e3688f |
| single-agent-3 | 7.91 | 0.0017 | 7.0 | 0% | 0% | Routes: ['single_agent'] |
| multi-agent-3 | 46.96 | 0.0045 | 10.0 | 100% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done']; Trace: https://jp.cloud.langfuse.com/project/cmt1bkvne004uad0hlsr0m2y6/traces/357ee5d6a972c951d108949fe043bedc |
| single-agent-4 | 17.45 | 0.0018 | 7.0 | 0% | 0% | Routes: ['single_agent'] |
| multi-agent-4 | 22.38 | 0.0042 | 8.0 | 0% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done']; Trace: https://jp.cloud.langfuse.com/project/cmt1bkvne004uad0hlsr0m2y6/traces/0784fc3d8f99278b5f3fb3b228578911 |
| single-agent-5 | 5.45 | 0.0016 | 7.0 | 0% | 0% | Routes: ['single_agent'] |
| multi-agent-5 | 26.27 | 0.0046 | 10.0 | 100% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done']; Trace: https://jp.cloud.langfuse.com/project/cmt1bkvne004uad0hlsr0m2y6/traces/c196f809f1e6e4fa13ff13a507495f0d |

## Aggregate summary

| Architecture | Runs | Mean latency | Median latency | Mean cost/run | Mean quality | Mean citation coverage | Failure rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| single-agent | 5 | 12.15s | 7.91s | $0.0016 | 7.00/10 | 0% | 0% |
| multi-agent | 5 | 29.42s | 26.27s | $0.0045 | 9.20/10 | 60% | 0% |

## Quality rubric and limitations

Quality is a deterministic, architecture-neutral output proxy (0-10): non-empty answer 5 points, answer depth up to 1, retrieved source evidence 1, citation coverage up to 2, and error-free completion 1. It does not reward private research or analysis notes, so both architectures are judged on observable output properties.

Citation coverage is the fraction of retrieved source URLs reproduced in the final answer; it measures source usage, not factual correctness. The suite is an exploratory matched sample with one run per query, not a statistically powered production eval. Human review with the peer-review rubric remains the final quality check.

## Trade-off analysis

Compared with the single-agent baseline, multi-agent changed mean latency by +142% and mean cost by +184%. Quality changed by +2.20/10, citation coverage by +60%, and failure rate by +0%.

**Decision:** prefer multi-agent for evidence-heavy research where traceable sources, staged failure recovery, and output quality justify extra latency and cost. Prefer single-agent for short, low-risk requests where speed and cost matter more than explicit retrieval and specialist handoffs.

## Failure mode and remediation

No end-to-end run failed, but the benchmark log captured a Gemini HTTP 503 on the first request. The bounded exponential-backoff retry recovered with HTTP 200, so the transient request error did not become a run failure. Langfuse records each attempt separately, making the recovered error visible instead of hiding it behind the final success. If all retries fail, worker agents use evidence-preserving deterministic fallbacks; workflow timeout and max-iteration guards prevent an infinite loop.

Two multi-agent outputs (`multi-agent-1` and `multi-agent-4`) retrieved sources but omitted their URLs, resulting in 0% citation coverage. This is a quality failure rather than an execution failure. After this benchmark, Writer gained a deterministic citation check that appends only missing URLs already collected by Researcher and records `citation_repair_count`; it never invents a source. Future benchmark runs should validate that this moves coverage upward without claiming that URL presence alone proves factual correctness.

## Trace evidence

- [Public end-to-end Langfuse trace with Scores](https://jp.cloud.langfuse.com/project/cmt1bkvne004uad0hlsr0m2y6/traces/286d9c8c4336e81cfceb2938d428df15)
- [Trace tree screenshot](multi-agent-research.png)
- Trace-level scores: `structural-quality`, `citation-coverage`, and `run-success`.
- Observation types: workflow and roles are `AGENT`, Tavily is `RETRIEVER`, and Gemini calls are `GENERATION` with model, token, latency, and cost data.
