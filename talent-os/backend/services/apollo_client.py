"""
Talent OS — Apollo.io API wrapper.
Uses Apollo's REST API for candidate search, email enrichment, and intent data.
Docs: https://apollo.io/api/docs
"""
import httpx
from typing import Optional, List, Dict, Any


class ApolloClient:
    """Async Apollo.io API client with rate-limit awareness."""

    BASE_URL = "https://api.apollo.io/api/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                },
                timeout=30.0,
            )
        return self._client

    async def search_people(
        self,
        q: str = "",
        title: str = "",
        location: str = "",
        company: str = "",
        limit: int = 25,
        page: int = 1,
    ) -> Dict[str, Any]:
        """
        Search Apollo.io's people database.
        POST /api/v1/mixed_people/search
        """
        client = await self._get_client()
        payload = {
            "api_key": self.api_key,
            "q_organization": company,
            "q_keywords": q,
            "person_titles": [title] if title else [],
            "person_locations": [location] if location else [],
            "per_page": min(limit, 100),
            "page": page,
        }
        # Remove empty fields
        payload = {k: v for k, v in payload.items() if v}

        resp = await client.post("/mixed_people/search", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def enrich_person(self, linkedin_url: str) -> Dict[str, Any]:
        """
        Enrich a LinkedIn URL to verified email and full profile.
        POST /api/v1/people/match
        """
        client = await self._get_client()
        payload = {
            "api_key": self.api_key,
            "reveal_personal_emails": True,
            "reveal_phone": False,
        }

        # Support both full URL and just the LinkedIn ID
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url

        resp = await client.post("/people/match", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_intent_data(
        self,
        industry: str = "",
        location: str = "",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Get hiring intent data — which companies are actively hiring.
        POST /api/v1/intent_keywords
        """
        client = await self._get_client()
        payload = {
            "api_key": self.api_key,
            "per_page": limit,
        }
        if industry:
            payload["industry"] = industry
        if location:
            payload["location"] = location

        resp = await client.post("/intent_keywords", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None