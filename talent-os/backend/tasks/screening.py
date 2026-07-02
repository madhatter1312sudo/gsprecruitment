"""
Talent OS — Celery tasks for screening: semantic matching via OpenRouter.
"""
from tasks.celery_app import celery_app
from services.matcher import EmbeddingMatcher
from core.database import get_pool, fetch_one
import asyncio


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def run_semantic_matching(self, job_id: int):
    """
    Run semantic matching for a specific job against all sourced candidates.
    Uses OpenRouter embedding API (no local models on VPS).
    """
    async def _run():
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Get the job
            job = await conn.fetchrow(
                "SELECT * FROM job_orders WHERE id = $1", job_id
            )
            if not job:
                return {"status": "error", "reason": "Job not found"}

            # Get all sourced candidates
            candidates = await conn.fetch(
                "SELECT * FROM candidates WHERE status = 'sourced' ORDER BY created_at DESC LIMIT 200"
            )

        if not candidates:
            return {"status": "ok", "job_id": job_id, "matched": 0, "note": "No sourced candidates"}

        job_text = f"{job['title']}: {job['description'] or ''} {job['requirements'] or ''}"
        cand_dicts = [dict(c) for c in candidates]

        matcher = EmbeddingMatcher()
        try:
            results = await matcher.match_job_to_candidates(job_text, cand_dicts, min_score=0.3)

            inserted = 0
            for r in results:
                await fetch_one(
                    """INSERT INTO matches (job_id, candidate_id, match_score, matched_by_agent, status)
                       VALUES ($1, $2, $3, $4, 'pending')
                       ON CONFLICT (job_id, candidate_id) DO UPDATE SET match_score = $3
                       RETURNING id""",
                    job_id, r["candidate_id"], r["match_score"],
                    "celery-semantic-matcher",
                )
                inserted += 1

            return {
                "status": "ok",
                "job_id": job_id,
                "candidates_processed": len(candidates),
                "matches_created": inserted,
            }
        finally:
            await matcher.close()

    try:
        return _run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)