import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings


def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content)


def main() -> None:
    print("=" * 52)
    print("IntelliNotes setup verification")
    print("=" * 52)

    problems = []
    if not settings.google_api_key or "your-" in settings.google_api_key:
        problems.append("GOOGLE_API_KEY is missing or still a placeholder in .env")
    if not settings.tavily_api_key or "your-" in settings.tavily_api_key:
        problems.append("TAVILY_API_KEY is missing or still a placeholder in .env")
    if problems:
        for problem in problems:
            print(f"  [FAIL] {problem}")
        sys.exit(1)
    print("[OK] API keys present in .env")

    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

    print(f"Testing Gemini chat model ({settings.chat_model})...")
    chat = ChatGoogleGenerativeAI(model=settings.chat_model, api_key=settings.google_api_key)
    reply = chat.invoke("Reply with exactly one word: OK")
    print(f"  [OK] Gemini replied: {text_of(reply).strip()!r}")

    print(f"Testing Gemini embeddings ({settings.embedding_model})...")
    embeddings = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.google_api_key,
        output_dimensionality=settings.embedding_dimensions,
    )
    vector = embeddings.embed_query("hello world")
    print(f"  [OK] Embedding returned {len(vector)} dimensions")

    print("Testing Tavily web search...")
    from tavily import TavilyClient

    client = TavilyClient(api_key=settings.tavily_api_key)
    result = client.search("what is retrieval augmented generation", max_results=1)
    print(f"  [OK] Tavily returned: {result['results'][0]['title']!r}")

    print()
    print("All checks passed. IntelliNotes is ready to run.")


if __name__ == "__main__":
    main()
