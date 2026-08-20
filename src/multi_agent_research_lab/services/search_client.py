"""Search client backed by Tavily's HTTP API."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import AgentExecutionError
from multi_agent_research_lab.core.schemas import SourceDocument
from multi_agent_research_lab.observability.tracing import remote_observation


class SearchClient:
    """Tavily-powered search client."""

    def __init__(self, timeout: float = 20.0) -> None:
        settings = get_settings()
        if not settings.tavily_api_key:
            raise AgentExecutionError("TAVILY_API_KEY not set in .env")
        self._api_key = settings.tavily_api_key
        self._timeout = timeout

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        with remote_observation(
            name="search-web",
            as_type="retriever",
            input={"query": query},
            metadata={"provider": "tavily", "max_results": max_results},
        ) as retrieval:
            try:
                payload = json.dumps(
                    {"api_key": self._api_key, "query": query, "max_results": max_results}
                ).encode("utf-8")
                request = Request(
                    "https://api.tavily.com/search",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=self._timeout) as raw_response:  # noqa: S310
                    response = json.loads(raw_response.read().decode("utf-8"))
                documents = [
                    SourceDocument(
                        title=result.get("title", ""),
                        url=result.get("url"),
                        snippet=result.get("content", ""),
                    )
                    for result in response.get("results", [])
                ]
                if retrieval is not None:
                    retrieval.update(
                        output=[
                            {"title": document.title, "url": document.url} for document in documents
                        ],
                        metadata={
                            "provider": "tavily",
                            "max_results": max_results,
                            "result_count": len(documents),
                        },
                    )
                return documents
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                if retrieval is not None:
                    retrieval.update(level="ERROR", status_message=type(exc).__name__)
                raise AgentExecutionError(f"Search failed: {exc}") from exc
