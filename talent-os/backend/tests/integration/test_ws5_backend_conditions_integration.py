"""
WS5 backendvoorwaarden BV1 t/m BV10 (SITE-DESIGN-SPEC.md §7.7) over een
echte Postgres: de routes zelf, hun autorisatie, hun paginering en het
gedrag van migratie 043 op een tabel die al een afwijkende waarde draagt.
De tekstuele en model-kant staat in tests/test_ws5_backend_conditions.py.

Elk adres dat dit bestand aanmaakt is een verse @example.com (conftest's
unique_email) -- geen echte persoonsgegevens, ook niet in een testrun.
"""
import importlib.util
import os
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "migrations",
)


@pytest.fixture
def make_pipeline_entry(db_run, make_client_user):
    """A pipeline entry plus the client/candidate/job rows it needs.
    Returns the dict the route should later hand back, keyed by id."""
    from core.database import fetch_one

    def _make(*, stage="sourced", consented=False, client_id=None):
        suffix = uuid.uuid4().hex[:10]
        if client_id is None:
            client_id = db_run(
                fetch_one,
                "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
                f"Pipeline Co {suffix}",
            )["id"]
        candidate = db_run(
            fetch_one,
            """INSERT INTO candidates (full_name, email, current_title, source, lawful_basis,
                                       consent_spec_presentation_at)
               VALUES ($1, $2, 'Embedded Engineer', 'manual', 'gerechtvaardigd_belang', $3)
               RETURNING id, full_name""",
            f"Pipeline Person {suffix}", f"pipeline-{suffix}@example.com",
            datetime.now(timezone.utc) if consented else None,
        )
        job = db_run(
            fetch_one,
            "INSERT INTO job_orders (client_id, title, status) VALUES ($1, $2, 'open') RETURNING id",
            client_id, f"Senior Embedded Engineer {suffix}",
        )
        entry = db_run(
            fetch_one,
            """INSERT INTO pipeline_entries (client_id, candidate_id, job_id, stage, updated_at)
               VALUES ($1, $2, $3, $4, NOW()) RETURNING id""",
            client_id, candidate["id"], job["id"], stage,
        )
        return {"entry_id": entry["id"], "client_id": client_id,
                "candidate_id": candidate["id"], "job_id": job["id"],
                "full_name": candidate["full_name"]}
    return _make


@pytest.fixture
def make_placement(db_run, make_pipeline_entry):
    """A placements row plus the candidate/job/client it references."""
    from core.database import fetch_one

    def _make(**overrides):
        base = make_pipeline_entry()
        row = db_run(
            fetch_one,
            """INSERT INTO placements (candidate_id, job_id, client_id, placement_type, start_date, status)
               VALUES ($1, $2, $3, 'werving_selectie', CURRENT_DATE, 'concept') RETURNING id""",
            base["candidate_id"], base["job_id"], base["client_id"],
        )
        return {**base, "placement_id": row["id"]}
    return _make


# ── BV1: GET /api/v1/admin/pipeline ──────────────────────────────────────

def test_bv1_admin_can_list_pipeline_entries_with_a_total(client, make_admin, make_pipeline_entry):
    admin = make_admin()
    made = make_pipeline_entry()

    res = client.get(
        "/api/v1/admin/pipeline", params={"candidate_id": made["candidate_id"]},
        headers=admin["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 1, body
    assert body["limit"] == 50 and body["offset"] == 0
    item = body["items"][0]
    assert item["id"] == made["entry_id"]
    assert item["client_id"] == made["client_id"]
    assert item["job_id"] == made["job_id"]
    assert item["stage"] == "sourced"
    assert item["job_title"]
    assert item["skills"] == [], "a NULL array column must read back as []"


def test_bv1_filters_are_independent_and_combine(client, make_admin, make_pipeline_entry):
    admin = make_admin()
    a = make_pipeline_entry()
    b = make_pipeline_entry()

    by_client = client.get(
        "/api/v1/admin/pipeline", params={"client_id": a["client_id"]}, headers=admin["headers"],
    ).json()
    assert [i["id"] for i in by_client["items"]] == [a["entry_id"]]

    by_job = client.get(
        "/api/v1/admin/pipeline", params={"job_id": b["job_id"]}, headers=admin["headers"],
    ).json()
    assert [i["id"] for i in by_job["items"]] == [b["entry_id"]]

    mismatched = client.get(
        "/api/v1/admin/pipeline",
        params={"client_id": a["client_id"], "job_id": b["job_id"]},
        headers=admin["headers"],
    ).json()
    assert mismatched["items"] == [] and mismatched["total"] == 0


def test_bv1_stage_filter_matches_the_client_route(client, make_admin, make_pipeline_entry):
    """code-review F3: the client route has had a stage filter all along;
    the admin twin now takes the same one."""
    admin = make_admin()
    screening = make_pipeline_entry(stage="screening")
    make_pipeline_entry(stage="offer", client_id=screening["client_id"])

    hit = client.get(
        "/api/v1/admin/pipeline",
        params={"client_id": screening["client_id"], "stage": "screening"},
        headers=admin["headers"],
    ).json()
    assert [i["id"] for i in hit["items"]] == [screening["entry_id"]]
    assert hit["total"] == 1

    miss = client.get(
        "/api/v1/admin/pipeline",
        params={"client_id": screening["client_id"], "stage": "placed"},
        headers=admin["headers"],
    ).json()
    assert miss["items"] == [] and miss["total"] == 0


def test_bv1_unfiltered_call_pages_and_reports_the_full_total(client, make_admin, make_pipeline_entry):
    admin = make_admin()
    for _ in range(3):
        make_pipeline_entry()

    page = client.get("/api/v1/admin/pipeline", params={"limit": 1}, headers=admin["headers"]).json()
    assert len(page["items"]) == 1
    assert page["total"] >= 3, "total must count the whole set, not the page"


def test_bv1_admin_always_sees_the_name(client, db_run, make_admin, make_pipeline_entry):
    """Chief-of-staff product decision on BV1: the presentation-consent
    gate is a disclosure control aimed at the client, not an internal
    access control, so the admin pipeline list returns `full_name` in all
    three consent states. The same admin token already reads the name
    unconditionally from GET /api/v1/admin/candidates."""
    from core.database import execute

    admin = make_admin()

    no_consent = make_pipeline_entry(consented=False)
    consented = make_pipeline_entry(consented=True)
    withdrawn = make_pipeline_entry(consented=True)
    db_run(
        execute, "UPDATE candidates SET consent_withdrawn_at = NOW() WHERE id = $1",
        withdrawn["candidate_id"],
    )

    for made in (no_consent, consented, withdrawn):
        item = client.get(
            "/api/v1/admin/pipeline", params={"candidate_id": made["candidate_id"]},
            headers=admin["headers"],
        ).json()["items"][0]
        assert item["full_name"] == made["full_name"], made
        # The internal consent columns still never leave the endpoint.
        assert "consent_spec_presentation_at" not in item
        assert "consent_withdrawn_at" not in item


def test_client_pipeline_still_withholds_the_name_without_consent(
    client, db_run, make_client_user, make_pipeline_entry,
):
    """The other half of the same decision: the gate stays ON for the
    client portal, and this route is the one it was always for. Sits next
    to the admin test above so a future change cannot relax one without
    the other going red."""
    from core.database import execute

    client_user = make_client_user(approved=True)
    made = make_pipeline_entry(consented=False, client_id=client_user["client_id"])

    item = client.get("/api/v1/client/pipeline", headers=client_user["headers"]).json()["items"][0]
    assert "full_name" not in item, item
    assert "consent_spec_presentation_at" not in item
    assert "consent_withdrawn_at" not in item

    db_run(
        execute, "UPDATE candidates SET consent_spec_presentation_at = NOW() WHERE id = $1",
        made["candidate_id"],
    )
    named = client.get("/api/v1/client/pipeline", headers=client_user["headers"]).json()["items"][0]
    assert named["full_name"] == made["full_name"]

    # And a later withdrawal takes it away again.
    db_run(
        execute, "UPDATE candidates SET consent_withdrawn_at = NOW() WHERE id = $1",
        made["candidate_id"],
    )
    withdrawn = client.get("/api/v1/client/pipeline", headers=client_user["headers"]).json()["items"][0]
    assert "full_name" not in withdrawn, withdrawn


def test_bv1_a_client_jwt_is_refused(client, make_client_user, make_pipeline_entry):
    """The route exists because the client-scoped one is unusable for an
    admin -- it must not become usable in the other direction."""
    client_user = make_client_user(approved=True)
    made = make_pipeline_entry(client_id=client_user["client_id"])

    res = client.get(
        "/api/v1/admin/pipeline", params={"client_id": made["client_id"]},
        headers=client_user["headers"],
    )
    assert res.status_code == 403, res.text


def test_bv1_a_candidate_jwt_is_refused(client, make_candidate_user):
    candidate_user = make_candidate_user()
    res = client.get("/api/v1/admin/pipeline", headers=candidate_user["headers"])
    assert res.status_code == 403, res.text


def test_bv1_without_a_token_is_refused(client):
    res = client.get("/api/v1/admin/pipeline")
    assert res.status_code in (401, 403), res.text


# ── BV2: lockout fields on the user routes ───────────────────────────────

def test_bv2_user_list_and_detail_carry_the_lockout_fields(client, db_run, make_admin, insert_raw_user):
    from core.database import execute

    admin = make_admin()
    target = insert_raw_user("candidate")
    db_run(
        execute,
        "UPDATE users SET failed_login_count = 7, locked_until = NOW() + INTERVAL '15 minutes' WHERE id = $1",
        target["id"],
    )

    detail = client.get(f"/api/v1/admin/users/{target['id']}", headers=admin["headers"]).json()
    assert detail["failed_login_count"] == 7
    assert detail["locked_until"] is not None
    # Nothing that used to be there disappeared.
    for key in ("id", "email", "full_name", "role", "is_verified", "created_at"):
        assert key in detail

    listing = client.get(
        "/api/v1/admin/users", params={"search": target["email"]}, headers=admin["headers"],
    ).json()
    row = next(r for r in listing["items"] if r["id"] == target["id"])
    assert row["failed_login_count"] == 7
    assert row["locked_until"] is not None


# ── BV3: structured 409 detail on the referral route ─────────────────────

def test_bv3_suppressed_address_returns_a_code(client, db_run, make_admin, make_email):
    from core import privacy
    from core.database import execute

    admin = make_admin()
    email = make_email("ws5-referral-suppressed")
    db_run(
        execute,
        "INSERT INTO suppression_list (email_hash, email_domain, reason) VALUES ($1, $2, 'test') "
        "ON CONFLICT (email_hash) DO NOTHING",
        privacy.email_hash(email), privacy.email_domain(email),
    )

    res = client.post(
        "/api/v1/admin/candidates/referral",
        json={"full_name": "Geblokkeerd", "email": email, "referred_by": "Piet",
              "evidence": "mondeling bevestigd"},
        headers=admin["headers"],
    )
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["code"] == "referral_email_suppressed"


def test_bv3_existing_candidate_returns_a_code_and_the_id(client, db_run, make_admin, make_email):
    from core.database import fetch_one

    admin = make_admin()
    email = make_email("ws5-referral-existing")
    existing = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, source, lawful_basis)
           VALUES ('Bestaand', $1, 'portal_registration', 'portal_registratie') RETURNING id""",
        email,
    )

    res = client.post(
        "/api/v1/admin/candidates/referral",
        json={"full_name": "Referral", "email": email, "referred_by": "Piet",
              "evidence": "mondeling bevestigd"},
        headers=admin["headers"],
    )
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "referral_candidate_exists"
    assert detail["candidate_id"] == existing["id"], "the panel opens the candidate from this id"


# ── BV4: consent fields on the candidate portal profile ──────────────────

def test_bv4_profile_reports_withdrawal_and_lawful_basis(client, db_run, make_candidate_user):
    from core.database import execute, fetch_one

    user = make_candidate_user()
    db_run(execute, "INSERT INTO candidate_profiles (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user["id"])
    candidate = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, source, lawful_basis, consent_withdrawn_at)
           VALUES ('WS5 Kandidaat', $1, 'manual', 'opt_in_talentpool', NOW()) RETURNING id""",
        user["email"],
    )
    db_run(
        execute, "UPDATE candidate_profiles SET candidate_id = $1 WHERE user_id = $2",
        candidate["id"], user["id"],
    )

    body = client.get("/api/v1/candidate/profile", headers=user["headers"]).json()
    assert body["consent_withdrawn_at"] is not None
    assert body["lawful_basis"] == "opt_in_talentpool"
    # The four WS-C.17 fields still answer.
    assert "consent_talentpool_at" in body and "consent_source" in body


def test_bv4_profile_without_a_candidates_row_reports_none(client, db_run, make_candidate_user):
    from core.database import execute

    user = make_candidate_user(verified=True)
    db_run(execute, "INSERT INTO candidate_profiles (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user["id"])

    body = client.get("/api/v1/candidate/profile", headers=user["headers"]).json()
    assert body["consent_withdrawn_at"] is None
    assert body["lawful_basis"] in (None, "portal_registratie")


# ── BV5: total on the suppression list ───────────────────────────────────

def test_bv5_suppression_list_reports_a_total_beyond_the_page(client, db_run, make_admin, make_email):
    from core import privacy
    from core.database import execute

    admin = make_admin()
    for i in range(3):
        email = make_email(f"ws5-suppression-{i}")
        db_run(
            execute,
            "INSERT INTO suppression_list (email_hash, email_domain, reason) VALUES ($1, $2, 'STOP') "
            "ON CONFLICT (email_hash) DO NOTHING",
            privacy.email_hash(email), privacy.email_domain(email),
        )

    body = client.get("/api/v1/admin/suppression", params={"limit": 1}, headers=admin["headers"]).json()
    assert len(body["items"]) == 1
    assert body["total"] >= 3
    assert body["limit"] == 1 and body["offset"] == 0
    # Still no plaintext address anywhere in the payload.
    assert set(body["items"][0]) == {"id", "email_hash", "email_domain", "reason", "created_at"}


# ── BV6: paging on the retention review list ─────────────────────────────

@pytest.fixture
def review_items(db_run):
    from core.database import execute

    def _make(count=3):
        suffix = uuid.uuid4().hex[:8]
        # A fresh subject_id block per call: the table has a UNIQUE
        # (category, subject_table, subject_id) and this suite runs
        # repeatedly against the same database.
        subject_base = 900000 + (uuid.uuid4().int % 90000) * 10
        for i in range(count):
            db_run(
                execute,
                """INSERT INTO retention_review_items
                     (category, subject_table, subject_id, email, action, term_expired_at, status)
                   VALUES ('leads_quiz', 'quiz_submissions', $1, $2, 'hard_delete',
                           NOW() - ($3 || ' days')::interval, 'pending')
                   ON CONFLICT (category, subject_table, subject_id) DO NOTHING""",
                subject_base + i, f"ws5-review-{suffix}-{i}@example.com", str(i + 1),
            )
        return suffix
    return _make


def test_bv6_default_call_still_returns_the_whole_set(client, make_admin, review_items):
    admin = make_admin()
    review_items(3)

    body = client.get("/api/v1/admin/retention/review", headers=admin["headers"]).json()
    assert body["limit"] is None, "no default page size -- the bulk flow's expected_count depends on it"
    assert body["total"] == len(body["items"]), "unpaged, so total and page length agree"
    assert body["total"] >= 3


def test_bv6_limit_and_offset_page_within_a_stable_total(client, make_admin, review_items):
    admin = make_admin()
    review_items(3)

    first = client.get(
        "/api/v1/admin/retention/review", params={"limit": 2, "offset": 0}, headers=admin["headers"],
    ).json()
    second = client.get(
        "/api/v1/admin/retention/review", params={"limit": 2, "offset": 2}, headers=admin["headers"],
    ).json()

    assert len(first["items"]) == 2
    assert first["total"] == second["total"], "total is the filtered set, not the page"
    assert first["total"] > 2
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})


# ── BV7: a readable actor on the stage history ───────────────────────────

def test_bv7_history_names_the_actor(client, make_admin, make_pipeline_entry):
    admin = make_admin()
    made = make_pipeline_entry(stage="sourced")

    patch = client.patch(
        f"/api/v1/admin/pipeline/{made['entry_id']}/stage",
        json={"stage": "screening"}, headers=admin["headers"],
    )
    assert patch.status_code == 200, patch.text

    history = client.get(
        f"/api/v1/admin/pipeline/{made['entry_id']}/history", headers=admin["headers"],
    ).json()
    row = history["items"][-1]
    assert row["from_stage"] == "sourced" and row["to_stage"] == "screening"
    assert row["changed_by"] == admin["id"]
    assert row["changed_by_name"] == "Admin Example"


def test_bv7_history_survives_a_deleted_actor(client, db_run, make_admin, make_pipeline_entry):
    """A stage history row is append-only and outlives the account that
    wrote it; a LEFT JOIN keeps the row and nulls only the name."""
    from core.database import execute

    admin = make_admin()
    made = make_pipeline_entry(stage="sourced")
    client.patch(
        f"/api/v1/admin/pipeline/{made['entry_id']}/stage",
        json={"stage": "interview"}, headers=admin["headers"],
    )
    db_run(execute, "UPDATE pipeline_stage_history SET changed_by = NULL WHERE pipeline_entry_id = $1",
           made["entry_id"])

    reader = make_admin()
    history = client.get(
        f"/api/v1/admin/pipeline/{made['entry_id']}/history", headers=reader["headers"],
    ).json()
    assert history["total"] >= 1
    assert all(row["changed_by_name"] is None for row in history["items"])


# ── BV8: the closed stage list, at the API and in the database ───────────

@pytest.mark.parametrize("stage", ["sourced", "new", "screening", "interview", "offer", "placed", "rejected"])
def test_bv8_admin_patch_accepts_every_canonical_stage(client, make_admin, make_pipeline_entry, stage):
    admin = make_admin()
    made = make_pipeline_entry()
    res = client.patch(
        f"/api/v1/admin/pipeline/{made['entry_id']}/stage",
        json={"stage": stage}, headers=admin["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.json()["stage"] == stage


@pytest.mark.parametrize("stage", ["Screening", "interviewing", "", "onbekend"])
def test_bv8_admin_patch_refuses_an_unknown_stage(client, make_admin, make_pipeline_entry, stage):
    admin = make_admin()
    made = make_pipeline_entry()
    res = client.patch(
        f"/api/v1/admin/pipeline/{made['entry_id']}/stage",
        json={"stage": stage}, headers=admin["headers"],
    )
    assert res.status_code == 422, res.text


def test_bv8_client_portal_add_and_patch_refuse_an_unknown_stage(
    client, db_run, make_client_user, make_email,
):
    from core.database import fetch_one

    client_user = make_client_user(approved=True)
    candidate = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, source, lawful_basis)
           VALUES ('WS5 Stage', $1, 'manual', 'gerechtvaardigd_belang') RETURNING id""",
        make_email("ws5-stage"),
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title, status) VALUES ($1, 'Stage Job', 'open') RETURNING id",
        client_user["client_id"],
    )

    bad = client.post(
        "/api/v1/client/pipeline",
        json={"candidate_id": candidate["id"], "job_id": job["id"], "stage": "benaderd"},
        headers=client_user["headers"],
    )
    assert bad.status_code == 422, bad.text

    good = client.post(
        "/api/v1/client/pipeline",
        json={"candidate_id": candidate["id"], "job_id": job["id"], "stage": "sourced"},
        headers=client_user["headers"],
    )
    assert good.status_code in (200, 201), good.text
    entry_id = good.json()["id"]

    bad_patch = client.patch(
        f"/api/v1/client/pipeline/{entry_id}/stage",
        json={"stage": "interviewing"}, headers=client_user["headers"],
    )
    assert bad_patch.status_code == 422, bad_patch.text


def test_bv8_database_rejects_an_unknown_stage_on_insert(client, db_run, make_pipeline_entry):
    """The CHECK is NOT VALID, which still enforces every new write."""
    import asyncpg

    from core.database import execute

    made = make_pipeline_entry()
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        db_run(execute, "UPDATE pipeline_entries SET stage = 'zomaar' WHERE id = $1", made["entry_id"])


def _load_043():
    path = os.path.join(MIGRATIONS_DIR, "043_pipeline_stage_check.py")
    spec = importlib.util.spec_from_file_location("m043", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bv8_migration_043_runs_twice_and_tolerates_an_unknown_existing_value(
    db_run, make_pipeline_entry,
):
    """Re-runs the real migration through the real runner, on a table that
    already carries (a) a value differing only in case and spacing, (b) a
    value from a vocabulary the mapping table knows, and (c) a value the
    migration has never heard of. All three must land inside the seven --
    the third one via the catch-all, because a row the CHECK rejects is
    not an untouched row but an unwritable one (see the erase_person test
    below)."""
    from core.database import execute, fetch_val

    mod = _load_043()

    deviating = make_pipeline_entry()
    known_alias = make_pipeline_entry()
    unknown = make_pipeline_entry()

    # Seed the deviating values behind the constraint's back -- the whole
    # point is the state a production table can already be in.
    db_run(execute, "ALTER TABLE pipeline_entries DROP CONSTRAINT IF EXISTS pipeline_entries_stage_check")
    db_run(execute, "UPDATE pipeline_entries SET stage = '  Screening ' WHERE id = $1", deviating["entry_id"])
    db_run(execute, "UPDATE pipeline_entries SET stage = 'interviewing' WHERE id = $1", known_alias["entry_id"])
    db_run(execute, "UPDATE pipeline_entries SET stage = 'op-de-koffie' WHERE id = $1", unknown["entry_id"])
    db_run(execute, "DELETE FROM schema_migrations WHERE version = $1", mod.VERSION)

    db_run(mod.run_migration, mod.VERSION, mod.MIGRATION_SQL)

    assert db_run(fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", deviating["entry_id"]) == "screening"
    assert db_run(fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", known_alias["entry_id"]) == "interview"
    assert db_run(fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", unknown["entry_id"]) == "sourced", (
        "an unmapped value goes to the column default: the lowest stage, claiming no progress"
    )

    constraint = db_run(
        fetch_val,
        "SELECT convalidated FROM pg_constraint WHERE conname = 'pipeline_entries_stage_check'",
    )
    assert constraint is False, "the constraint must land as NOT VALID, never validated by the deploy"

    # Second run: the runner sees its own version row and does nothing.
    db_run(mod.run_migration, mod.VERSION, mod.MIGRATION_SQL)
    assert db_run(fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", known_alias["entry_id"]) == "interview"

    # And the SQL itself is re-runnable even without the version guard.
    db_run(execute, "DELETE FROM schema_migrations WHERE version = $1", mod.VERSION)
    db_run(mod.run_migration, mod.VERSION, mod.MIGRATION_SQL)
    assert db_run(fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", deviating["entry_id"]) == "screening"


# Every value migrations/043's mapping table claims to handle, and what it
# must become. Seeded as real rows (code-review F5) so a mapping that is
# dropped from the SQL fails here on its own line instead of disappearing
# quietly into the catch-all and reading as 'sourced'.
_MAPPED_STAGES = {
    "  Screening ": "screening",
    "INTERVIEW": "interview",
    "": "sourced",
    "applied": "new",
    "contacted": "new",
    "active": "new",
    "suggested": "sourced",
    "interviewing": "interview",
    "offered": "offer",
    "hired": "placed",
    "declined": "rejected",
    "afgewezen": "rejected",
}


def test_bv8_migration_043_maps_every_documented_value_to_its_own_target(db_run, make_pipeline_entry):
    """One row per documented mapping. 'sourced' as an expected result is
    only correct for the two values that genuinely mean "no progress
    recorded"; for the rest it would mean the mapping was lost and the
    catch-all swallowed it."""
    from core.database import execute, fetch_val

    mod = _load_043()
    entries = {stored: make_pipeline_entry() for stored in _MAPPED_STAGES}

    db_run(execute, "ALTER TABLE pipeline_entries DROP CONSTRAINT IF EXISTS pipeline_entries_stage_check")
    for stored, made in entries.items():
        db_run(execute, "UPDATE pipeline_entries SET stage = $1 WHERE id = $2", stored, made["entry_id"])
    db_run(execute, "DELETE FROM schema_migrations WHERE version = $1", mod.VERSION)

    db_run(mod.run_migration, mod.VERSION, mod.MIGRATION_SQL)

    for stored, expected in _MAPPED_STAGES.items():
        actual = db_run(
            fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", entries[stored]["entry_id"],
        )
        assert actual == expected, f"{stored!r} became {actual!r}, expected {expected!r}"


def test_bv8_migration_043_leaves_a_null_stage_alone(db_run, make_pipeline_entry):
    """NULL satisfies the CHECK, so there is nothing to normalise and
    nothing that would make the row unwritable."""
    from core.database import execute, fetch_val

    mod = _load_043()
    made = make_pipeline_entry()

    db_run(execute, "ALTER TABLE pipeline_entries DROP CONSTRAINT IF EXISTS pipeline_entries_stage_check")
    db_run(execute, "UPDATE pipeline_entries SET stage = NULL WHERE id = $1", made["entry_id"])
    db_run(execute, "DELETE FROM schema_migrations WHERE version = $1", mod.VERSION)

    db_run(mod.run_migration, mod.VERSION, mod.MIGRATION_SQL)

    assert db_run(fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", made["entry_id"]) is None
    db_run(execute, "UPDATE pipeline_entries SET notes = NULL WHERE id = $1", made["entry_id"])
    db_run(execute, "UPDATE pipeline_entries SET stage = 'sourced' WHERE id = $1", made["entry_id"])


def test_bv8_migration_043_leaves_every_row_writable_for_erase_person(db_run, make_pipeline_entry):
    """security-audit HIGH. A NOT VALID CHECK skips only the initial scan;
    it still fires on every later write to a row, including one that does
    not touch `stage`. routers/gdpr.py's erase_person() does exactly that
    (`UPDATE pipeline_entries SET notes = NULL WHERE candidate_id = $1`),
    halfway through a non-transactional erasure with users and candidates
    already anonymised. So after this migration no row may be left
    outside the seven, and VALIDATE CONSTRAINT must succeed immediately.
    """
    from core.database import execute, fetch_val

    mod = _load_043()
    stranded = make_pipeline_entry()

    db_run(execute, "ALTER TABLE pipeline_entries DROP CONSTRAINT IF EXISTS pipeline_entries_stage_check")
    db_run(execute, "UPDATE pipeline_entries SET stage = 'inactive' WHERE id = $1", stranded["entry_id"])
    db_run(execute, "DELETE FROM schema_migrations WHERE version = $1", mod.VERSION)

    db_run(mod.run_migration, mod.VERSION, mod.MIGRATION_SQL)

    assert db_run(fetch_val, "SELECT stage FROM pipeline_entries WHERE id = $1", stranded["entry_id"]) == "sourced"

    # The exact statement erase_person() runs, on the row that used to be
    # stranded. Before the catch-all this raised CheckViolationError.
    db_run(
        execute, "UPDATE pipeline_entries SET notes = NULL WHERE candidate_id = $1",
        stranded["candidate_id"],
    )

    # And nothing anywhere in the table is left outside the seven.
    leftover = db_run(
        fetch_val,
        """SELECT COUNT(*) FROM pipeline_entries
            WHERE stage IS NOT NULL
              AND stage NOT IN ('sourced','new','screening','interview','offer','placed','rejected')""",
    )
    assert leftover == 0

    db_run(execute, "ALTER TABLE pipeline_entries VALIDATE CONSTRAINT pipeline_entries_stage_check")
    assert db_run(
        fetch_val, "SELECT convalidated FROM pg_constraint WHERE conname = 'pipeline_entries_stage_check'",
    ) is True

    # Put the constraint back the way a fresh deploy leaves it, so the
    # NOT VALID assertion in the test above holds whatever the order.
    db_run(execute, "ALTER TABLE pipeline_entries DROP CONSTRAINT IF EXISTS pipeline_entries_stage_check")
    db_run(
        execute,
        "ALTER TABLE pipeline_entries ADD CONSTRAINT pipeline_entries_stage_check "
        "CHECK (stage IN ('sourced', 'new', 'screening', 'interview', 'offer', 'placed', 'rejected')) NOT VALID",
    )


# ── BV9: the erase confirmation is the address ───────────────────────────

def test_bv9_erase_refuses_a_confirmation_that_is_not_the_address(client, make_admin, make_email):
    admin = make_admin()
    res = client.post(
        "/api/v1/admin/gdpr/erase",
        json={"email": make_email("ws5-erase"), "confirm": make_email("ws5-other")},
        headers=admin["headers"],
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "erase_confirm_must_match_email"


def test_bv9_erase_refuses_a_missing_confirmation(client, make_admin, make_email):
    admin = make_admin()
    email = make_email("ws5-erase-none")
    res = client.post(
        "/api/v1/admin/gdpr/erase", json={"email": email}, headers=admin["headers"],
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "erase_confirm_must_match_email"
    # security-audit MEDIUM: a required `confirm` would have made this
    # FastAPI's own validation error, which echoes the whole request body.
    assert email not in res.text, res.text


def test_bv9_erase_refusal_never_echoes_the_address_over_http(client, make_admin, make_email):
    admin = make_admin()
    email = make_email("ws5-erase-echo")
    other = make_email("ws5-erase-echo-other")
    res = client.post(
        "/api/v1/admin/gdpr/erase", json={"email": email, "confirm": other},
        headers=admin["headers"],
    )
    assert res.status_code == 422, res.text
    assert email not in res.text and other not in res.text, res.text


def test_bv9_erase_refuses_an_empty_confirmation(client, make_admin, make_email):
    admin = make_admin()
    email = make_email("ws5-erase-empty")
    res = client.post(
        "/api/v1/admin/gdpr/erase", json={"email": email, "confirm": ""},
        headers=admin["headers"],
    )
    assert res.status_code == 422, res.text
    assert email not in res.text, res.text


def test_bv9_erase_proceeds_when_the_address_is_repeated(client, db_run, make_admin, make_email):
    from core.database import fetch_one

    admin = make_admin()
    email = make_email("ws5-erase-ok")
    db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, source, lawful_basis)
           VALUES ('Te Wissen', $1, 'manual', 'gerechtvaardigd_belang') RETURNING id""",
        email,
    )

    res = client.post(
        "/api/v1/admin/gdpr/erase",
        json={"email": email, "confirm": f"  {email.upper()} "},
        headers=admin["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "complete"


def test_bv9_admin_target_still_needs_its_own_second_answer(client, make_admin):
    """The typed address and the admin/self opt-in are two questions --
    answering the first one does not answer the second."""
    admin = make_admin()
    target = make_admin()

    first = client.post(
        "/api/v1/admin/gdpr/erase",
        json={"email": target["email"], "confirm": target["email"]},
        headers=admin["headers"],
    )
    assert first.status_code == 409, first.text
    assert first.json()["detail"]["code"] == "erase_admin_or_self_requires_confirm"

    second = client.post(
        "/api/v1/admin/gdpr/erase",
        json={"email": target["email"], "confirm": target["email"], "confirm_admin_or_self": True},
        headers=admin["headers"],
    )
    assert second.status_code == 200, second.text


def test_bv9_erase_needs_an_admin_jwt(client, make_candidate_user, make_email):
    user = make_candidate_user()
    email = make_email("ws5-erase-forbidden")
    res = client.post(
        "/api/v1/admin/gdpr/erase", json={"email": email, "confirm": email},
        headers=user["headers"],
    )
    assert res.status_code == 403, res.text


# ── BV10: sort and order on the five list routes ─────────────────────────

_SORTABLE_ROUTES = [
    ("/api/v1/admin/users", "full_name"),
    ("/api/v1/admin/candidates", "full_name"),
    ("/api/v1/admin/jobs", "title"),
    ("/api/v1/admin/placements", "start_date"),
    ("/api/v1/admin/retention/review", "term_expired_at"),
]


@pytest.mark.parametrize("path,column", _SORTABLE_ROUTES)
def test_bv10_an_allowlisted_column_sorts(client, make_admin, path, column):
    admin = make_admin()
    res = client.get(path, params={"sort": column, "order": "asc"}, headers=admin["headers"])
    assert res.status_code == 200, res.text


@pytest.mark.parametrize("path,_column", _SORTABLE_ROUTES)
def test_bv10_a_column_outside_the_allowlist_is_422(client, make_admin, path, _column):
    admin = make_admin()
    res = client.get(path, params={"sort": "password_hash"}, headers=admin["headers"])
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "invalid_sort_column"


@pytest.mark.parametrize("path,_column", _SORTABLE_ROUTES)
def test_bv10_an_injection_shaped_sort_is_422_not_a_500(client, make_admin, path, _column):
    admin = make_admin()
    res = client.get(
        path, params={"sort": "id; DROP TABLE users"}, headers=admin["headers"],
    )
    assert res.status_code == 422, res.text


@pytest.mark.parametrize("path,column", _SORTABLE_ROUTES)
def test_bv10_an_unknown_order_direction_is_422(client, make_admin, path, column):
    admin = make_admin()
    res = client.get(path, params={"sort": column, "order": "sideways"}, headers=admin["headers"])
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "invalid_order_direction"


def test_bv10_users_sort_orders_the_whole_set_not_just_the_page(client, make_admin):
    admin = make_admin()
    asc = client.get(
        "/api/v1/admin/users", params={"sort": "id", "order": "asc", "limit": 5},
        headers=admin["headers"],
    ).json()["items"]
    desc = client.get(
        "/api/v1/admin/users", params={"sort": "id", "order": "desc", "limit": 5},
        headers=admin["headers"],
    ).json()["items"]

    assert [r["id"] for r in asc] == sorted(r["id"] for r in asc)
    assert [r["id"] for r in desc] == sorted((r["id"] for r in desc), reverse=True)
    assert asc[0]["id"] < desc[0]["id"], "asc and desc must start at opposite ends of the set"


def test_bv10_candidates_sort_applies_across_both_merge_branches(client, db_run, make_admin, make_email):
    """GET /candidates merges a `candidates` branch and a
    `candidate_profiles` branch in Python; a sorted page must be ordered
    as one sequence, not per branch."""
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:8]
    # One row in each branch, with names that interleave.
    db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, source, lawful_basis)
           VALUES ($1, $2, 'manual', 'gerechtvaardigd_belang') RETURNING id""",
        f"AAA Sourced {suffix}", make_email(f"ws5-sortA-{suffix}"),
    )
    profile_email = make_email(f"ws5-sortB-{suffix}")
    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, is_verified)
           VALUES ($1, 'x', $2, 'candidate', TRUE) RETURNING id""",
        profile_email, f"BBB Self {suffix}",
    )
    db_run(execute, "INSERT INTO candidate_profiles (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user["id"])

    body = client.get(
        "/api/v1/admin/candidates",
        params={"search": suffix, "sort": "full_name", "order": "asc", "limit": 50},
        headers=admin["headers"],
    ).json()
    names = [item["full_name"] for item in body["items"]]
    assert names == sorted(names), names
    assert any(n.startswith("AAA") for n in names) and any(n.startswith("BBB") for n in names), (
        "both branches must be represented, otherwise the merge is not being tested"
    )


# (path, the field carrying the route's default sort, is the default DESC)
# -- every one of these is called by the panel on load with no sort at
# all, so the default ordering is the contract that matters most.
_DEFAULT_ORDER_ROUTES = [
    ("/api/v1/admin/users", "created_at", True),
    ("/api/v1/admin/candidates", "created_at", True),
    ("/api/v1/admin/jobs", "created_at", True),
    # PlacementResponse does not expose created_at, so the check reads the
    # route's own tiebreaker instead: ids are monotonic with insertion, so
    # id DESC is created_at DESC for this table.
    ("/api/v1/admin/placements", "id", True),
    ("/api/v1/admin/retention/review", "term_expired_at", False),
]


@pytest.mark.parametrize("path,field,descending", _DEFAULT_ORDER_ROUTES)
def test_bv10_omitting_sort_keeps_the_historical_order(
    client, make_admin, make_placement, review_items, path, field, descending,
):
    """Every existing caller passes neither parameter, so each route must
    still return its own historical ordering. Parametrised over all five
    (code-review F1): the single-route version of this test let both
    "drop the reverse() from the /candidates merge" and "flip the
    /candidates default to ASC" through the whole suite."""
    admin = make_admin()
    review_items(3)
    for _ in range(2):
        make_placement()

    items = client.get(path, params={"limit": 10}, headers=admin["headers"]).json()["items"]
    values = [r[field] for r in items if r.get(field) is not None]
    assert len(values) >= 2, f"{path}: need at least two rows to detect an order"
    assert values == sorted(values, reverse=descending), path


def test_bv10_candidates_default_is_newest_first_and_order_desc_reverses_it(
    client, db_run, make_admin, make_email,
):
    """The /candidates default in particular: it is the merged two-branch
    route, its order is produced in Python, and the panel loads it with no
    parameters. Both directions asserted, so a lost reverse() or a flipped
    default cannot pass."""
    from core.database import fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:8]
    for i in range(3):
        db_run(
            fetch_one,
            """INSERT INTO candidates (full_name, email, source, lawful_basis)
               VALUES ($1, $2, 'manual', 'gerechtvaardigd_belang') RETURNING id""",
            f"Default Order {suffix} {i}", make_email(f"ws5-defaultorder-{suffix}-{i}"),
        )

    default = client.get(
        "/api/v1/admin/candidates", params={"search": suffix, "limit": 10}, headers=admin["headers"],
    ).json()["items"]
    created = [r["created_at"] for r in default]
    assert len(created) == 3
    assert created == sorted(created, reverse=True), "the default is newest first"

    ascending = client.get(
        "/api/v1/admin/candidates",
        params={"search": suffix, "limit": 10, "sort": "created_at", "order": "asc"},
        headers=admin["headers"],
    ).json()["items"]
    assert [r["email"] for r in ascending] == [r["email"] for r in reversed(default)], (
        "order=asc must be the exact reverse of the default page"
    )

    descending = client.get(
        "/api/v1/admin/candidates",
        params={"search": suffix, "limit": 10, "sort": "created_at", "order": "desc"},
        headers=admin["headers"],
    ).json()["items"]
    assert [r["email"] for r in descending] == [r["email"] for r in default], (
        "order=desc must reproduce the default page"
    )


def test_bv10_candidates_merge_matches_postgres_for_both_directions(
    client, db_run, make_admin, make_email,
):
    """code-review F2: the merge is sorted in Python while each branch is
    cut in SQL, and nothing until now compared the two. Seeds NULL and
    non-NULL sort values across both branches and asserts the route's id
    sequence equals what Postgres produces for the same ids."""
    from core.database import execute, fetch_all, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:8]
    candidate_ids = []
    # Branch A: two with a title, one with NULL.
    for i, title in enumerate((f"Zeta {suffix}", None, f"Alfa {suffix}")):
        row = db_run(
            fetch_one,
            """INSERT INTO candidates (full_name, email, current_title, source, lawful_basis)
               VALUES ($1, $2, $3, 'manual', 'gerechtvaardigd_belang') RETURNING id""",
            f"Merge A {suffix} {i}", make_email(f"ws5-mergeA-{suffix}-{i}"), title,
        )
        candidate_ids.append(row["id"])
    # Branch B: same mix, on candidate_profiles rows with no candidates row.
    user_ids = []
    for i, title in enumerate((f"Mu {suffix}", None, f"Beta {suffix}")):
        user = db_run(
            fetch_one,
            """INSERT INTO users (email, password_hash, full_name, role, is_verified)
               VALUES ($1, 'x', $2, 'candidate', TRUE) RETURNING id""",
            make_email(f"ws5-mergeB-{suffix}-{i}"), f"Merge B {suffix} {i}",
        )
        db_run(
            execute,
            "INSERT INTO candidate_profiles (user_id, current_title) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET current_title = EXCLUDED.current_title",
            user["id"], title,
        )
        user_ids.append(user["id"])

    for direction, sql_direction in (("asc", "ASC"), ("desc", "DESC")):
        route_ids = [
            item["id"] for item in client.get(
                "/api/v1/admin/candidates",
                params={"search": suffix, "sort": "current_title", "order": direction, "limit": 50},
                headers=admin["headers"],
            ).json()["items"]
        ]
        assert len(route_ids) == 6, route_ids

        # The same six rows, ordered by Postgres over one UNION ALL, on the
        # same (current_title, created_at) pair the route orders on.
        expected = db_run(
            fetch_all,
            f"""SELECT id FROM (
                    SELECT c.id AS id, c.current_title AS current_title, c.created_at AS created_at
                      FROM candidates c WHERE c.id = ANY($1::int[])
                    UNION ALL
                    SELECT u.id AS id, cp.current_title AS current_title, cp.created_at AS created_at
                      FROM candidate_profiles cp JOIN users u ON u.id = cp.user_id
                     WHERE u.id = ANY($2::int[])
                ) merged
                ORDER BY current_title {sql_direction}, created_at {sql_direction}""",
            candidate_ids, user_ids,
        )
        assert route_ids == [r["id"] for r in expected], (
            f"{direction}: the Python merge disagrees with Postgres over the same rows"
        )


def test_bv10_sorting_on_the_tiebreaker_column_itself_works(client, make_admin):
    """security-audit LOW #3: the route must not emit "id ASC, id DESC"."""
    admin = make_admin()
    for path in ("/api/v1/admin/users", "/api/v1/admin/jobs", "/api/v1/admin/placements"):
        res = client.get(path, params={"sort": "id", "order": "asc"}, headers=admin["headers"])
        assert res.status_code == 200, (path, res.text)
        ids = [r["id"] for r in res.json()["items"]]
        assert ids == sorted(ids), path


def test_bv10_candidates_page_boundary_holds_with_duplicate_sort_values(
    client, db_run, make_admin, make_email,
):
    """security-audit LOW #4: rows sharing a sort value, spread over both
    merge branches and across a page boundary, must appear exactly once
    over the two pages -- no row lost between the branches' own cuts."""
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:8]
    shared_title = f"Duplicate Title {suffix}"

    # Three in the candidates branch, three in the profiles-only branch,
    # all with the identical sort value.
    for i in range(3):
        db_run(
            fetch_one,
            """INSERT INTO candidates (full_name, email, current_title, source, lawful_basis)
               VALUES ($1, $2, $3, 'manual', 'gerechtvaardigd_belang') RETURNING id""",
            f"Dup Sourced {suffix} {i}", make_email(f"ws5-dupA-{suffix}-{i}"), shared_title,
        )
    for i in range(3):
        user = db_run(
            fetch_one,
            """INSERT INTO users (email, password_hash, full_name, role, is_verified)
               VALUES ($1, 'x', $2, 'candidate', TRUE) RETURNING id""",
            make_email(f"ws5-dupB-{suffix}-{i}"), f"Dup Self {suffix} {i}",
        )
        db_run(
            execute,
            "INSERT INTO candidate_profiles (user_id, current_title) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET current_title = EXCLUDED.current_title",
            user["id"], shared_title,
        )

    params = {"search": suffix, "sort": "current_title", "order": "asc"}
    first = client.get(
        "/api/v1/admin/candidates", params={**params, "limit": 3, "offset": 0},
        headers=admin["headers"],
    ).json()
    second = client.get(
        "/api/v1/admin/candidates", params={**params, "limit": 3, "offset": 3},
        headers=admin["headers"],
    ).json()

    assert first["total"] == 6, first
    seen = [(i["kind"], i["email"]) for i in first["items"]] + [(i["kind"], i["email"]) for i in second["items"]]
    assert len(seen) == 6, seen
    assert len(set(seen)) == 6, f"a row appears twice across the page boundary: {seen}"
    assert {kind for kind, _ in seen} == {"sourced", "self-registered"}, seen
