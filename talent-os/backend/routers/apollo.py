"""
Talent OS — Apollo.io integration router (auth-protected).
"""
from fastapi import APIRouter, Depends, HTTPException
from core.security import verify_api_key
from services.apollo_client import ApolloClient
from core.config import settings

router = APIRouter(prefix="/api/apollo", tags=["apollo"], dependencies=[Depends(verify_api_key)])


@router.get("/search/candidates")
async def search_candidates(
    q: str = "",
    title: str = "",
    location: str = "",
    company: str = "",
    limit: int = 25,
):
    """Search Apollo.io for candidates matching criteria."""
    if not settings.apollo_api_key:
        raise HTTPException(status_code=400, detail="Apollo.io API key not configured")
    client = ApolloClient(api_key=settings.apollo_api_key)
    result = await client.search_people(
        q=q, title=title, location=location, company=company, limit=min(limit, 100),
    )
    return result


@router.get("/enrich/email")
async def enrich_email(linkedin_url: str = ""):
    """Enrich a LinkedIn URL to get verified email via Apollo.io."""
    if not settings.apollo_api_key:
        raise HTTPException(status_code=400, detail="Apollo.io API key not configured")
    if not linkedin_url:
        raise HTTPException(status_code=400, detail="linkedin_url is required")
    client = ApolloClient(api_key=settings.apollo_api_key)
    result = await client.enrich_person(linkedin_url=linkedin_url)
    return result


@router.get("/intent")
async def get_hiring_intent(industry: str = "", location: str = ""):
    """Get hiring intent data from Apollo.io."""
    if not settings.apollo_api_key:
        raise HTTPException(status_code=400, detail="Apollo.io API key not configured")
    client = ApolloClient(api_key=settings.apollo_api_key)
    result = await client.get_intent_data(industry=industry, location=location)
    return result