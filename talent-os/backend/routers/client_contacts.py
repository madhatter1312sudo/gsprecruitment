"""
Talent OS — Client Contacts (WS-C.4).

Admin CRUD over `client_contacts` (migrations/024_client_contacts.py) --
the named hiring_manager/finance/tekenbevoegd/overig people at a client
company, independent of whether they ever get a portal login (that's
`user_clients`/`routers/client.py`'s team-invite flow, a different thing).

Two routers:
  - `router` (admin, Bearer JWT): full CRUD under
    /api/v1/admin/clients/{client_id}/contacts.
  - `client_router` (client portal, Bearer JWT, role='client'/'admin'):
    read-only, scoped to the calling client's own contacts only --
    GET /api/v1/client/contacts.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.database import fetch_one, fetch_all, execute
from core.deps import require_role, require_verified_role
from models.schemas import ClientContactCreate, ClientContactUpdate

logger = logging.getLogger("talent_os.client_contacts")

router = APIRouter(prefix="/api/v1/admin/clients", tags=["client-contacts-admin"])
client_router = APIRouter(prefix="/api/v1/client", tags=["client-contacts-portal"])


async def _get_client_or_404(client_id: int) -> dict:
    client = await fetch_one(
        "SELECT id FROM clients WHERE id = $1 AND deleted_at IS NULL",
        client_id,
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


async def _audit(action: str, actor_id: int, target_id: int, changes: dict) -> None:
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        action, actor_id, "client_contact", target_id, json.dumps(changes),
    )


# ── Admin CRUD ────────────────────────────────────────────────────────────

@router.get("/{client_id}/contacts")
async def list_client_contacts(
    client_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """List a client's contacts (excludes soft-deleted rows)."""
    await _get_client_or_404(client_id)
    rows = await fetch_all(
        """SELECT * FROM client_contacts
           WHERE client_id = $1 AND deleted_at IS NULL
           ORDER BY is_primary DESC, created_at""",
        client_id,
    )
    return {"items": rows, "total": len(rows)}


@router.post("/{client_id}/contacts", status_code=201)
async def create_client_contact(
    client_id: int,
    payload: ClientContactCreate,
    current_user: dict = Depends(require_role("admin")),
):
    await _get_client_or_404(client_id)

    if payload.is_primary:
        await _demote_other_primaries(client_id, exclude_contact_id=None)

    row = await fetch_one(
        """INSERT INTO client_contacts
           (client_id, full_name, email, phone, role, is_primary, lawful_basis)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING *""",
        client_id, payload.full_name, payload.email, payload.phone,
        payload.role, payload.is_primary, payload.lawful_basis,
    )

    await _audit("client_contact_create", current_user["id"], row["id"], payload.model_dump())
    return row


@router.put("/{client_id}/contacts/{contact_id}")
async def update_client_contact(
    client_id: int,
    contact_id: int,
    updates: ClientContactUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    await _get_client_or_404(client_id)

    existing = await fetch_one(
        "SELECT id FROM client_contacts WHERE id = $1 AND client_id = $2 AND deleted_at IS NULL",
        contact_id, client_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")

    update_dict = updates.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    if update_dict.get("is_primary") is True:
        await _demote_other_primaries(client_id, exclude_contact_id=contact_id)

    set_parts = []
    values = []
    idx = 1
    for key, val in update_dict.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_parts.append("updated_at = NOW()")

    values.extend([contact_id, client_id])
    row = await fetch_one(
        f"""UPDATE client_contacts SET {', '.join(set_parts)}
            WHERE id = ${idx} AND client_id = ${idx + 1} AND deleted_at IS NULL
            RETURNING *""",
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    await _audit("client_contact_update", current_user["id"], contact_id, update_dict)
    return row


@router.delete("/{client_id}/contacts/{contact_id}", status_code=204)
async def delete_client_contact(
    client_id: int,
    contact_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Soft delete -- sets deleted_at, never a real DELETE (GDPR
    provenance/audit-trail reasons match the rest of this codebase)."""
    row = await fetch_one(
        """UPDATE client_contacts SET deleted_at = NOW(), updated_at = NOW()
           WHERE id = $1 AND client_id = $2 AND deleted_at IS NULL
           RETURNING id""",
        contact_id, client_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    await _audit("client_contact_delete", current_user["id"], contact_id, {})
    return None


async def _demote_other_primaries(client_id: int, exclude_contact_id: Optional[int]) -> None:
    """No unique index enforces "one primary per client" at the DB level
    (WS-C.4 spec: no unique indexes that could abort on existing data) --
    this is the API-layer equivalent, run before a contact is set primary."""
    if exclude_contact_id is None:
        await execute(
            "UPDATE client_contacts SET is_primary = false, updated_at = NOW() "
            "WHERE client_id = $1 AND is_primary = true AND deleted_at IS NULL",
            client_id,
        )
    else:
        await execute(
            "UPDATE client_contacts SET is_primary = false, updated_at = NOW() "
            "WHERE client_id = $1 AND id != $2 AND is_primary = true AND deleted_at IS NULL",
            client_id, exclude_contact_id,
        )


# ── Client portal: read own contacts only ─────────────────────────────────

@client_router.get("/contacts")
async def list_own_client_contacts(
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """A client sees only its own contacts -- client_id is resolved from
    the caller's own user_clients row, never taken from the request."""
    client = await fetch_one(
        "SELECT c.id FROM clients c JOIN user_clients uc ON uc.client_id = c.id "
        "WHERE uc.user_id = $1",
        current_user["id"],
    )
    if not client:
        return {"items": [], "total": 0}

    rows = await fetch_all(
        """SELECT * FROM client_contacts
           WHERE client_id = $1 AND deleted_at IS NULL
           ORDER BY is_primary DESC, created_at""",
        client["id"],
    )
    return {"items": rows, "total": len(rows)}
