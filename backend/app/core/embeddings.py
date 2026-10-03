from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings


@lru_cache
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your Gemini key."
        )
    return GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.google_api_key,
        output_dimensionality=settings.embedding_dimensions,
    )
