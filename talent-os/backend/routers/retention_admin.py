"""
Talent OS — WS-E.8 retention/purge admin endpoints (JWT-protected,
role='admin').

Two independent tools, both dry-run by default and never triggered by
anything other than an explicit admin request or the RETENTION_PURGE_ENABLED
daily cron (services/scheduler.py):

  1. POST /api/v1/admin/retention/run — the bewaartabel purge
     (core/retention.py). dry_run=true (default) returns counts only, no
     DB writes. dry_run=false additionally requires confirm="PURGE".
  2. POST /api/v1/admin/apollo-pool/purge — the separate, one-off Apollo
     bulk-pool cleanup (VERWERKINGSREGISTER.md §2.6, §5.7). dry_run=true
     (default) returns counts only. dry_run=false additionally requires
     confirm="DELETE APOLLO POOL".

Neither endpoint runs automatically. This PR never deletes production
data by itself — see the module docstrings on core/retention.py and
services/scheduler.py for the daily job's own dry-run default.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import fetch_all, execute
from core.deps import require_role
from core import retention
from services import scheduler as scheduler_service

logger = logging.getLogger("talent_os.retention_admin")

router = APIRouter(prefix="/api/v1/admin/retention", tags=["retention-admin"])
apollo_pool_router = APIRouter(prefix="/api/v1/admin/apollo-pool", tags=["retention-admin"])


class RetentionRunRequest(BaseModel):
    dry_run: bool = True
    confirm: Optional[str] = None


@router.get("/table")
async def get_retention_table(current_user: dict = Depends(require_role("admin"))):
    """The bewaartabel as both structured rows and the exact Markdown the
    register/SOP carry (docs/VERWERKINGSREGISTER.md §1.4, docs/SOURCING-SOP.md
    §6) — for admins verifying the two stay in sync, not just tests."""
    return {
        "markdown": retention.render_markdown(),
        "rows": [
            {
                "key": r.key,
                "categorie": r.categorie,
                "bewaartermijn": r.bewaartermijn,
                "bron_opmerking": r.bron_opmerking,
                "legal_basis_ref": r.legal_basis_ref,
                "anchor_column": r.anchor_column,
                "action": r.action,
                "schema_ready": r.schema_ready,
            }
            for r in retention.RETENTION_TABLE
        ],
    }


@router.post("/run")
async def run_retention(
    payload: RetentionRunRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """dry_run=true (default): counts per category, no DB writes at all.
    dry_run=false: requires confirm="PURGE" and actually anonymises/deletes
    per core/retention.py's table, writing one audit_log row per purged
    category (services/scheduler.py run_retention_purge)."""
    if not payload.dry_run and payload.confirm != "PURGE":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "retention_purge_requires_confirm",
                "message": 'dry_run=false requires confirm: "PURGE".',
            },
        )
    result = await scheduler_service.run_retention_purge(dry_run=payload.dry_run)
    if not payload.dry_run:
        logger.warning(
            "Retention purge run by admin user_id=%s: %s",
            current_user["id"], {c["key"]: c["count"] for c in result["categories"]},
        )
    return result


# ── Apollo bulk-pool purge (VERWERKINGSREGISTER.md §2.6, §5.7) ───────────


class ApolloPoolPurgeRequest(BaseModel):
    dry_run: bool = True
    confirm: Optional[str] = None


APOLLO_POOL_CONFIRM = "DELETE APOLLO POOL"

# Rows without an http(s) source_url never passed the LIA (§2.6) — those
# are the only ones this endpoint ever touches. A row that later gained a
# real public source_url (the owner's other option besides wiping the
# pool, §5.7) is left alone entirely by this endpoint.
_TARGET_ROWS_SQL = """
    SELECT id, email FROM candidates
    WHERE pool_origin = 'apollo'
      AND deleted_at IS NULL
      AND (source_url IS NULL OR source_url !~* '^https?://')
"""


@apollo_pool_router.post("/purge")
async def purge_apollo_pool(
    payload: ApolloPoolPurgeRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """The Apollo-pool wipe/keep decision itself belongs to the owner
    (VERWERKINGSREGISTER.md §2.6) — this endpoint is the tooling, never
    run automatically, and dry_run=true by default.

    Choice of anonymise vs. hard-delete, per row:
      - Has an e-mail address: anonymise via the same erase_person()
        routine as a manual Art. 17 request (routers/gdpr.py) — this
        preserves any matches/pipeline_entries FK history (candidates.id
        survives, PII doesn't) and adds the person to suppression_list so
        a future Apollo re-sync (should the owner ever re-enable it)
        can't re-source the same person. Preferred whenever it's possible,
        since it keeps the suppression guarantee.
      - No e-mail address at all: hard DELETE. suppression_list is keyed
        on email_hash, so a row with no e-mail can't be suppressed either
        way, and (per WS-E.7's erase_person) these bulk-harvested rows
        never had a portal account or an application tied to them —
        nothing else references the row, so there is nothing an
        anonymise-in-place step would preserve that a DELETE doesn't
        already achieve equally safely.
    """
    if not payload.dry_run and payload.confirm != APOLLO_POOL_CONFIRM:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "apollo_pool_purge_requires_confirm",
                "message": f'dry_run=false requires confirm: "{APOLLO_POOL_CONFIRM}".',
            },
        )

    rows = await fetch_all(_TARGET_ROWS_SQL)
    with_email = [r for r in rows if r["email"]]
    without_email = [r for r in rows if not r["email"]]

    if payload.dry_run:
        return {
            "dry_run": True,
            "total": len(rows),
            "would_anonymise": len(with_email),
            "would_hard_delete": len(without_email),
        }

    from routers.gdpr import erase_person

    anonymised = 0
    for row in with_email:
        await erase_person(row["email"], actor_id=current_user["id"], reason="apollo_pool_purge")
        anonymised += 1

    deleted = 0
    if without_email:
        ids = [r["id"] for r in without_email]
        await execute("DELETE FROM candidates WHERE id = ANY($1::int[])", ids)
        deleted = len(ids)

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, NULL, $4::jsonb)",
        "apollo_pool_purge", current_user["id"], "candidates_pool",
        json.dumps({"anonymised": anonymised, "hard_deleted": deleted, "total": len(rows)}),
    )
    logger.warning(
        "Apollo pool purge run by admin user_id=%s: anonymised=%s hard_deleted=%s",
        current_user["id"], anonymised, deleted,
    )
    return {"dry_run": False, "total": len(rows), "anonymised": anonymised, "hard_deleted": deleted}
