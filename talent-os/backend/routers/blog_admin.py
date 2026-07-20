"""
Talent OS — Blog Admin Router (JWT-protected, role='admin').

AI drafts blog posts (services/outreach_ai.draft_blog + services/scheduler.py)
but a human always reviews/edits and explicitly publishes before anything
goes live on the public site. There is no auto-publish path anywhere here.
"""
import json
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import fetch_one, fetch_all, fetch_val, execute
from core.deps import require_role

logger = logging.getLogger("talent_os.blog_admin")

router = APIRouter(prefix="/api/v1/admin/blog", tags=["blog-admin"])

SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class BlogPostCreate(BaseModel):
    slug: str
    title_nl: Optional[str] = None
    title_en: Optional[str] = None
    excerpt_nl: Optional[str] = None
    excerpt_en: Optional[str] = None
    body_nl: Optional[str] = None
    body_en: Optional[str] = None
    tags: Optional[List[str]] = None
    read_time_min: Optional[int] = None


class BlogPostUpdate(BaseModel):
    slug: Optional[str] = None
    title_nl: Optional[str] = None
    title_en: Optional[str] = None
    excerpt_nl: Optional[str] = None
    excerpt_en: Optional[str] = None
    body_nl: Optional[str] = None
    body_en: Optional[str] = None
    tags: Optional[List[str]] = None
    read_time_min: Optional[int] = None


# ── List / Create ────────────────────────────────────────────────────────

@router.get("/")
async def list_blog_posts(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """List all blog posts (any status), optionally filtered by status."""
    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    total = await fetch_val(f"SELECT COUNT(*) FROM blog_posts {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT * FROM blog_posts {where}
            ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {"items": rows, "total": total}


@router.post("/", status_code=201)
async def create_blog_post(
    data: BlogPostCreate,
    current_user: dict = Depends(require_role("admin")),
):
    """Create a new draft blog post."""
    if not SLUG_RE.match(data.slug):
        raise HTTPException(
            status_code=400,
            detail="Invalid slug — must match ^[a-z0-9-]+$",
        )

    existing = await fetch_one("SELECT id FROM blog_posts WHERE slug = $1", data.slug)
    if existing:
        raise HTTPException(status_code=400, detail="A post with this slug already exists")

    row = await fetch_one(
        """INSERT INTO blog_posts
           (slug, title_nl, title_en, excerpt_nl, excerpt_en, body_nl, body_en,
            tags, read_time_min, status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'draft')
           RETURNING *""",
        data.slug, data.title_nl, data.title_en, data.excerpt_nl, data.excerpt_en,
        data.body_nl, data.body_en, data.tags, data.read_time_min,
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create blog post")

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5)",
        "blog_post_created", current_user["id"], "blog_post", row["id"],
        json.dumps({"slug": data.slug}),
    )
    return row


# ── Edit ──────────────────────────────────────────────────────────────────

@router.put("/{post_id}")
async def update_blog_post(
    post_id: int,
    updates: BlogPostUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Edit a blog post's fields."""
    existing = await fetch_one("SELECT * FROM blog_posts WHERE id = $1", post_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Blog post not found")

    update_dict = updates.model_dump(exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "slug" in update_dict and not SLUG_RE.match(update_dict["slug"]):
        raise HTTPException(
            status_code=400,
            detail="Invalid slug — must match ^[a-z0-9-]+$",
        )

    set_parts = []
    values = []
    idx = 1
    for key, val in update_dict.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    values.append(post_id)
    row = await fetch_one(
        f"UPDATE blog_posts SET {', '.join(set_parts)}, updated_at = NOW() "
        f"WHERE id = ${idx} RETURNING *",
        *values,
    )

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5)",
        "blog_post_updated", current_user["id"], "blog_post", post_id, json.dumps(update_dict),
    )
    return row


# ── Publish / Archive ─────────────────────────────────────────────────────

@router.post("/{post_id}/publish")
async def publish_blog_post(
    post_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Publish a blog post — the only path that makes a post visible on the
    public site. Always requires an explicit human action."""
    row = await fetch_one(
        """UPDATE blog_posts SET status = 'published', published_at = NOW(), updated_at = NOW()
           WHERE id = $1 RETURNING *""",
        post_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Blog post not found")

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5)",
        "blog_post_published", current_user["id"], "blog_post", post_id,
        json.dumps({"slug": row["slug"]}),
    )
    return row


@router.post("/{post_id}/archive")
async def archive_blog_post(
    post_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Archive a blog post — removes it from the public listing without
    deleting it."""
    row = await fetch_one(
        "UPDATE blog_posts SET status = 'archived', updated_at = NOW() WHERE id = $1 RETURNING *",
        post_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Blog post not found")

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5)",
        "blog_post_archived", current_user["id"], "blog_post", post_id,
        json.dumps({"slug": row["slug"]}),
    )
    return row
