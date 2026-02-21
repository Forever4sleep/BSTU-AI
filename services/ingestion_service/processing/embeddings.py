"""
OpenRouter Embeddings

Direct HTTP client for OpenRouter embeddings API to avoid
OpenAI client compatibility issues with OpenRouter response format.
"""

import logging
from typing import List

import httpx

from services.ingestion_service.config import (
    get_embedding_api_key,
    get_embedding_model,
    get_embedding_base_url,
)

logger = logging.getLogger(__name__)

# Max texts per request (OpenRouter/OpenAI limit)
BATCH_SIZE = 100


class OpenRouterEmbeddings:
    """Embeddings via OpenRouter API (OpenAI-compatible endpoint)."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model or get_embedding_model()
        self.api_key = api_key or get_embedding_api_key()
        self.base_url = (base_url or get_embedding_base_url()).rstrip("/")
        self._url = f"{self.base_url}/embeddings"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts.

        Args:
            texts: List of strings to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a single batch of texts."""
        payload = {
            "model": self.model,
            "input": texts if len(texts) > 1 else texts[0],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(f"Embedding batch of {len(texts)} texts via {self._url}")

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self._url, json=payload, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Embedding API error: status={response.status_code}, body={response.text}"
            )
            raise ValueError(
                f"Embedding API failed: {response.status_code} - {response.text}"
            )

        data = response.json()

        if "data" not in data or not data["data"]:
            logger.error(f"Embedding API returned no data: {data}")
            raise ValueError(
                f"No embedding data received. Response: {data}"
            )

        # Extract embeddings in order (API returns with optional index field)
        items = data["data"]
        if len(items) != len(texts):
            logger.warning(
                f"Expected {len(texts)} embeddings, got {len(items)}"
            )

        embeddings = []
        for item in sorted(items, key=lambda x: x.get("index", 0)):
            if "embedding" not in item:
                raise ValueError(
                    f"No embedding data received. API response: {data}"
                )
            embeddings.append(item["embedding"])

        return embeddings
