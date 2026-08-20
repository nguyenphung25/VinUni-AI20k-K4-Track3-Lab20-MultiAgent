# Benchmark Report

| Run | Latency (s) | Cost (USD) | Quality | Citation cov. | Failure rate | Notes |
|---|---:|---:|---:|---:|---:|---|
| single-agent-1 | 18.30 | 0.0012 | 6.0 | 0% | 0% | Routes: ['single_agent'] |
| multi-agent-1 | 22.02 | 0.0043 | 10.0 | 0% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done'] |
| single-agent-2 | 6.21 | 0.0017 | 6.0 | 0% | 0% | Routes: ['single_agent'] |
| multi-agent-2 | 24.15 | 0.0046 | 10.0 | 100% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done'] |
| single-agent-3 | 6.37 |  | 0.0 | 0% | 100% | Routes: [] |
| multi-agent-3 | 12.65 | 0.0041 | 10.0 | 100% | 0% | Routes: ['researcher', 'analyst', 'writer', 'done'] |

## Aggregate summary

- **single-agent**: mean latency 10.29s, mean structural quality 4.00/10, failure rate 33%.
- **multi-agent**: mean latency 19.61s, mean structural quality 10.00/10, failure rate 0%.

> Quality is a transparent structural proxy (answer, evidence, analysis, and errors), not an LLM-as-judge score. Use the peer-review rubric for final grading.

## Failure mode and remediation

`single-agent-3` failed when Gemini returned a transient HTTP 503, which explains the
baseline failure rate of 33%. A single-agent run had no downstream stage capable of preserving
partial work. The LLM client now retries connection, rate-limit, and provider 5xx failures with
bounded exponential backoff. In the multi-agent path, Researcher, Analyst, and Writer also have
deterministic fallbacks based on already collected evidence, while timeout and max-iteration
guards prevent infinite retry loops. This is why the benchmark recorded 0% multi-agent failure
despite provider instability.

## Trace evidence

- [Successful end-to-end Langfuse trace](https://jp.cloud.langfuse.com/project/cmt1bkvne004uad0hlsr0m2y6/traces/286d9c8c4336e81cfceb2938d428df15)
- Route: `researcher -> analyst -> writer -> done`
- Trace structure: root workflow and role executions are `AGENT`; Tavily is `RETRIEVER`;
  Gemini calls are `GENERATION` observations with model, token, latency, and cost data.
