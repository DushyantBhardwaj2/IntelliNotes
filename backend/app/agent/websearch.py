from app.agent.state import AgentState, append_trace
from app.config import settings


def web_search_node(state: AgentState) -> dict:
    question = state["question"]
    results: list[dict] = []
    error = None

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(question, max_results=3)
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            }
            for item in response.get("results", [])
        ]
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, never crash the graph
        error = str(exc)

    detail = f"{len(results)} web result(s) via Tavily"
    if error:
        detail += f" (search failed: {error})"

    return {
        "web_results": results,
        "trace": append_trace(
            state,
            {
                "step": "web_search",
                "detail": detail,
                "sources": [
                    {"title": result["title"], "url": result["url"]}
                    for result in results
                ],
            },
        ),
    }
