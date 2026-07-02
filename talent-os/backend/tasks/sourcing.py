"""
Talent OS — Celery tasks for Apollo.io sourcing (background, non-blocking).
"""
from tasks.celery_app import celery_app
from services.apollo_client import ApolloClient
from core.database import get_pool, fetch_one
from core.config import settings
import asyncio


def _run_async(coro):
    """Run an async function in the sync Celery worker context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def apollo_search_and_sync(self, title: str = "", location: str = "", limit: int = 25):
    """
    Search Apollo.io for candidates matching criteria, then insert into PostgreSQL.
    Run daily via celery beat.
    """
    if not settings.apollo_api_key:
        return {"status": "skipped", "reason": "Apollo API key not configured"}

    async def _run():
        client = ApolloClient(api_key=settings.apollo_api_key)
        try:
            result = await client.search_people(title=title, location=location, limit=limit)
            people = result.get("people", []) or result.get("data", []) or []
            inserted = 0
            for person in people:
                # Map Apollo fields to our schema
                name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
                email = person.get("email", person.get("personal_email", ""))
                company = ""
                if person.get("employment_history"):
                    company = person["employment_history"][0].get("company_name", "")

                if not name or not email:
                    continue

                # Check for duplicate email before inserting
                existing = await fetch_one(
                    "SELECT id FROM candidates WHERE email = $1", email
                )
                if existing:
                    continue

                await fetch_one(
                    """INSERT INTO candidates
                       (full_name, email, current_company, current_title, location,
                        skills, source, sourced_by_agent, is_passive)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                       RETURNING id""",
                    name, email, company,
                    person.get("title", ""), person.get("city", person.get("location", "")),
                    [s.get("name", "") for s in person.get("skills", [])],
                    "apollo", "celery-apollo-sync", True,
                )
                inserted += 1

            return {"status": "success", "searched": len(people), "inserted": inserted}
        finally:
            await client.close()

    try:
        return _run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3)
def apollo_enrich_batch(self):
    """
    Batch enrich candidates that have LinkedIn URLs but no verified emails.
    Run daily via celery beat.
    """
    if not settings.apollo_api_key:
        return {"status": "skipped", "reason": "Apollo API key not configured"}

    async def _run():
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, linkedin_url FROM candidates WHERE email IS NULL AND linkedin_url IS NOT NULL LIMIT 50"
            )

        client = ApolloClient(api_key=settings.apollo_api_key)
        enriched = 0
        try:
            for row in rows:
                try:
                    result = await client.enrich_person(linkedin_url=row["linkedin_url"])
                    person = result.get("person", result.get("data", {}))
                    email = person.get("email", person.get("personal_email", ""))
                    if email:
                        await fetch_one(
                            "UPDATE candidates SET email = $1, updated_at = NOW() WHERE id = $2",
                            email, row["id"],
                        )
                        enriched += 1
                except Exception:
                    continue
            return {"status": "success", "processed": len(rows), "enriched": enriched}
        finally:
            await client.close()

    try:
        return _run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)