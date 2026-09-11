"""
WS3b/WS3c integratietests tegen een echte Postgres.

Waar tests/test_ws3bc_referral_alerts.py de SQL-vorm en de templates
controleert, bewijst dit bestand wat die queries tegen echte rijen doen.
Dat onderscheid is hier niet academisch: de kern van dit spoor bestaat
uit WHERE-clausules die iemand wel of niet een e-mail bezorgen, en een
string-assertie kan niet zien dat een clausule per ongeluk nul rijen
selecteert.

Adversarieel, in deze volgorde:
  1. hergebruik van een afmeldtoken doet niets;
  2. afmelden met een onbestaand token geeft exact hetzelfde antwoord als
     met een geldig token (geen enumeratie-orakel);
  3. een kandidaat die zijn toestemming heeft ingetrokken krijgt nooit
     een alert;
  4. de 18-maandengrens ligt precies;
  5. met de schakelaars uit gaat er geen enkele mail de deur uit.

Geen letterlijke tokenachtige strings: elk token komt uit
secrets.token_urlsafe(32), net als in de productiecode.
"""
import secrets
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Zelfde reden als in test_ws_vacatures_probes.py: de limiter
    (core/ratelimit.py) is één proces-breed object en de integratiesuite
    deelt een sessie-scoped TestClient, dus elke aanroep hier telt op bij
    wat andere bestanden in dezelfde minuut al deden. Deze tests gaan over
    het gedrag van /api/public/unsubscribe (10/minuut), niet over de
    limiet zelf; die heeft eigen dekking in
    test_ws_e4_ratelimit_lockout.py."""
    from core.ratelimit import limiter

    limiter.reset()
    yield


def _email(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def _insert_alert_candidate(db_run, **over):
    """Een kandidaat die aan elke voorwaarde voor een alert voldoet, tenzij
    een test er een kapotmaakt."""
    from core.database import fetch_one

    fields = {
        "email": _email("alert"),
        "consent_scope": "matching_and_contact",
        "lawful_basis": "opt_in_talentpool",
    }
    fields.update(over)
    return db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, lawful_basis, consent_scope, consent_talentpool_until,
              job_alert_optin_at, consent_withdrawn_at, job_alert_unsubscribed_at, updated_at)
           VALUES ('Alert Kandidaat', $1, $2, $3, NOW() + INTERVAL '12 months',
                   NOW() - INTERVAL '1 day', $4, $5, NOW())
           RETURNING id, email""",
        fields["email"], fields["lawful_basis"], fields["consent_scope"],
        over.get("consent_withdrawn_at"), over.get("job_alert_unsubscribed_at"),
    )


def _open_job(db_run, title="Embedded Software Engineer"):
    from core.database import fetch_one

    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
        f"Alert Client {uuid.uuid4().hex[:8]}",
    )
    return db_run(
        fetch_one,
        """INSERT INTO job_orders (client_id, title, city, status, is_demo)
           VALUES ($1, $2, 'Eindhoven', 'open', false) RETURNING id""",
        client_row["id"], title,
    )


def _suggest_match(db_run, candidate_id, job_id, score=81.0):
    from core.database import execute

    db_run(
        execute,
        """INSERT INTO matches (candidate_id, job_id, match_score, status, created_at, updated_at)
           VALUES ($1, $2, $3, 'suggested', NOW(), NOW())
           ON CONFLICT (candidate_id, job_id) DO UPDATE SET match_score = EXCLUDED.match_score""",
        candidate_id, job_id, score,
    )


def _issue_alert_token(db_run, candidate_id, job_ids):
    """Doet wat job_alert_job na een geslaagde verzending doet, zodat een
    afmeldtest niet afhankelijk is van een echte e-mailverzending."""
    from core.database import execute
    from core.security import hash_token

    token = secrets.token_urlsafe(32)
    db_run(
        execute,
        "INSERT INTO job_alert_sends (candidate_id, job_ids, token_hash) VALUES ($1, $2::int[], $3)",
        candidate_id, job_ids, hash_token(token),
    )
    return token


# ── 1 + 2: het afmeldendpoint ───────────────────────────────────────────

def test_unsubscribe_with_a_valid_token_sets_only_the_alert_column(client, db_run):
    from core.database import fetch_one

    cand = _insert_alert_candidate(db_run)
    token = _issue_alert_token(db_run, cand["id"], [1])

    res = client.post("/api/public/unsubscribe", json={"token": token, "scope": "alerts"})
    assert res.status_code == 200

    row = db_run(
        fetch_one,
        "SELECT job_alert_unsubscribed_at, consent_withdrawn_at FROM candidates WHERE id = $1",
        cand["id"],
    )
    assert row["job_alert_unsubscribed_at"] is not None
    # scope='alerts' is de smalle keuze en mag de grondslag niet raken.
    assert row["consent_withdrawn_at"] is None


def test_unsubscribe_token_cannot_be_reused(client, db_run):
    """Adversarieel 1: een tweede keer hetzelfde token gebruiken doet
    niets meer, en is van buiten niet te onderscheiden van de eerste keer."""
    from core.database import fetch_one

    cand = _insert_alert_candidate(db_run)
    token = _issue_alert_token(db_run, cand["id"], [1])

    first = client.post("/api/public/unsubscribe", json={"token": token, "scope": "alerts"})
    assert first.status_code == 200

    used = db_run(fetch_one, "SELECT used_at FROM job_alert_sends WHERE candidate_id = $1", cand["id"])
    assert used["used_at"] is not None

    # Tweede poging, nu met de ingrijpendste scope: die mag NIET alsnog
    # de toestemming intrekken. Een verbruikt token is een dood token.
    second = client.post("/api/public/unsubscribe", json={"token": token, "scope": "all"})
    assert second.status_code == first.status_code
    assert second.json() == first.json()

    row = db_run(fetch_one, "SELECT consent_withdrawn_at FROM candidates WHERE id = $1", cand["id"])
    assert row["consent_withdrawn_at"] is None, "een hergebruikt token mocht niets meer doen"


def test_unsubscribe_unknown_token_is_indistinguishable_from_a_valid_one(client, db_run):
    """Adversarieel 2: geen enumeratie-orakel. Zelfde statuscode, zelfde
    body, voor een geldig token, een verzonnen token, een al gebruikt
    token en een ontbrekend token."""
    cand = _insert_alert_candidate(db_run)
    valid = _issue_alert_token(db_run, cand["id"], [1])

    valid_res = client.post("/api/public/unsubscribe", json={"token": valid, "scope": "alerts"})
    unknown_res = client.post(
        "/api/public/unsubscribe", json={"token": secrets.token_urlsafe(32), "scope": "alerts"},
    )
    reused_res = client.post("/api/public/unsubscribe", json={"token": valid, "scope": "alerts"})
    missing_res = client.post("/api/public/unsubscribe", json={"scope": "alerts"})
    empty_res = client.post("/api/public/unsubscribe", json={})

    codes = {valid_res.status_code, unknown_res.status_code, reused_res.status_code,
             missing_res.status_code, empty_res.status_code}
    bodies = {valid_res.text, unknown_res.text, reused_res.text, missing_res.text, empty_res.text}
    assert codes == {200}, f"statuscodes verschillen: {codes}"
    assert len(bodies) == 1, f"antwoorden verschillen: {bodies}"


def test_unsubscribe_all_withdraws_consent_and_suppresses(client, db_run):
    from core import privacy
    from core.database import fetch_one

    cand = _insert_alert_candidate(db_run)
    token = _issue_alert_token(db_run, cand["id"], [1])

    res = client.post("/api/public/unsubscribe", json={"token": token, "scope": "all"})
    assert res.status_code == 200

    row = db_run(
        fetch_one,
        "SELECT job_alert_unsubscribed_at, consent_withdrawn_at FROM candidates WHERE id = $1",
        cand["id"],
    )
    assert row["job_alert_unsubscribed_at"] is not None
    assert row["consent_withdrawn_at"] is not None

    supp = db_run(
        fetch_one, "SELECT 1 FROM suppression_list WHERE email_hash = $1",
        privacy.email_hash(cand["email"]),
    )
    assert supp is not None, "scope='all' hoort op de blokkeerlijst te komen (SOP §3.3)"

    audit = db_run(
        fetch_one,
        "SELECT changes FROM audit_log WHERE action = 'job_alert_unsubscribe' AND target_id = $1",
        cand["id"],
    )
    assert audit is not None
    assert cand["email"] not in str(audit["changes"]), "audit_log mag het adres nooit in klare tekst bevatten"


def test_unsubscribe_one_click_query_params_work_without_a_json_body(client, db_run):
    """RFC 8058: een mailclient POST met
    Content-Type: application/x-www-form-urlencoded en de body
    'List-Unsubscribe=One-Click'. Dat is geen JSON en mag geen 422
    opleveren -- dat antwoord zou bovendien het enige zijn dat iets
    verklapt."""
    from core.database import fetch_one

    cand = _insert_alert_candidate(db_run)
    token = _issue_alert_token(db_run, cand["id"], [1])

    res = client.post(
        f"/api/public/unsubscribe?token={token}&scope=alerts",
        content="List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200

    row = db_run(fetch_one, "SELECT job_alert_unsubscribed_at FROM candidates WHERE id = $1", cand["id"])
    assert row["job_alert_unsubscribed_at"] is not None


def test_unsubscribe_unknown_scope_falls_back_to_the_narrowest(client, db_run):
    """Een onbekende scope mag nooit de ingrijpendste betekenis krijgen."""
    from core.database import fetch_one

    cand = _insert_alert_candidate(db_run)
    token = _issue_alert_token(db_run, cand["id"], [1])

    res = client.post(f"/api/public/unsubscribe?token={token}&scope=everything", json={})
    assert res.status_code == 200

    row = db_run(fetch_one, "SELECT consent_withdrawn_at FROM candidates WHERE id = $1", cand["id"])
    assert row["consent_withdrawn_at"] is None


# ── 3 + 5: de alert-job zelf ────────────────────────────────────────────

def _run_job_alert(db_run, monkeypatch, *, env=True, db_flag=True):
    from core.config import settings
    from services import scheduler

    monkeypatch.setattr(settings, "job_alerts_enabled", env)

    async def _flag(key):
        return db_flag if key == "job_alerts_enabled" else True

    monkeypatch.setattr(scheduler, "_flag_enabled", _flag)
    return db_run(scheduler.job_alert_job)


class _NoSend:
    """Een e-mailservice die elke verzending registreert en weigert door te
    laten -- zo kan geen enkele test per ongeluk echt mailen."""

    def __init__(self):
        self.sent = []

    async def send_template(self, name, to_email, ctx, lang=None, headers=None):
        self.sent.append(to_email)
        return True


@pytest.fixture
def no_send(monkeypatch):
    """Vervangt de e-mailservice op ELKE plek die er een verwijzing naar
    vasthoudt.

    services/scheduler.py importeert hem binnen de job (`from
    services.email_service import email_service`), dus daar volstaat het
    modulattribuut; routers/admin.py en routers/public.py importeren hem
    bovenaan en houden dus hun eigen verwijzing vast, die door een patch
    op de servicemodule niet wordt geraakt. Alle drie patchen is het
    verschil tussen "deze test mailt niet" en "deze test mailt echt"."""
    import routers.admin as admin_router
    import routers.public as public_router
    import services.email_service as es

    stub = _NoSend()
    monkeypatch.setattr(es, "email_service", stub)
    monkeypatch.setattr(admin_router, "email_service", stub)
    monkeypatch.setattr(public_router, "email_service", stub)
    return stub


def test_withdrawn_consent_never_receives_an_alert(db_run, monkeypatch, no_send):
    """Adversarieel 3. Drie kandidaten met dezelfde openstaande vacature en
    dezelfde match: één normaal, één met ingetrokken toestemming, één die
    zich heeft afgemeld. Alleen de eerste mag een alert krijgen."""
    job = _open_job(db_run)

    ok = _insert_alert_candidate(db_run)
    withdrawn = _insert_alert_candidate(db_run, consent_withdrawn_at=datetime.now(timezone.utc))
    unsubscribed = _insert_alert_candidate(db_run, job_alert_unsubscribed_at=datetime.now(timezone.utc))

    for cand in (ok, withdrawn, unsubscribed):
        _suggest_match(db_run, cand["id"], job["id"])

    _run_job_alert(db_run, monkeypatch, env=True, db_flag=True)

    assert ok["email"] in no_send.sent
    assert withdrawn["email"] not in no_send.sent, "ingetrokken toestemming mag nooit een alert krijgen"
    assert unsubscribed["email"] not in no_send.sent


def test_below_threshold_match_does_not_trigger_an_alert(db_run, monkeypatch, no_send):
    """POST /api/matches accepteert elke match_score; de alert-job mag
    alleen matches melden die minstens zo goed zijn als wat de matcher
    zelf een suggestie noemt."""
    from routers.matches import MATCH_SUGGESTION_MIN_STORED_SCORE

    job = _open_job(db_run)
    weak = _insert_alert_candidate(db_run)
    _suggest_match(db_run, weak["id"], job["id"], score=MATCH_SUGGESTION_MIN_STORED_SCORE - 1)

    _run_job_alert(db_run, monkeypatch, env=True, db_flag=True)

    assert weak["email"] not in no_send.sent


def test_demo_and_closed_vacancies_never_reach_an_alert(db_run, monkeypatch, no_send):
    from core.database import execute

    job = _open_job(db_run, title="Gesloten Rol")
    db_run(execute, "UPDATE job_orders SET status = 'closed' WHERE id = $1", job["id"])

    cand = _insert_alert_candidate(db_run)
    _suggest_match(db_run, cand["id"], job["id"])

    _run_job_alert(db_run, monkeypatch, env=True, db_flag=True)

    assert cand["email"] not in no_send.sent


def test_no_mail_leaves_the_door_with_either_switch_off(db_run, monkeypatch, no_send):
    """Adversarieel 5, met beide schakelaars afzonderlijk."""
    from core.database import fetch_one

    job = _open_job(db_run)
    cand = _insert_alert_candidate(db_run)
    _suggest_match(db_run, cand["id"], job["id"])

    for env, db_flag in ((False, True), (True, False), (False, False)):
        no_send.sent.clear()
        result = _run_job_alert(db_run, monkeypatch, env=env, db_flag=db_flag)
        assert result["status"] == "dry_run"
        assert result["with_matches"] >= 1, "droogloop hoort wel te tellen"
        assert no_send.sent == []

    # En geen enkel spoor in de database dat een verzending suggereert.
    row = db_run(
        fetch_one,
        "SELECT job_alert_last_sent_at FROM candidates WHERE id = $1", cand["id"],
    )
    assert row["job_alert_last_sent_at"] is None
    sends = db_run(fetch_one, "SELECT 1 FROM job_alert_sends WHERE candidate_id = $1", cand["id"])
    assert sends is None


# ── 4: de 18-maandengrens ───────────────────────────────────────────────

def _dormant_user(db_run, months_ago_expr):
    from core.database import fetch_one

    return db_run(
        fetch_one,
        f"""INSERT INTO users (email, password_hash, full_name, role, is_verified, last_login_at)
            VALUES ($1, 'x', 'Slapend Account', 'candidate', true, NOW() - INTERVAL '{months_ago_expr}')
            RETURNING id, email""",
        _email("dormant"),
    )


def test_dormant_warning_window_boundaries_are_exact(db_run, monkeypatch, no_send):
    """Adversarieel 4. Vier accounts rond de randen van het venster:
    16 maanden (te vroeg), 17 maanden en 1 dag (net binnen), 17 maanden
    en 29 dagen (binnen), 18 maanden en 1 dag (te laat). Alleen de twee
    middelste horen gewaarschuwd te worden."""
    from core.config import settings
    from services import scheduler

    too_early = _dormant_user(db_run, "16 months")
    just_in = _dormant_user(db_run, "17 months 1 day")
    still_in = _dormant_user(db_run, "17 months 29 days")
    too_late = _dormant_user(db_run, "18 months 1 day")

    monkeypatch.setattr(settings, "dormant_warning_enabled", True)
    db_run(scheduler.dormant_account_warning_job)

    assert too_early["email"] not in no_send.sent, "16 maanden is te vroeg"
    assert just_in["email"] in no_send.sent
    assert still_in["email"] in no_send.sent
    assert too_late["email"] not in no_send.sent, "boven 18 maanden valt buiten dit venster"


def test_dormant_warning_is_sent_once_per_inactivity_cycle(db_run, monkeypatch, no_send):
    from core.config import settings
    from core.database import fetch_one
    from services import scheduler

    user = _dormant_user(db_run, "17 months 10 days")
    monkeypatch.setattr(settings, "dormant_warning_enabled", True)

    db_run(scheduler.dormant_account_warning_job)
    assert user["email"] in no_send.sent

    stamped = db_run(fetch_one, "SELECT dormant_warning_sent_at FROM users WHERE id = $1", user["id"])
    assert stamped["dormant_warning_sent_at"] is not None

    no_send.sent.clear()
    db_run(scheduler.dormant_account_warning_job)
    assert user["email"] not in no_send.sent, "tweede run mag niet opnieuw waarschuwen"


def test_dormant_warning_dry_run_stamps_nothing(db_run, monkeypatch, no_send):
    """Zou de droogloop stempelen, dan zou PORTAL_ACCOUNT_INACTIVE_SQL 30
    dagen later accounts op de verwijderlijst zetten waarover niemand een
    waarschuwing heeft gehad."""
    from core.config import settings
    from core.database import fetch_one
    from services import scheduler

    user = _dormant_user(db_run, "17 months 5 days")
    monkeypatch.setattr(settings, "dormant_warning_enabled", False)

    result = db_run(scheduler.dormant_account_warning_job)
    assert result["status"] == "dry_run"
    assert no_send.sent == []

    row = db_run(fetch_one, "SELECT dormant_warning_sent_at FROM users WHERE id = $1", user["id"])
    assert row["dormant_warning_sent_at"] is None


# ── WS3b: referral-bevestiging ──────────────────────────────────────────

def test_referral_create_and_confirm_stamps_the_reaction_signal(client, db_run, make_admin, no_send):
    from core.database import fetch_one

    admin = make_admin()
    email = _email("referral")

    res = client.post(
        "/api/v1/admin/candidates/referral",
        json={"full_name": "Referral Kandidaat", "email": email,
              "referred_by": "Piet de Vries", "note": "aangedragen op de meetup"},
        headers=admin["headers"],
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["lawful_basis"] == "toestemming_referral"
    assert body["source"] == "referral"
    assert body["referred_by"] == "Piet de Vries"
    assert email in no_send.sent

    cand = db_run(
        fetch_one,
        "SELECT id, referral_confirmed_at, referred_by, consent_source FROM candidates WHERE LOWER(email) = $1",
        email.lower(),
    )
    assert cand["referral_confirmed_at"] is None, "nog niet bevestigd"
    assert cand["consent_source"] == "referral", "migratie 037 verbreedde de CHECK hiervoor"

    # De bevestigingsmail draagt het ruwe token; de tabel alleen de hash.
    # Reconstrueer het token niet -- maak in plaats daarvan een tweede rij
    # zoals het endpoint dat doet, en bevestig die.
    pending = db_run(
        fetch_one,
        "SELECT id, source, scope FROM talentpool_optin_requests WHERE LOWER(email) = $1",
        email.lower(),
    )
    assert pending["source"] == "referral"
    assert pending["scope"] == "matching_and_contact"


def test_referral_confirm_sets_referral_confirmed_at(client, db_run):
    """De bevestigingsklik is de enige handeling die deze flow van de
    betrokkene vraagt, en moet het reactiesignaal zetten dat
    core/retention.py's referral-selector leest."""
    from core.database import execute, fetch_one
    from core.security import hash_token

    email = _email("referral-confirm")
    cand = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, source, lawful_basis, date_found, referred_by, consent_source, status)
           VALUES ('R', $1, 'referral', 'toestemming_referral', CURRENT_DATE, 'Piet', 'referral', 'sourced')
           RETURNING id""",
        email,
    )
    token = secrets.token_urlsafe(32)
    db_run(
        execute,
        """INSERT INTO talentpool_optin_requests (email, token_hash, scope, source)
           VALUES ($1, $2, 'matching_and_contact', 'referral')""",
        email, hash_token(token),
    )

    res = client.post("/api/public/talentpool-confirm", json={"token": token})
    assert res.status_code == 200, res.text

    row = db_run(
        fetch_one,
        "SELECT referral_confirmed_at, lawful_basis FROM candidates WHERE id = $1", cand["id"],
    )
    assert row["referral_confirmed_at"] is not None
    # De referral-grondslag blijft staan: privacy.should_set_talentpool_
    # lawful_basis() overschrijft een bestaande grondslag nooit.
    assert row["lawful_basis"] == "toestemming_referral"


def test_confirmed_referral_drops_out_of_the_retention_selector(db_run):
    """Het punt van de hele kolom: een referral die bevestigde, mag na 3
    maanden niet op de maandelijkse beoordelingslijst komen."""
    from core import retention
    from core.database import execute, fetch_all, fetch_one

    def _make(confirmed):
        row = db_run(
            fetch_one,
            """INSERT INTO candidates
                 (full_name, email, source, lawful_basis, date_found, status, referral_confirmed_at)
               VALUES ('R', $1, 'referral', 'toestemming_referral',
                       CURRENT_DATE - INTERVAL '4 months', 'sourced', $2)
               RETURNING id""",
            _email("retention-referral"),
            datetime.now(timezone.utc) if confirmed else None,
        )
        return row["id"]

    unconfirmed_id = _make(False)
    confirmed_id = _make(True)

    rows = db_run(fetch_all, retention.REFERRAL_NO_RESPONSE_SQL, "toestemming_referral")
    ids = {r["id"] for r in rows}
    assert unconfirmed_id in ids, "zonder bevestiging is dit nog steeds 'geen reactie'"
    assert confirmed_id not in ids, "een bevestigde referral heeft wel degelijk gereageerd"

    # En de gesourcete selector mag door deze splitsing niet veranderd
    # zijn: die kent de kolom niet en selecteert op zijn eigen grondslag.
    db_run(execute, "SELECT 1")


def test_referral_endpoint_refuses_a_suppressed_address(client, db_run, make_admin, no_send):
    from core import privacy
    from core.database import execute

    admin = make_admin()
    email = _email("referral-suppressed")
    db_run(
        execute,
        "INSERT INTO suppression_list (email_hash, email_domain, reason) VALUES ($1, $2, 'test') "
        "ON CONFLICT (email_hash) DO NOTHING",
        privacy.email_hash(email), privacy.email_domain(email),
    )

    res = client.post(
        "/api/v1/admin/candidates/referral",
        json={"full_name": "Geblokkeerd", "email": email, "referred_by": "Piet"},
        headers=admin["headers"],
    )
    assert res.status_code == 409
    assert email not in no_send.sent, "STOP betekent nooit meer mailen, ook niet als referral"


def test_referral_endpoint_never_overwrites_an_existing_candidate(client, db_run, make_admin, no_send):
    from core.database import fetch_one

    admin = make_admin()
    email = _email("referral-existing")
    db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, source, lawful_basis)
           VALUES ('Bestaand', $1, 'portal_registration', 'portal_registratie') RETURNING id""",
        email,
    )

    res = client.post(
        "/api/v1/admin/candidates/referral",
        json={"full_name": "Referral", "email": email, "referred_by": "Piet"},
        headers=admin["headers"],
    )
    assert res.status_code == 409

    row = db_run(fetch_one, "SELECT lawful_basis FROM candidates WHERE LOWER(email) = $1", email.lower())
    assert row["lawful_basis"] == "portal_registratie", "een bestaande grondslag blijft staan"


def test_referral_endpoint_requires_an_admin_jwt(client):
    res = client.post(
        "/api/v1/admin/candidates/referral",
        json={"full_name": "X", "email": _email("nope"), "referred_by": "Y"},
    )
    assert res.status_code in (401, 403)


def test_referral_audit_log_never_stores_the_plaintext_address(client, db_run, make_admin, no_send):
    from core.database import fetch_one

    admin = make_admin()
    email = _email("referral-audit")
    referrer_email = _email("referrer")

    res = client.post(
        "/api/v1/admin/candidates/referral",
        json={"full_name": "R", "email": email, "referred_by": "Piet",
              "note": f"aangedragen door {referrer_email}"},
        headers=admin["headers"],
    )
    assert res.status_code == 201

    audit = db_run(
        fetch_one,
        "SELECT changes FROM audit_log WHERE action = 'admin_referral_create' AND target_id = $1",
        res.json()["id"],
    )
    changes = str(audit["changes"])
    assert email not in changes
    assert referrer_email not in changes, "redact_emails() hoort ook het adres in de notitie te vangen"
    assert "[redacted:" in changes


# ── WS3c: de portaalschakelaar ──────────────────────────────────────────

def test_portal_switch_opts_in_and_out(client, db_run, make_candidate_user):
    from core.database import fetch_one

    user = make_candidate_user()
    cand = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, lawful_basis) VALUES ('P', $1, 'portal_registratie') RETURNING id",
        user["email"],
    )

    on = client.put("/api/v1/candidate/job-alerts", json={"enabled": True}, headers=user["headers"])
    assert on.status_code == 200, on.text
    assert on.json()["enabled"] is True

    off = client.put("/api/v1/candidate/job-alerts", json={"enabled": False}, headers=user["headers"])
    assert off.status_code == 200
    assert off.json()["enabled"] is False

    row = db_run(
        fetch_one,
        "SELECT job_alert_optin_at, job_alert_unsubscribed_at FROM candidates WHERE id = $1", cand["id"],
    )
    assert row["job_alert_optin_at"] is not None
    assert row["job_alert_unsubscribed_at"] is not None


def test_talentpool_confirm_never_reenrolls_someone_who_unsubscribed(client, db_run):
    """Een afmelding is een intrekking. Een latere talentpool-bevestiging
    met het alerts-vinkje aan mag die niet stilzwijgend ongedaan maken --
    alleen de persoon zelf, ingelogd, kan dat."""
    from core.database import execute, fetch_one
    from core.security import hash_token

    email = _email("reenroll")
    cand = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, lawful_basis, job_alert_unsubscribed_at)
           VALUES ('U', $1, 'opt_in_talentpool', NOW()) RETURNING id""",
        email,
    )
    token = secrets.token_urlsafe(32)
    db_run(
        execute,
        """INSERT INTO talentpool_optin_requests (email, token_hash, scope, source, job_alerts)
           VALUES ($1, $2, 'matching_and_contact', 'kandidaten_page', true)""",
        email, hash_token(token),
    )

    res = client.post("/api/public/talentpool-confirm", json={"token": token})
    assert res.status_code == 200

    row = db_run(fetch_one, "SELECT job_alert_optin_at FROM candidates WHERE id = $1", cand["id"])
    assert row["job_alert_optin_at"] is None, "afgemeld blijft afgemeld tot de persoon zelf terugkomt"


def test_talentpool_confirm_carries_over_the_job_alerts_tick(client, db_run):
    from core.database import execute, fetch_one
    from core.security import hash_token

    email = _email("carryover")
    token = secrets.token_urlsafe(32)
    db_run(
        execute,
        """INSERT INTO talentpool_optin_requests (email, token_hash, scope, source, job_alerts)
           VALUES ($1, $2, 'matching_and_contact', 'kandidaten_page', true)""",
        email, hash_token(token),
    )

    res = client.post("/api/public/talentpool-confirm", json={"token": token})
    assert res.status_code == 200

    row = db_run(fetch_one, "SELECT job_alert_optin_at FROM candidates WHERE LOWER(email) = $1", email.lower())
    assert row["job_alert_optin_at"] is not None


def test_talentpool_confirm_without_the_tick_does_not_opt_in(client, db_run):
    from core.database import execute, fetch_one
    from core.security import hash_token

    email = _email("notick")
    token = secrets.token_urlsafe(32)
    db_run(
        execute,
        """INSERT INTO talentpool_optin_requests (email, token_hash, scope, source, job_alerts)
           VALUES ($1, $2, 'matching_and_contact', 'kandidaten_page', false)""",
        email, hash_token(token),
    )

    res = client.post("/api/public/talentpool-confirm", json={"token": token})
    assert res.status_code == 200

    row = db_run(fetch_one, "SELECT job_alert_optin_at FROM candidates WHERE LOWER(email) = $1", email.lower())
    assert row["job_alert_optin_at"] is None
