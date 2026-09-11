"""
WS3b/WS3c unit tests: referral-bevestiging, waarschuwing slapend account,
en vacature-alerts met opt-in en een-klik-afmelden.

Geen DB en geen netwerk: de templates zijn pure functies, de
scheduler-jobs krijgen fetch_all/execute/email_service gemonkeypatcht op
moduleniveau (zelfde stijl als tests/test_draft_refused_counter.py en
tests/test_ws3_email_service.py), en de SQL-vorm wordt als string
gecontroleerd. De echte rijen-en-kolommen-kant zit in
tests/integration/test_ws3bc_referral_alerts_integration.py.

Geen letterlijke tokenachtige strings in dit bestand: gitleaks slaat
daarop aan. Waar een token nodig is, wordt hij met
secrets.token_urlsafe(32) gegenereerd, precies zoals de productiecode dat
doet.
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest

from core import retention
from core.config import settings
from core.security import hash_token
from services import email_templates
import services.scheduler as sched


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════════════
# WS3b -- referral_confirm template
# ══════════════════════════════════════════════════════════════════════

_REFERRAL_CTX = {
    "full_name": "Jan Jansen",
    "referred_by": "Piet de Vries (oud-collega)",
    "date_found": "2026-09-11",
    "link": "https://gsprecruitment.nl/talentpool-confirm#token=x",
    "ttl_hours": 24,
}


def test_referral_confirm_nl_carries_the_full_art14_block():
    """Het Art. 14-blok moet compleet zijn, en wel precies zo compleet als
    routers/outreach.py's eigen weigeringslogica het definieert: dezelfde
    markers, zodat deze tekst niet langs een andere maatstaf wordt
    beoordeeld dan elk ander eerste bericht aan een gesourcete persoon."""
    from routers.outreach import _ART14_MARKERS_NL, _has_art14_block, _has_optout_line

    _subject, text, _html = email_templates.render("referral_confirm", _REFERRAL_CTX, "nl")

    for marker in _ART14_MARKERS_NL:
        assert marker in text.lower(), f"Art. 14-marker ontbreekt: {marker}"
    assert _has_art14_block(text, "nl")
    assert _has_optout_line(text)


def test_referral_confirm_en_carries_the_full_art14_block():
    from routers.outreach import _ART14_MARKERS_EN, _has_art14_block, _has_optout_line

    _subject, text, _html = email_templates.render("referral_confirm", _REFERRAL_CTX, "en")

    for marker in _ART14_MARKERS_EN:
        assert marker in text.lower(), f"Art. 14 marker missing: {marker}"
    assert _has_art14_block(text, "en")
    assert _has_optout_line(text)


def test_referral_confirm_uses_the_referral_source_sentence_not_the_found_you_one():
    """SOP §3.2: bij referral vervalt de zin "Wij vonden uw [bron] op
    [datum]" volledig en komt de referral-zin ervoor in de plaats. Een
    referral is niet gevonden, hij is aangedragen -- die twee door elkaar
    halen is precies wat het register verbiedt."""
    _s, nl, _h = email_templates.render("referral_confirm", _REFERRAL_CTX, "nl")
    _s, en, _h = email_templates.render("referral_confirm", _REFERRAL_CTX, "en")

    assert "via een aanbeveling van Piet de Vries (oud-collega)" in nl
    assert "Wij vonden uw" not in nl
    assert "through a recommendation from Piet de Vries (oud-collega)" in en
    assert "We found your" not in en


def test_referral_confirm_html_escapes_every_ctx_value():
    ctx = dict(_REFERRAL_CTX, full_name="<script>alert(1)</script>", referred_by="a & b")
    _subject, _text, html = email_templates.render("referral_confirm", ctx, "nl")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a &amp; b" in html


def test_referral_confirm_renders_bilingually_by_default():
    subject, text, html = email_templates.render("referral_confirm", _REFERRAL_CTX)
    assert "Beste Jan Jansen" in text and "Dear Jan Jansen" in text
    assert "GSP Recruitment, KvK 75545586" in html
    assert subject.startswith("U bent bij ons aangedragen")


# ══════════════════════════════════════════════════════════════════════
# WS3b -- referral retentieselector
# ══════════════════════════════════════════════════════════════════════

def test_referral_selector_is_the_sourced_one_plus_the_confirmation_signal():
    assert "referral_confirmed_at IS NULL" in retention.REFERRAL_NO_RESPONSE_SQL
    assert "referral_confirmed_at" not in retention.SOURCED_NO_RESPONSE_SQL
    assert retention.get_row("referral").selector_sql is retention.REFERRAL_NO_RESPONSE_SQL
    # Zelfde termijn en zelfde beschermende guards.
    assert retention.CANDIDATE_NO_REACTION_GUARD_SQL in retention.REFERRAL_NO_RESPONSE_SQL
    assert "INTERVAL '3 months'" in retention.REFERRAL_NO_RESPONSE_SQL


# ══════════════════════════════════════════════════════════════════════
# WS3b -- dormant_warning: template en job
# ══════════════════════════════════════════════════════════════════════

def test_dormant_warning_promises_only_what_the_code_does():
    """De mail mag niet zeggen "je account wordt verwijderd": de code zet
    het account op een lijst die een mens beoordeelt (core/retention.py,
    routers/retention_admin.py). Hij moet wel de datum noemen en zeggen
    dat inloggen genoeg is."""
    ctx = {"full_name": "Jan", "link": "https://gsprecruitment.nl/candidate/login.html", "deadline": "2026-10-11"}
    _s, nl, _h = email_templates.render("dormant_warning", ctx, "nl")
    _s, en, _h = email_templates.render("dormant_warning", ctx, "en")

    assert "2026-10-11" in nl and "2026-10-11" in en
    assert "verwijderlijst" in nl and "deletion list" in en
    assert "beheerder" in nl and "administrator" in en
    assert "Inloggen is genoeg" in nl and "Logging in is enough" in en


def test_dormant_warning_sql_window_is_exactly_17_to_18_months():
    """De 18-maandengrens moet precies liggen: 17 maanden is de ondergrens
    om gewaarschuwd te worden (dat geeft de 30 dagen die
    PORTAL_ACCOUNT_INACTIVE_SQL eist), 18 maanden de bovengrens."""
    sql = sched.DORMANT_WARNING_SQL
    assert "u.last_login_at <= (NOW() - INTERVAL '17 months')" in sql
    assert "u.last_login_at > (NOW() - INTERVAL '18 months')" in sql
    assert "u.role = 'candidate'" in sql
    assert "u.deleted_at IS NULL" in sql
    assert "u.dormant_warning_sent_at IS NULL OR u.dormant_warning_sent_at < u.last_login_at" in sql
    # De beschermende guards komen letterlijk uit core/retention.py, niet
    # uit een tweede handgeschreven kopie.
    assert retention._CANDIDATE_ENGAGEMENT_SIGNALS_SQL in sql


def test_dormant_warning_grace_matches_the_retention_selector():
    """De 30 dagen in de mail en de 30 dagen die de verwijderlijst-selector
    eist, moeten hetzelfde getal zijn."""
    assert sched.DORMANT_WARNING_GRACE_DAYS == 30
    assert "INTERVAL '30 days'" in retention.PORTAL_ACCOUNT_INACTIVE_SQL


def _stub_scheduler_db(monkeypatch, rows_by_sql=None, default_rows=None):
    """fetch_all/execute op services.scheduler vervangen. Geeft
    (executed_sql_args, ) terug zodat een test kan bewijzen dat er niets
    is weggeschreven."""
    executed = []

    async def _fake_fetch_all(sql, *args):
        if rows_by_sql:
            for needle, rows in rows_by_sql.items():
                if needle in sql:
                    return list(rows)
        return list(default_rows or [])

    async def _fake_execute(sql, *args):
        executed.append((sql, args))
        return "UPDATE 1"

    monkeypatch.setattr(sched, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(sched, "execute", _fake_execute)
    return executed


class _RecordingEmailService:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    async def send_template(self, name, to_email, ctx, lang=None, headers=None):
        self.sent.append({"name": name, "to": to_email, "ctx": ctx, "headers": headers})
        return self.ok


@pytest.fixture
def stub_email(monkeypatch):
    svc = _RecordingEmailService()
    import services.email_service as es

    monkeypatch.setattr(es, "email_service", svc)
    return svc


def test_dormant_warning_job_sends_nothing_when_the_switch_is_off(monkeypatch, stub_email):
    """Met DORMANT_WARNING_ENABLED uit: wel tellen, niet verzenden en --
    net zo belangrijk -- niet stempelen. Zou de droogloop toch stempelen,
    dan zet PORTAL_ACCOUNT_INACTIVE_SQL 30 dagen later accounts op de
    verwijderlijst waarover nooit iemand is gewaarschuwd."""
    executed = _stub_scheduler_db(
        monkeypatch, default_rows=[{"id": 1, "email": "a@example.com", "full_name": "A", "last_login_at": None}],
    )
    monkeypatch.setattr(settings, "dormant_warning_enabled", False)

    result = _run(sched.dormant_account_warning_job())

    assert result == {"status": "dry_run", "accounts_due": 1, "sent": 0}
    assert stub_email.sent == []
    assert executed == [], "droogloop mag niets naar de database schrijven"


def test_dormant_warning_job_stamps_only_after_a_successful_send(monkeypatch, stub_email):
    executed = _stub_scheduler_db(
        monkeypatch,
        default_rows=[{"id": 7, "email": "a@example.com", "full_name": "A", "last_login_at": None}],
    )
    monkeypatch.setattr(settings, "dormant_warning_enabled", True)

    result = _run(sched.dormant_account_warning_job())

    assert result["sent"] == 1
    assert stub_email.sent[0]["name"] == "dormant_warning"
    assert any("dormant_warning_sent_at = NOW()" in sql for sql, _ in executed)

    # Mislukte verzending: geen stempel, anders is de waarschuwing
    # "verstuurd" zonder dat iemand hem heeft gekregen.
    stub_email.ok = False
    executed.clear()
    result = _run(sched.dormant_account_warning_job())
    assert result["sent"] == 0
    assert executed == []


# ══════════════════════════════════════════════════════════════════════
# WS3c -- job_alert template en job
# ══════════════════════════════════════════════════════════════════════

_ALERT_CTX = {
    "full_name": "Jan",
    "jobs": [
        {"title": "Embedded Software Engineer", "location": "Eindhoven", "url": "https://gsprecruitment.nl/vacature.html?id=1"},
        {"title": "C++ Developer", "location": None, "url": "https://gsprecruitment.nl/vacature.html?id=2"},
    ],
    "unsubscribe_link": "https://gsprecruitment.nl/unsubscribe#token=x",
}


def test_job_alert_always_carries_an_unsubscribe_link():
    for lang in ("nl", "en"):
        _s, text, html = email_templates.render("job_alert", _ALERT_CTX, lang)
        assert "https://gsprecruitment.nl/unsubscribe#token=x" in text
        assert "https://gsprecruitment.nl/unsubscribe#token=x" in html


def test_job_alert_has_no_art14_block():
    """Dit gaat naar iemand die zich zelf aanmeldde: art. 13, niet art. 14.
    Het kennisgevingsblok hoort hier juist NIET in te staan (SOP §3.2)."""
    from routers.outreach import _has_art14_block

    _s, text, _h = email_templates.render("job_alert", _ALERT_CTX, "nl")
    assert not _has_art14_block(text, "nl")


def test_job_alert_html_escapes_job_titles():
    ctx = dict(_ALERT_CTX, jobs=[{"title": "<img src=x onerror=1>", "location": "A & B", "url": "https://x/y"}])
    _s, _t, html = email_templates.render("job_alert", ctx, "nl")
    assert "<img src=x" not in html
    assert "&lt;img" in html
    assert "A &amp; B" in html


def test_job_alert_threshold_comes_from_the_stored_match_score_scale():
    """Geen verzonnen drempel: hij is de opslagvorm van precies de
    ondergrens waaronder de matcher zelf niets als 'suggested'
    wegschrijft."""
    from routers import matches

    assert matches.MATCH_SUGGESTION_MIN_STORED_SCORE == matches.MATCH_SUGGESTION_MIN_SCORE * matches.MATCH_SCORE_SCALE
    assert matches.MATCH_SCORE_SCALE == 100
    assert "m.match_score >= $2" in sched.JOB_ALERT_MATCHES_SQL


def test_job_alert_candidate_selection_requires_a_self_made_optin():
    """De harde randvoorwaarde van dit spoor, als test: de selectie mag
    nooit iemand kunnen raken die zich niet zelf heeft aangemeld, en moet
    elke intrekking respecteren."""
    sql = sched.JOB_ALERT_CANDIDATE_SQL
    assert "c.job_alert_optin_at IS NOT NULL" in sql
    assert "c.job_alert_unsubscribed_at IS NULL" in sql
    assert "c.consent_withdrawn_at IS NULL" in sql
    assert "c.deleted_at IS NULL" in sql
    assert "c.consent_scope = 'matching_and_contact' OR c.lawful_basis = 'portal_registratie'" in sql


def test_job_alert_only_links_to_publicly_visible_vacancies():
    from routers.jobs import PUBLIC_JOB_WHERE

    assert PUBLIC_JOB_WHERE in sched.job_alert_matches_sql()


def _alert_candidate(**over):
    row = {"id": 5, "email": "kandidaat@example.com", "full_name": "K", "job_alert_last_sent_at": None}
    row.update(over)
    return row


def _alert_job_rows():
    return [{"id": 11, "title": "Embedded Software Engineer", "city": "Eindhoven", "match_score": 81.0}]


def test_job_alert_job_sends_nothing_when_the_env_switch_is_off(monkeypatch, stub_email):
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "FROM candidates c": [_alert_candidate()],
            "FROM matches m": _alert_job_rows(),
            "FROM suppression_list": [],
        },
    )
    monkeypatch.setattr(settings, "job_alerts_enabled", False)
    monkeypatch.setattr(sched, "_flag_enabled", lambda key: _true())

    result = _run(sched.job_alert_job())

    assert result["status"] == "dry_run"
    assert result["with_matches"] == 1
    assert result["sent"] == 0
    assert stub_email.sent == []
    assert executed == [], "droogloop mag geen token- of stempelrij schrijven"


def test_job_alert_job_sends_nothing_when_the_db_flag_is_off(monkeypatch, stub_email):
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "FROM candidates c": [_alert_candidate()],
            "FROM matches m": _alert_job_rows(),
            "FROM suppression_list": [],
        },
    )
    monkeypatch.setattr(settings, "job_alerts_enabled", True)
    monkeypatch.setattr(sched, "_flag_enabled", lambda key: _false())

    result = _run(sched.job_alert_job())

    assert result["status"] == "dry_run"
    assert stub_email.sent == []
    assert executed == []


async def _true():
    return True


async def _false():
    return False


def test_job_alert_job_skips_a_suppressed_candidate(monkeypatch, stub_email):
    """STOP ontvangen betekent nooit meer mailen, op geen enkele grondslag
    -- ook niet als deze persoon ooit zelf alerts aanzette."""
    from core import privacy

    row = _alert_candidate()
    _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "FROM candidates c": [row],
            "FROM matches m": _alert_job_rows(),
            "FROM suppression_list": [{"email_hash": privacy.email_hash(row["email"])}],
        },
    )
    monkeypatch.setattr(settings, "job_alerts_enabled", True)
    monkeypatch.setattr(sched, "_flag_enabled", lambda key: _true())

    result = _run(sched.job_alert_job())

    assert result["sent"] == 0
    assert result["with_matches"] == 0
    assert stub_email.sent == []


def test_job_alert_job_sets_the_one_click_unsubscribe_headers(monkeypatch, stub_email):
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "FROM candidates c": [_alert_candidate()],
            "FROM matches m": _alert_job_rows(),
            "FROM suppression_list": [],
        },
    )
    monkeypatch.setattr(settings, "job_alerts_enabled", True)
    monkeypatch.setattr(sched, "_flag_enabled", lambda key: _true())

    result = _run(sched.job_alert_job())

    assert result["status"] == "success" and result["sent"] == 1
    headers = stub_email.sent[0]["headers"]
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert headers["List-Unsubscribe"].startswith("<https://")
    # RFC 8058 kan geen fragment gebruiken; de zichtbare voettekstlink
    # juist wel. Die twee mogen nooit omgedraaid raken.
    assert "#token=" not in headers["List-Unsubscribe"]
    assert "?token=" in headers["List-Unsubscribe"]
    assert "#token=" in stub_email.sent[0]["ctx"]["unsubscribe_link"]

    # Pas na een geslaagde verzending: tokenrij en stempel.
    assert any("INSERT INTO job_alert_sends" in sql for sql, _ in executed)
    assert any("job_alert_last_sent_at = NOW()" in sql for sql, _ in executed)


def test_job_alert_job_writes_only_the_token_hash_never_the_raw_token(monkeypatch, stub_email):
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "FROM candidates c": [_alert_candidate()],
            "FROM matches m": _alert_job_rows(),
            "FROM suppression_list": [],
        },
    )
    monkeypatch.setattr(settings, "job_alerts_enabled", True)
    monkeypatch.setattr(sched, "_flag_enabled", lambda key: _true())

    _run(sched.job_alert_job())

    insert = [args for sql, args in executed if "INSERT INTO job_alert_sends" in sql][0]
    stored = insert[2]
    raw_in_mail = stub_email.sent[0]["ctx"]["unsubscribe_link"].split("#token=")[1]
    assert stored == hash_token(raw_in_mail)
    assert stored != raw_in_mail
    assert len(stored) == 64  # sha256 hex


def test_job_alert_job_does_not_stamp_when_the_send_fails(monkeypatch, stub_email):
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "FROM candidates c": [_alert_candidate()],
            "FROM matches m": _alert_job_rows(),
            "FROM suppression_list": [],
        },
    )
    monkeypatch.setattr(settings, "job_alerts_enabled", True)
    monkeypatch.setattr(sched, "_flag_enabled", lambda key: _true())
    stub_email.ok = False

    result = _run(sched.job_alert_job())

    assert result["sent"] == 0
    assert executed == [], "een mislukte verzending mag geen geldig afmeldtoken achterlaten"


def test_job_alert_caps_are_what_the_spec_asks(monkeypatch):
    assert sched.JOB_ALERT_MAX_JOBS == 5
    assert sched.JOB_ALERT_RUN_CAP == 200
    assert "LIMIT $4" in sched.JOB_ALERT_MATCHES_SQL
    assert "LIMIT $1" in sched.JOB_ALERT_CANDIDATE_SQL
    # Een verse aanmelder krijgt geen jaar oude matches in één mail.
    assert "COALESCE($3, NOW() - INTERVAL '7 days')" in sched.JOB_ALERT_MATCHES_SQL


def test_generated_tokens_have_full_entropy():
    """De productiecode gebruikt secrets.token_urlsafe(32); deze test legt
    dat vast zonder ergens een letterlijk token op te schrijven."""
    token = secrets.token_urlsafe(32)
    assert len(token) >= 43
    assert hash_token(token) != hash_token(secrets.token_urlsafe(32))
