"""Embedding generation service."""

from typing import List, Optional
import httpx
import numpy as np

from app.config import settings


class EmbeddingService:
    """Generate embeddings for text chunks."""

    def __init__(self):
        self.model = settings.embedding_model
        self.dimension = 1536  # text-embedding-3-small dimension

    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = await self._embed_batch_internal(batch)
            embeddings.extend(batch_embeddings)

        return embeddings

    async def embed_single(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        embeddings = await self._embed_batch_internal([text])
        return embeddings[0] if embeddings else self._zero_vector()

    async def get_embedding(self, text: str) -> List[float]:
        """Alias for embed_single for compatibility."""
        return await self.embed_single(text)

    async def _embed_batch_internal(self, texts: List[str]) -> List[List[float]]:
        """Internal batch embedding using OpenAI API."""
        # Clean texts
        texts = [self._prepare_text(t) for t in texts]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._get_openai_key()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": texts,
                        "model": self.model,
                    },
                    timeout=60.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    # Sort by index to maintain order
                    embeddings_data = sorted(data["data"], key=lambda x: x["index"])
                    return [e["embedding"] for e in embeddings_data]
                else:
                    print(f"Embedding API error: {response.status_code} - {response.text}")
                    return [self._zero_vector() for _ in texts]

        except Exception as e:
            print(f"Embedding generation failed: {str(e)}")
            return [self._zero_vector() for _ in texts]

    def _prepare_text(self, text: str) -> str:
        """Prepare text for embedding."""
        # Truncate to avoid token limits
        max_chars = 8000  # Approximate limit for embedding models
        if len(text) > max_chars:
            text = text[:max_chars]

        # Clean whitespace
        text = ' '.join(text.split())

        return text

    def _zero_vector(self) -> List[float]:
        """Return a zero vector for failed embeddings."""
        return [0.0] * self.dimension

    def _get_openai_key(self) -> str:
        """Get OpenAI API key from settings."""
        return settings.openai_api_key

    def cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """Calculate cosine similarity between two embeddings."""
        a = np.array(embedding1)
        b = np.array(embedding2)

        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0

        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
