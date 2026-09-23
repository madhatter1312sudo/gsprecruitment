"""
WS-4 sonde ("vacatures met anonieme opdrachtgever") -- onafhankelijke
probes tegen het gedeelde contract in migrations/037_pool_vacancies_consent_
sources.py, geschreven zonder de fix in te zien. Zelfde stijl/fixtures als
tests/integration/conftest.py (db_run, client, make_admin, api_key_headers)
en tests/integration/test_ws4_anonymous_vacancies_integration.py, maar een
los bestand met eigen helpers -- dit bestand claimt geen coverage, het is
een onafhankelijke tweede meting van hetzelfde contract.

Verondersteld schema: migraties 000-035 plus 037 zijn toegepast (036 en
038 zijn gereserveerd voor andere sporen en draaien hier niet). Als 037
nog niet is toegepast (clients.is_internal ontbreekt), worden de asserts
die erop steunen geskipt met een expliciete reden -- de rest van de
sonde (wat al op hoofdtak-schema werkt) blijft gewoon draaien en rood
gaan waar het gedrag nog ontbreekt.

Elke sonde in dit bestand komt overeen met een genummerd punt uit de
opdracht:
  1. GET /api/public/jobs -- filtering + projectie (anonymous_client,
     nice_to_have erbij; client_id/fee_percentage/fee_value/filled_at/
     deleted_at/is_demo eraf)
  2. GET /api/public/jobs/{id} -- 200 zelfde projectie; 404 identieke body
     voor gesloten/demo/verwijderd/niet-bestaand; geen API-key nodig
  3. POST /api/public/talentpool-optin -- job_id/job_alerts opslag,
     stille no-op bij ongeldige job_id, 'vacancy_apply' door de CHECK
  4. POST /api/public/talentpool-confirm -- consent_source, matches-rij
     'applied', applied_job in het antwoord, idempotent bij dubbel
     bevestigen, null als de vacature tussentijds sloot
  5. PATCH /api/jobs/{id} -- status 'bogus' -> 422; 'closed' -> 200 en
     verdwijnt van het publieke bord
  6. scripts/seed_pool_vacancies.py -- dry-run/--apply/idempotent
  7. GET /api/v1/admin/analytics -- job_fill_rate telt een interne klant
     niet mee
"""
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """De limiter (core/ratelimit.py) is een enkel proces-breed object en
    de integratiesuite deelt een sessie-scoped TestClient (zie
    tests/integration/conftest.py), dus elke aanroep van dit bestand telt
    mee bovenop wat eerdere testbestanden in dezelfde minuut al tegen
    /api/public/talentpool-optin (5/minuut) deden. Deze sonde test
    contractgedrag, niet het rate-limiet zelf (dat heeft zijn eigen
    dekking in test_ws_e4_ratelimit_lockout.py) -- reset vooraf zodat
    testvolgorde/-toeval geen 429 veroorzaakt waar 202 verwacht wordt."""
    from core.ratelimit import limiter
    limiter.reset()
    yield


def _has_is_internal(db_run):
    from core.database import fetch_val
    return db_run(
        fetch_val,
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'clients' AND column_name = 'is_internal')",
    )


def _mk_client(db_run, *, is_internal=False):
    """Voegt een klantrij toe. Op een DB zonder migratie 037 bestaat
    clients.is_internal nog niet -- deze helper valt dan terug op een
    insert zonder die kolom (is_internal=True is dan zinloos en hoort
    alleen voor te komen in sondes die zelf al met _skip_if_no_037 zijn
    afgeschermd)."""
    from core.database import fetch_one
    name = f"Sonde Klant {uuid.uuid4().hex[:8]}"
    if _has_is_internal(db_run):
        return db_run(
            fetch_one,
            "INSERT INTO clients (company_name, domain, is_internal) VALUES ($1, 'probe.example.com', $2) RETURNING id",
            name, is_internal,
        )
    return db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ($1, 'probe.example.com') RETURNING id",
        name,
    )


def _mk_job(db_run, client_id, *, status="open", is_demo=False, deleted_at=None,
            title=None, nice_to_have="Rust ervaring", company_display=None):
    from core.database import fetch_one
    title = title or f"Sonde Vacature {uuid.uuid4().hex[:8]}"
    return db_run(
        fetch_one,
        """INSERT INTO job_orders
               (client_id, title, description, nice_to_have, status, is_demo,
                deleted_at, company_display, fee_percentage, fee_value)
           VALUES ($1, $2, 'Embedded C++ op een OT-cybersecurity project', $3, $4, $5, $6, $7, 20, 5000)
           RETURNING id, title""",
        client_id, title, nice_to_have, status, is_demo, deleted_at, company_display,
    )


def _cleanup(db_run, job_ids, client_ids):
    from core.database import execute
    if job_ids:
        db_run(execute, "DELETE FROM matches WHERE job_id = ANY($1::int[])", job_ids)
        db_run(execute, "DELETE FROM talentpool_optin_requests WHERE job_id = ANY($1::int[])", job_ids)
        db_run(execute, "DELETE FROM job_orders WHERE id = ANY($1::int[])", job_ids)
    if client_ids:
        db_run(execute, "DELETE FROM clients WHERE id = ANY($1::int[])", client_ids)


def _skip_if_no_037(db_run):
    if not _has_is_internal(db_run):
        pytest.skip(
            "migrations/037_pool_vacancies_consent_sources.py is nog niet toegepast "
            "(clients.is_internal ontbreekt) -- deze sonde steunt op die migratie."
        )


# ── 1. GET /api/public/jobs: filtering + projectie ─────────────────────────

def test_public_jobs_list_filters_and_projection(db_run, client):
    _skip_if_no_037(db_run)
    from core.database import execute

    internal = _mk_client(db_run, is_internal=True)
    external = _mk_client(db_run, is_internal=False)

    open_internal = _mk_job(db_run, internal["id"])
    open_external = _mk_job(db_run, external["id"])
    closed = _mk_job(db_run, external["id"], status="closed")
    demo = _mk_job(db_run, external["id"], is_demo=True)
    deleted = _mk_job(db_run, external["id"])
    db_run(execute, "UPDATE job_orders SET deleted_at = NOW() WHERE id = $1", deleted["id"])

    resp = client.get("/api/public/jobs")
    assert resp.status_code == 200
    body = resp.json()
    ids = {row["id"]: row for row in body}

    assert open_internal["id"] in ids
    assert open_external["id"] in ids
    assert closed["id"] not in ids
    assert demo["id"] not in ids
    assert deleted["id"] not in ids

    row_internal = ids[open_internal["id"]]
    row_external = ids[open_external["id"]]
    assert row_internal["anonymous_client"] is True
    assert row_external["anonymous_client"] is False
    assert row_internal["nice_to_have"] == "Rust ervaring"

    forbidden = {"client_id", "fee_percentage", "fee_value", "filled_at", "deleted_at", "is_demo"}
    assert forbidden.isdisjoint(row_internal.keys()), f"publieke rij lekt: {forbidden & row_internal.keys()}"
    assert forbidden.isdisjoint(row_external.keys()), f"publieke rij lekt: {forbidden & row_external.keys()}"

    _cleanup(db_run, [open_internal["id"], open_external["id"], closed["id"], demo["id"], deleted["id"]],
             [internal["id"], external["id"]])


# ── 2. GET /api/public/jobs/{id}: 200/404 ───────────────────────────────────

def test_public_job_detail_200_matches_list_projection(db_run, client):
    _skip_if_no_037(db_run)
    c = _mk_client(db_run, is_internal=True)
    job = _mk_job(db_run, c["id"])

    list_resp = client.get("/api/public/jobs")
    list_row = next(r for r in list_resp.json() if r["id"] == job["id"])

    detail_resp = client.get(f"/api/public/jobs/{job['id']}")
    assert detail_resp.status_code == 200
    detail_row = detail_resp.json()

    assert set(detail_row.keys()) == set(list_row.keys())
    assert detail_row == list_row

    _cleanup(db_run, [job["id"]], [c["id"]])


def test_public_job_detail_needs_no_api_key(client):
    # Geen X-API-Key header meegegeven -- /api/jobs vereist die wel (401),
    # /api/public/jobs/{id} mag dat niet vereisen.
    resp = client.get("/api/public/jobs/999999999")
    assert resp.status_code != 401


@pytest.mark.parametrize("kind", ["closed", "demo", "deleted", "unknown"])
def test_public_job_detail_404_identical_body(db_run, client, kind):
    from core.database import execute

    c = _mk_client(db_run)
    job_ids = []
    if kind == "unknown":
        target_id = 999999999
    else:
        if kind == "closed":
            job = _mk_job(db_run, c["id"], status="closed")
        elif kind == "demo":
            job = _mk_job(db_run, c["id"], is_demo=True)
        else:
            job = _mk_job(db_run, c["id"])
            db_run(execute, "UPDATE job_orders SET deleted_at = NOW() WHERE id = $1", job["id"])
        target_id = job["id"]
        job_ids = [job["id"]]

    resp = client.get(f"/api/public/jobs/{target_id}")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Job not found"}

    _cleanup(db_run, job_ids, [c["id"]])


def test_public_job_detail_404_bodies_are_pairwise_identical(db_run, client):
    """Niet alleen elk apart gelijk aan {"detail": "Job not found"}, ook
    onderling byte-voor-byte gelijk -- zodat een client de vier gevallen
    nergens aan de body kan onderscheiden."""
    from core.database import execute

    c = _mk_client(db_run)
    closed = _mk_job(db_run, c["id"], status="closed")
    demo = _mk_job(db_run, c["id"], is_demo=True)
    deleted = _mk_job(db_run, c["id"])
    db_run(execute, "UPDATE job_orders SET deleted_at = NOW() WHERE id = $1", deleted["id"])

    bodies = [
        client.get(f"/api/public/jobs/{closed['id']}"),
        client.get(f"/api/public/jobs/{demo['id']}"),
        client.get(f"/api/public/jobs/{deleted['id']}"),
        client.get("/api/public/jobs/999999999"),
    ]
    assert all(r.status_code == 404 for r in bodies)
    assert len({r.text for r in bodies}) == 1

    _cleanup(db_run, [closed["id"], demo["id"], deleted["id"]], [c["id"]])


# ── 3. POST /api/public/talentpool-optin: job_id/job_alerts ────────────────

def test_optin_vacancy_apply_stores_job_id_and_job_alerts(db_run, client):
    _skip_if_no_037(db_run)
    c = _mk_client(db_run)
    job = _mk_job(db_run, c["id"])
    email = f"sonde-optin-{uuid.uuid4().hex[:10]}@example.com"

    resp = client.post(
        "/api/public/talentpool-optin",
        json={"email": email, "consent": True, "scope": "matching_only",
              "source": "vacancy_apply", "job_id": job["id"], "job_alerts": True},
    )
    assert resp.status_code == 202

    from core.database import fetch_one, execute
    row = db_run(
        fetch_one,
        "SELECT job_id, job_alerts, source FROM talentpool_optin_requests WHERE LOWER(email) = $1",
        email.lower(),
    )
    assert row is not None, "vacancy_apply-bron werd geweigerd of niet opgeslagen"
    assert row["job_id"] == job["id"]
    assert row["job_alerts"] is True
    assert row["source"] == "vacancy_apply"

    db_run(execute, "DELETE FROM talentpool_optin_requests WHERE LOWER(email) = $1", email.lower())
    _cleanup(db_run, [job["id"]], [c["id"]])


@pytest.mark.parametrize("kind", ["closed", "unknown"])
def test_optin_invalid_job_id_silently_ignored(db_run, client, kind):
    c = _mk_client(db_run)
    job_ids = []
    if kind == "closed":
        job = _mk_job(db_run, c["id"], status="closed")
        job_id = job["id"]
        job_ids = [job_id]
    else:
        job_id = 999999999

    email = f"sonde-badjob-{uuid.uuid4().hex[:10]}@example.com"
    resp = client.post(
        "/api/public/talentpool-optin",
        json={"email": email, "consent": True, "scope": "matching_only",
              "source": "vacancy_apply", "job_id": job_id},
    )
    assert resp.status_code == 202  # zelfde 202 als een geldige job_id -- geen enumeratiesignaal

    from core.database import fetch_one, execute
    row = db_run(
        fetch_one,
        "SELECT job_id FROM talentpool_optin_requests WHERE LOWER(email) = $1", email.lower(),
    )
    assert row is not None
    assert row["job_id"] is None

    db_run(execute, "DELETE FROM talentpool_optin_requests WHERE LOWER(email) = $1", email.lower())
    _cleanup(db_run, job_ids, [c["id"]])


def test_optin_job_id_out_of_int32_range_no_enumeration_oracle(db_run, client):
    """Security-audit fix (schemas.py TalentpoolOptinRequest.job_id):
    job_id buiten int4-bereik (hier 2**31) moet op de pydantic-validatie
    stranden, voordat de suppressie-check en de job-lookup draaien. Vóór
    de fix bereikte zo'n job_id de job-lookup alleen op het pad zonder
    suppressie-hit (de gesuppressed-tak slaat de lookup over) en
    asyncpg's DataError op die lookup gaf een 500 -- dus gesuppressed gaf
    202 en een vers adres gaf 500, wat suppressiestatus per adres
    verraadde. Met de ge/le-grens op het veld geeft elk van de twee
    adressen dezelfde 422, vóór enige DB-toegang."""
    from core.database import execute, fetch_one
    from core.privacy import email_hash

    suppressed_email = f"sonde-oob-suppressed-{uuid.uuid4().hex[:10]}@example.com"
    fresh_email = f"sonde-oob-fresh-{uuid.uuid4().hex[:10]}@example.com"
    db_run(
        execute,
        "INSERT INTO suppression_list (email_hash, reason) VALUES ($1, 'sonde')",
        email_hash(suppressed_email),
    )

    def _payload(email):
        return {
            "email": email, "consent": True, "scope": "matching_only",
            "source": "vacancy_apply", "job_id": 2 ** 31,
        }

    resp_suppressed = client.post("/api/public/talentpool-optin", json=_payload(suppressed_email))
    resp_fresh = client.post("/api/public/talentpool-optin", json=_payload(fresh_email))

    assert resp_suppressed.status_code == 422, (
        f"job_id=2**31 hoort op validatie te stranden (422), kreeg {resp_suppressed.status_code}: "
        f"{resp_suppressed.text}"
    )
    assert resp_fresh.status_code == 422, (
        f"job_id=2**31 hoort op validatie te stranden (422) ongeacht suppressiestatus, kreeg "
        f"{resp_fresh.status_code}: {resp_fresh.text}"
    )
    assert resp_fresh.status_code == resp_suppressed.status_code
    assert resp_fresh.json() == resp_suppressed.json(), (
        "een gesuppressed en een vers adres moeten identieke status/body geven voor een "
        "out-of-range job_id -- elk verschil is een suppressie-orakel"
    )

    row = db_run(
        fetch_one,
        "SELECT id FROM talentpool_optin_requests WHERE LOWER(email) = $1", fresh_email.lower(),
    )
    assert row is None, "een 422 op validatie mag geen rij in talentpool_optin_requests aanmaken"

    db_run(execute, "DELETE FROM suppression_list WHERE email_hash = $1", email_hash(suppressed_email))


def test_optin_without_job_id_unchanged(db_run, client):
    """Bestaande aanroep zonder job_id blijft werken -- geen regressie op
    het pad zonder vacaturekoppeling."""
    email = f"sonde-nojob-{uuid.uuid4().hex[:10]}@example.com"
    resp = client.post(
        "/api/public/talentpool-optin",
        json={"email": email, "consent": True, "scope": "matching_only", "source": "kandidaten_page"},
    )
    assert resp.status_code == 202

    from core.database import fetch_one, execute
    row = db_run(
        fetch_one,
        "SELECT job_id, job_alerts FROM talentpool_optin_requests WHERE LOWER(email) = $1", email.lower(),
    )
    assert row is not None
    assert row["job_id"] is None
    assert row["job_alerts"] is False  # default

    db_run(execute, "DELETE FROM talentpool_optin_requests WHERE LOWER(email) = $1", email.lower())


# ── 4. POST /api/public/talentpool-confirm: applied_job + matches ──────────

def _optin_token_via_db(db_run, email, *, job_id=None, source="vacancy_apply"):
    """Rechtstreekse insert (omzeilt de rate-limiter/e-mail), zelfde
    resultaat als een geslaagde talentpool_optin()-aanroep."""
    import secrets
    from core.database import execute
    from core.security import hash_token

    token = secrets.token_urlsafe(32)
    db_run(
        execute,
        """INSERT INTO talentpool_optin_requests (email, token_hash, scope, source, job_id)
           VALUES ($1, $2, 'matching_only', $3, $4)""",
        email, hash_token(token), source, job_id,
    )
    return token


def test_confirm_records_applied_match_and_consent_source(db_run, client):
    _skip_if_no_037(db_run)
    c = _mk_client(db_run)
    job = _mk_job(db_run, c["id"])
    email = f"sonde-confirm-{uuid.uuid4().hex[:10]}@example.com"
    token = _optin_token_via_db(db_run, email, job_id=job["id"])

    resp = client.post("/api/public/talentpool-confirm", json={"token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert "applied_job" in body, "applied_job ontbreekt in het antwoord"
    assert body["applied_job"] == {"id": job["id"], "title": job["title"]}

    from core.database import fetch_one, execute
    candidate = db_run(fetch_one, "SELECT id, consent_source FROM candidates WHERE LOWER(email) = $1", email.lower())
    assert candidate is not None
    assert candidate["consent_source"] == "vacancy_apply"

    match = db_run(
        fetch_one,
        "SELECT status FROM matches WHERE candidate_id = $1 AND job_id = $2",
        candidate["id"], job["id"],
    )
    assert match is not None
    assert match["status"] == "applied"

    db_run(execute, "DELETE FROM matches WHERE candidate_id = $1", candidate["id"])
    db_run(execute, "DELETE FROM candidates WHERE id = $1", candidate["id"])
    _cleanup(db_run, [job["id"]], [c["id"]])


def test_confirm_twice_is_idempotent_no_second_match_no_leak(db_run, client):
    _skip_if_no_037(db_run)
    c = _mk_client(db_run)
    job = _mk_job(db_run, c["id"])
    email = f"sonde-confirm2-{uuid.uuid4().hex[:10]}@example.com"
    token = _optin_token_via_db(db_run, email, job_id=job["id"])

    first = client.post("/api/public/talentpool-confirm", json={"token": token})
    assert first.status_code == 200

    second = client.post("/api/public/talentpool-confirm", json={"token": token})
    # Geen 200 met een tweede toegepaste match, en de foutrespons mag niet
    # onthullen of het token ooit geldig was versus nooit bestond.
    assert second.status_code != 200, "een tweede bevestiging met hetzelfde token mag geen 200 + effect geven"

    from core.database import fetch_one, execute
    candidate = db_run(fetch_one, "SELECT id FROM candidates WHERE LOWER(email) = $1", email.lower())
    assert candidate is not None
    match_count = db_run(
        fetch_one,
        "SELECT COUNT(*) AS n FROM matches WHERE candidate_id = $1 AND job_id = $2",
        candidate["id"], job["id"],
    )
    assert match_count["n"] == 1, "dubbel bevestigen mag geen tweede match-rij maken"

    db_run(execute, "DELETE FROM matches WHERE candidate_id = $1", candidate["id"])
    db_run(execute, "DELETE FROM candidates WHERE id = $1", candidate["id"])
    _cleanup(db_run, [job["id"]], [c["id"]])


def test_confirm_job_closed_between_optin_and_confirm_gives_null_applied_job(db_run, client):
    _skip_if_no_037(db_run)
    c = _mk_client(db_run)
    job = _mk_job(db_run, c["id"])
    email = f"sonde-closedmeanwhile-{uuid.uuid4().hex[:10]}@example.com"
    token = _optin_token_via_db(db_run, email, job_id=job["id"])

    from core.database import execute, fetch_one
    db_run(execute, "UPDATE job_orders SET status = 'closed' WHERE id = $1", job["id"])

    resp = client.post("/api/public/talentpool-confirm", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["applied_job"] is None

    candidate = db_run(fetch_one, "SELECT id FROM candidates WHERE LOWER(email) = $1", email.lower())
    match = db_run(
        fetch_one, "SELECT id FROM matches WHERE candidate_id = $1 AND job_id = $2",
        candidate["id"], job["id"],
    )
    assert match is None, "een gesloten vacature mag tussen opt-in en bevestiging geen match aanmaken"

    db_run(execute, "DELETE FROM candidates WHERE id = $1", candidate["id"])
    _cleanup(db_run, [job["id"]], [c["id"]])


# ── 5. PATCH /api/jobs/{id}: status-validatie + verdwijnen van het bord ────

def test_patch_job_status_bogus_is_422(db_run, client, api_key_headers):
    c = _mk_client(db_run)
    job = _mk_job(db_run, c["id"])

    resp = client.patch(f"/api/jobs/{job['id']}", json={"status": "bogus"}, headers=api_key_headers)
    assert resp.status_code == 422, f"verwacht 422 voor status='bogus', kreeg {resp.status_code}: {resp.text}"

    _cleanup(db_run, [job["id"]], [c["id"]])


def test_patch_job_status_closed_removes_from_public_board(db_run, client, api_key_headers):
    c = _mk_client(db_run)
    job = _mk_job(db_run, c["id"])

    pre = client.get("/api/public/jobs")
    assert job["id"] in {r["id"] for r in pre.json()}

    resp = client.patch(f"/api/jobs/{job['id']}", json={"status": "closed"}, headers=api_key_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"

    post = client.get("/api/public/jobs")
    assert job["id"] not in {r["id"] for r in post.json()}

    detail = client.get(f"/api/public/jobs/{job['id']}")
    assert detail.status_code == 404
    assert detail.json() == {"detail": "Job not found"}

    _cleanup(db_run, [job["id"]], [c["id"]])


# ── 6. scripts/seed_pool_vacancies.py ───────────────────────────────────────

def _run_seed_script(dbname, *extra_args):
    import os
    env = dict(os.environ)
    env.update({
        "POSTGRES_HOST": "localhost", "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "mig", "POSTGRES_PASSWORD": "ci-test-password",
        "POSTGRES_DB": dbname,
    })
    return subprocess.run(
        [sys.executable, str(BACKEND_ROOT / "scripts" / "seed_pool_vacancies.py"), *extra_args],
        cwd=str(BACKEND_ROOT), env=env, capture_output=True, text=True, timeout=60,
    )


def test_seed_pool_vacancies_dry_run_then_apply_then_idempotent(db_run, client):
    _skip_if_no_037(db_run)
    data_path = BACKEND_ROOT / "data" / "pool_vacancies.json"
    if not data_path.exists():
        pytest.skip("talent-os/backend/data/pool_vacancies.json ontbreekt nog")

    from core.database import fetch_val
    dbname = db_run(fetch_val, "SELECT current_database()")

    from core.database import fetch_one
    internal = db_run(
        fetch_one,
        "SELECT id FROM clients WHERE company_name = 'GSP Recruitment (anonieme opdrachtgever)' AND is_internal",
    )
    if internal is None:
        pytest.skip("interne klant 'GSP Recruitment (anonieme opdrachtgever)' ontbreekt (037 niet toegepast?)")

    before = db_run(fetch_val, "SELECT COUNT(*) FROM job_orders WHERE client_id = $1", internal["id"])

    dry = _run_seed_script(dbname)
    assert dry.returncode == 0, f"dry-run exitcode {dry.returncode}: stderr={dry.stderr}"
    after_dry = db_run(fetch_val, "SELECT COUNT(*) FROM job_orders WHERE client_id = $1", internal["id"])
    assert after_dry == before, "zonder --apply mag er niets worden ingevoerd"

    apply1 = _run_seed_script(dbname, "--apply")
    assert apply1.returncode == 0, f"--apply exitcode {apply1.returncode}: stderr={apply1.stderr}"

    from core.database import fetch_all
    rows = db_run(
        fetch_all,
        "SELECT status, is_demo, sponsorship_possible, company_display FROM job_orders WHERE client_id = $1",
        internal["id"],
    )
    new_rows = [r for r in rows]
    inserted_count = len(new_rows) - before
    assert inserted_count == 27, f"verwacht precies 27 nieuwe rijen, kreeg {inserted_count}"
    for r in new_rows:
        assert r["status"] == "open"
        assert r["is_demo"] is False
        assert r["sponsorship_possible"] is False
        assert r["company_display"] is None

    apply2 = _run_seed_script(dbname, "--apply")
    assert apply2.returncode == 0
    after_apply2 = db_run(fetch_val, "SELECT COUNT(*) FROM job_orders WHERE client_id = $1", internal["id"])
    assert after_apply2 - before == 27, "een tweede --apply mag geen extra rijen invoeren (0 nieuw)"

    from core.database import execute
    db_run(execute, "DELETE FROM job_orders WHERE client_id = $1 AND created_at > NOW() - INTERVAL '5 minutes'",
           internal["id"])


# ── 7. GET /api/v1/admin/analytics: interne klant telt niet mee ────────────

def test_admin_analytics_job_fill_rate_excludes_internal_client(db_run, client, make_admin):
    _skip_if_no_037(db_run)
    admin = make_admin()
    from core.database import execute, fetch_val

    before_total = db_run(
        fetch_val,
        "SELECT COUNT(*) FROM job_orders j JOIN clients cl ON cl.id = j.client_id "
        "WHERE j.deleted_at IS NULL AND j.is_demo = false AND cl.is_internal = false",
    )
    before_filled = db_run(
        fetch_val,
        "SELECT COUNT(*) FROM job_orders j JOIN clients cl ON cl.id = j.client_id "
        "WHERE j.filled_at IS NOT NULL AND j.deleted_at IS NULL AND j.is_demo = false AND cl.is_internal = false",
    )

    internal = _mk_client(db_run, is_internal=True)
    job = _mk_job(db_run, internal["id"])
    db_run(execute, "UPDATE job_orders SET filled_at = NOW() WHERE id = $1", job["id"])

    resp = client.get("/api/v1/admin/analytics", headers=admin["headers"])
    assert resp.status_code == 200
    fill_rate = resp.json()["job_fill_rate"]

    after_total = db_run(
        fetch_val,
        "SELECT COUNT(*) FROM job_orders j JOIN clients cl ON cl.id = j.client_id "
        "WHERE j.deleted_at IS NULL AND j.is_demo = false AND cl.is_internal = false",
    )
    after_filled = db_run(
        fetch_val,
        "SELECT COUNT(*) FROM job_orders j JOIN clients cl ON cl.id = j.client_id "
        "WHERE j.filled_at IS NOT NULL AND j.deleted_at IS NULL AND j.is_demo = false AND cl.is_internal = false",
    )
    # De gevulde vacature onder de interne klant mag de teller-query voor
    # niet-interne klanten niet raken -- als de endpoint hem toch meetelt,
    # wijkt fill_rate af van wat deze niet-interne telling zou opleveren.
    assert after_total == before_total, "een interne klant-vacature lekte in de niet-interne teller"
    assert after_filled == before_filled, "een interne klant-vacature lekte in de niet-interne filled-teller"
    # Zelfde afronding/0-geval als routers/admin.py's eigen berekening
    # (round(...,1), en 0 -- niet None -- als total_jobs == 0).
    expected_rate = round(after_filled / after_total * 100, 1) if after_total > 0 else 0
    assert fill_rate == expected_rate, (
        f"job_fill_rate ({fill_rate}) wijkt af van de niet-interne telling ({expected_rate}) -- "
        "de interne vacature lijkt mee te tellen"
    )

    _cleanup(db_run, [job["id"]], [internal["id"]])
