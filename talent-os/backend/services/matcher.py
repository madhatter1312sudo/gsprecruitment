"""
Talent OS — Semantic Candidate-Job Matcher using OpenRouter Embeddings API.
NO local models on VPS. All embedding calls go through OpenRouter.
"""
import httpx
from typing import List, Dict, Any, Optional
from core.config import settings


class EmbeddingMatcher:
    """
    Matches candidates to jobs using OpenRouter's embedding API.
    Uses text-embedding-3-small via OpenRouter (no local models on VPS).
    """

    EMBEDDING_MODEL = "openai/text-embedding-3-small"
    EMBEDDING_DIMS = 512  # text-embedding-3-small supports dimensions truncation

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.openrouter_base_url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts using OpenRouter's embedding endpoint.
        Returns list of embedding vectors.
        """
        client = await self._get_client()
        payload = {
            "model": self.EMBEDDING_MODEL,
            "input": texts,
        }
        resp = await client.post("/embeddings", json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Sort by index to preserve order
        embeddings = [None] * len(texts)
        for item in data.get("data", []):
            embeddings[item["index"]] = item["embedding"]
        return embeddings

    async def match_job_to_candidates(
        self,
        job_text: str,
        candidates: List[Dict[str, Any]],
        min_score: float = 0.3,
        top_k: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Match a job description against a list of candidates using cosine similarity
        on OpenRouter embeddings.
        """
        if not candidates:
            return []

        # Build candidate texts
        cand_texts = []
        for c in candidates:
            # DB NULLs come through as None — never assume the defaults kick in
            title = c.get("current_title") or ""
            cv = (c.get("cv_text") or "")[:500]
            skills = " ".join(c.get("skills") or [])
            cand_texts.append(f"{title} {cv} {skills}")

        # Embed in batches — the embeddings endpoint caps input arrays
        # (~2048 items) and 5k+ candidates in one request 4xx's.
        BATCH = 500
        job_batch = await self.embed([job_text])
        if not job_batch or job_batch[0] is None:
            return []
        job_emb = job_batch[0]

        cand_embs: List[Any] = []
        for start in range(0, len(cand_texts), BATCH):
            chunk = await self.embed(cand_texts[start:start + BATCH])
            if not chunk:
                # keep index alignment with candidates on partial failure
                cand_embs.extend([None] * len(cand_texts[start:start + BATCH]))
            else:
                cand_embs.extend(chunk)

        import math

        def cosine_sim(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        results = []
        for i, c in enumerate(candidates):
            if i >= len(cand_embs) or cand_embs[i] is None:
                continue
            score = cosine_sim(job_emb, cand_embs[i])
            if score >= min_score:
                results.append({
                    "candidate_id": c.get("id"),
                    "name": c.get("full_name", c.get("name", "")),
                    "match_score": round(score * 100, 2),
                    "skills": c.get("skills", []),
                })

        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results[:top_k]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None