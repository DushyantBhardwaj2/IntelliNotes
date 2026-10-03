from functools import lru_cache
from typing import TypeVar

from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings

T = TypeVar("T")


@lru_cache
def get_chat_model() -> ChatGoogleGenerativeAI:
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your Gemini key."
        )
    return ChatGoogleGenerativeAI(
        model=settings.chat_model,
        api_key=settings.google_api_key,
    )


def chat(messages, schema: type[T] | None = None) -> T | AIMessage:
    """Invoke the chat model with automatic retry on transient errors (e.g. 429s).

    Pass a Pydantic model as `schema` to get a structured, validated response.
    """
    model = get_chat_model()
    runnable = model.with_structured_output(schema) if schema is not None else model
    return runnable.with_retry(
        stop_after_attempt=4,
        exponential_jitter_params={"initial": 4, "max": 60},
    ).invoke(messages)


def to_text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content)
