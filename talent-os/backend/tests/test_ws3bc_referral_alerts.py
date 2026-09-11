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
import json
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
    ctx = {"full_name": "Jan", "link": "https://gsprecruitment.nl/candidate/", "deadline": "2026-10-11"}
    _s, nl, _h = email_templates.render("dormant_warning", ctx, "nl")
    _s, en, _h = email_templates.render("dormant_warning", ctx, "en")

    assert "2026-10-11" in nl and "2026-10-11" in en
    assert "verwijderlijst" in nl and "deletion list" in en
    assert "beheerder" in nl and "administrator" in en
    assert "Inloggen is genoeg" in nl and "Logging in is enough" in en


def test_dormant_warning_does_not_claim_a_term_the_job_does_not_use():
    """B12. De tekst noemde vier keer "18 maanden" terwijl de job vanaf 17
    maanden waarschuwt, en sinds B3 zonder bovengrens -- dus voor een deel
    van de ontvangers was dat getal simpelweg onwaar. De datum is wat voor
    iedereen klopt en is ook het enige waar de ontvanger iets mee moet."""
    ctx = {"full_name": "Jan", "link": "https://gsprecruitment.nl/candidate/", "deadline": "2026-10-11"}
    for lang in ("nl", "en"):
        subject, text, html = email_templates.render("dormant_warning", ctx, lang)
        for part in (subject, text, html):
            assert "18 maanden" not in part and "18 months" not in part
        assert "2026-10-11" in text and "2026-10-11" in html


def test_referral_confirm_promises_only_what_the_code_does():
    """B11. Hier stond "Doet u niets, dan verwijderen wij uw gegevens
    weer", en dat gebeurt niet: de rij blijft staan, valt na 3 maanden in
    REFERRAL_NO_RESPONSE_SQL en komt dan op de maandelijkse lijst die een
    beheerder afhandelt. Dezelfde eis als aan dormant_warning hierboven,
    voor de tweede mail die iets over verwijderen zegt."""
    _s, nl, nl_html = email_templates.render("referral_confirm", _REFERRAL_CTX, "nl")
    _s, en, en_html = email_templates.render("referral_confirm", _REFERRAL_CTX, "en")

    for part in (nl, nl_html):
        assert "verwijderen wij uw gegevens weer" not in part
        assert "3 maanden" in part
        assert "verwijderlijst" in part and "beheerder" in part
    for part in (en, en_html):
        assert "we will delete your details again" not in part
        assert "3 months" in part
        assert "deletion list" in part and "administrator" in part


def test_dormant_warning_link_points_at_a_page_that_exists():
    """B6. De link wees naar candidate/login.html, een pagina die niet
    bestaat: het portaal is website/candidate/index.html met een
    inlogmodal. Een waarschuwing "log in om je account te houden" die naar
    een 404 wijst is erger dan geen waarschuwing, dus deze test kijkt naar
    het bestandssysteem en niet naar een string."""
    website = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "website",
    )
    path = sched._DORMANT_WARNING_PATH
    assert path.startswith("/") and path.endswith("/")
    assert os.path.isfile(os.path.join(website, path.strip("/"), "index.html"))
    assert not os.path.exists(os.path.join(website, "candidate", "login.html"))

    link = sched._dormant_warning_link()
    assert link.startswith(settings.frontend_url) and link.endswith(path)


def test_dormant_warning_sql_has_no_upper_bound_on_the_window():
    """B3, besluit van de eigenaar: de bovengrens van 18 maanden is eraf.
    Met die grens viel iedereen die bij invoering al langer dan 18 maanden
    sliep permanent buiten het venster: nooit gewaarschuwd, dus nooit
    beoordeeld, dus de beloofde termijn werd voor precies die achterstand
    nooit gehaald."""
    sql = retention.DORMANT_WARNING_SQL
    assert "u.last_login_at <= (NOW() - INTERVAL '17 months')" in sql
    assert "INTERVAL '18 months'" not in sql
    assert "u.role = 'candidate'" in sql
    assert "u.deleted_at IS NULL" in sql
    # De idempotentie die de bovengrens verving.
    assert "u.dormant_warning_sent_at IS NULL OR u.dormant_warning_sent_at < u.last_login_at" in sql
    # De beschermende guards komen letterlijk uit core/retention.py, niet
    # uit een tweede handgeschreven kopie.
    assert retention._CANDIDATE_ENGAGEMENT_SIGNALS_SQL in sql
    # CR L2: plafond in SQL, en een aparte telling zonder plafond.
    assert "LIMIT $1" in sql
    assert "COUNT(*) AS due" in retention.DORMANT_WARNING_COUNT_SQL
    assert "LIMIT" not in retention.DORMANT_WARNING_COUNT_SQL


def test_dormant_warning_selector_lives_next_to_the_selector_it_feeds():
    """R7: één bestand voor beide helften van dezelfde belofte.
    services/scheduler.py bouwde zijn eigen kopie met een private
    constante uit core/retention.py."""
    assert sched.retention.DORMANT_WARNING_SQL is retention.DORMANT_WARNING_SQL
    assert not hasattr(sched, "DORMANT_WARNING_SQL")


def test_dormant_warning_grace_matches_the_retention_selector():
    """De 30 dagen in de mail en de 30 dagen die de verwijderlijst-selector
    eist, moeten hetzelfde getal zijn."""
    assert sched.DORMANT_WARNING_GRACE_DAYS == 30
    assert "INTERVAL '30 days'" in retention.PORTAL_ACCOUNT_INACTIVE_SQL


def _stub_scheduler_db(monkeypatch, rows_by_sql=None, default_rows=None):
    """fetch_all/fetch_one/execute op services.scheduler vervangen. Geeft
    de lijst met uitgevoerde SCHRIJF-statements terug, zodat een test kan
    bewijzen dat er niets is weggeschreven.

    fetch_one hoort daar sinds B7 bij: de tokenrij wordt met INSERT ...
    RETURNING geschreven en is dus een schrijfactie die langs fetch_one
    loopt. Een lezende fetch_one (de COUNT van dormant_account_warning_
    job) belandt niet in `executed` -- anders zou "droogloop schrijft
    niets" op een telling stuklopen."""
    executed = []

    def _match(sql):
        if rows_by_sql:
            for needle, rows in rows_by_sql.items():
                if needle in sql:
                    return list(rows)
        return None

    async def _fake_fetch_all(sql, *args):
        rows = _match(sql)
        return rows if rows is not None else list(default_rows or [])

    async def _fake_fetch_one(sql, *args):
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            executed.append((sql, args))
            return {"id": 1}
        rows = _match(sql)
        if rows is None and "COUNT(*) AS due" in sql:
            return {"due": len(default_rows or [])}
        if rows is None:
            rows = list(default_rows or [])
        return rows[0] if rows else None

    async def _fake_execute(sql, *args):
        executed.append((sql, args))
        return "UPDATE 1"

    monkeypatch.setattr(sched, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(sched, "fetch_one", _fake_fetch_one)
    monkeypatch.setattr(sched, "execute", _fake_execute)
    return executed


def _dormant_rows(*rows):
    """rows_by_sql voor dormant_account_warning_job: de users-selectie, de
    telling en de blokkeerlijst zijn drie verschillende queries en mogen
    niet op één default terugvallen."""
    # Volgorde telt: de telling en de selectie delen hun FROM/WHERE, dus
    # de specifiekere naald staat voorop (dicts behouden invoegvolgorde).
    return {
        "COUNT(*) AS due": [{"due": len(rows)}],
        "FROM suppression_list": [],
        "FROM users u": list(rows),
    }


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
        monkeypatch,
        rows_by_sql=_dormant_rows({"id": 1, "email": "a@example.com", "full_name": "A", "last_login_at": None}),
    )
    monkeypatch.setattr(settings, "dormant_warning_enabled", False)

    result = _run(sched.dormant_account_warning_job())

    assert result == {
        "status": "dry_run", "accounts_due": 1, "selected": 1,
        "sent": 0, "suppressed": 0, "failed": 0,
    }
    assert stub_email.sent == []
    assert executed == [], "droogloop mag niets naar de database schrijven"


def test_dormant_warning_dry_run_counts_the_whole_backlog_not_the_capped_page(monkeypatch, stub_email):
    """CR L2: `accounts_due` komt uit een telling zonder plafond. Telde hij
    na het knippen, dan meldde een achterstand van duizenden accounts
    netjes DORMANT_WARNING_CAP en verdween precies het getal waar de
    eigenaar naar kijkt."""
    page = [
        {"id": i, "email": f"a{i}@example.com", "full_name": "A", "last_login_at": None}
        for i in range(sched.DORMANT_WARNING_CAP)
    ]
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "COUNT(*) AS due": [{"due": 4321}],
            "FROM suppression_list": [],
            "FROM users u": page,
        },
    )
    monkeypatch.setattr(settings, "dormant_warning_enabled", False)

    result = _run(sched.dormant_account_warning_job())

    assert result["accounts_due"] == 4321
    assert result["selected"] == sched.DORMANT_WARNING_CAP
    assert executed == []


def test_dormant_warning_job_handles_a_suppressed_account_without_mail(monkeypatch, stub_email):
    """B3. Wie STOP heeft gestuurd, krijgt geen bericht meer, op geen
    enkele grondslag -- ook geen waarschuwing over zijn eigen account.
    Maar overslaan is niet hetzelfde als niets doen: de rij wordt
    mailloos afgehandeld (`dormant_warning_skipped_at` plus een
    audit-regel), zodat hij de selector verlaat in plaats van morgen weer
    vooraan te staan, en zodat hij na dezelfde 30 dagen de
    beoordelingslijst bereikt."""
    from core import privacy

    row = {"id": 3, "email": "stop@example.com", "full_name": "S", "last_login_at": None}
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "COUNT(*) AS due": [{"due": 1}],
            "FROM suppression_list": [{"email_hash": privacy.email_hash(row["email"])}],
            "FROM users u": [row],
        },
    )
    monkeypatch.setattr(settings, "dormant_warning_enabled", True)

    result = _run(sched.dormant_account_warning_job())

    assert result["sent"] == 0
    assert result["suppressed"] == 1
    assert result["selected"] == 1
    assert stub_email.sent == []

    stamped = [sql for sql, _ in executed if "dormant_warning_skipped_at = NOW()" in sql]
    assert len(stamped) == 1, "een geblokkeerd account moet worden gestempeld, niet stil overgeslagen"

    audits = [(sql, args) for sql, args in executed if "INSERT INTO audit_log" in sql]
    assert len(audits) == 1
    _sql, args = audits[0]
    assert args[0] == "dormant_warning_suppressed"
    changes = json.loads(args[3])
    assert changes["email_hash"] == privacy.email_hash(row["email"])
    assert row["email"] not in args[3], "geen adres in de audit-regel, alleen de hash"


def test_dormant_warning_job_stamps_only_after_a_successful_send(monkeypatch, stub_email):
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql=_dormant_rows({"id": 7, "email": "a@example.com", "full_name": "A", "last_login_at": None}),
    )
    monkeypatch.setattr(settings, "dormant_warning_enabled", True)

    result = _run(sched.dormant_account_warning_job())

    assert result["sent"] == 1
    assert stub_email.sent[0]["name"] == "dormant_warning"
    assert any("dormant_warning_sent_at = NOW()" in sql for sql, _ in executed)

    # Mislukte verzending: geen verzendstempel, anders is de waarschuwing
    # "verstuurd" zonder dat iemand hem heeft gekregen.
    stub_email.ok = False
    executed.clear()
    result = _run(sched.dormant_account_warning_job())
    assert result["sent"] == 0
    assert not any("dormant_warning_sent_at = NOW()" in sql for sql, _ in executed)


def test_dormant_warning_job_counts_a_failed_send_as_an_attempt(monkeypatch, stub_email):
    """B4. Een structureel onbezorgbaar adres mag zijn plek onder het
    dagplafond niet houden: elke mislukte verzending hoogt
    `dormant_warning_attempts` op, en _DORMANT_WARNING_WHERE_SQL laat de
    rij na drie pogingen vallen."""
    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql=_dormant_rows({"id": 9, "email": "dead@example.com", "full_name": "D", "last_login_at": None}),
    )
    monkeypatch.setattr(settings, "dormant_warning_enabled", True)
    stub_email.ok = False

    result = _run(sched.dormant_account_warning_job())

    assert result["sent"] == 0
    assert result["failed"] == 1
    bumped = [
        sql for sql, _ in executed
        if "dormant_warning_attempts = dormant_warning_attempts + 1" in sql
    ]
    assert len(bumped) == 1, "een mislukte verzending moet de teller ophogen"


def test_dormant_warning_selector_excludes_skipped_and_exhausted_rows():
    """De twee clausules die B3 en B4 waarmaken staan in de selector zelf,
    niet in Python na de LIMIT -- anders verbruikt zo'n rij elke dag
    opnieuw een plek onder het dagplafond."""
    from core import retention

    sql = retention.DORMANT_WARNING_SQL
    assert "dormant_warning_skipped_at IS NULL OR u.dormant_warning_skipped_at < u.last_login_at" in sql
    assert "u.dormant_warning_attempts < 3" in sql
    # En de telling deelt datzelfde WHERE, anders meldt de droogloop een
    # achterstand die de job zelf nooit oppakt.
    assert "dormant_warning_attempts < 3" in retention.DORMANT_WARNING_COUNT_SQL


def test_portal_account_inactive_accepts_a_skipped_warning():
    """Een STOP is een verbod op berichten, geen toestemming tot
    onbeperkt bewaren: een geblokkeerd slapend account bereikt de
    maandelijkse beoordelingslijst na dezelfde 18 maanden plus 30 dagen,
    langs `dormant_warning_skipped_at` in plaats van
    `dormant_warning_sent_at`."""
    from core import retention

    sql = retention.PORTAL_ACCOUNT_INACTIVE_SQL
    assert "dormant_warning_skipped_at IS NOT NULL" in sql
    assert "u.dormant_warning_skipped_at < (NOW() - INTERVAL '30 days')" in sql
    assert "u.dormant_warning_sent_at < (NOW() - INTERVAL '30 days')" in sql


def test_every_login_path_resets_the_dormant_attempt_counter():
    """B4: de teller hoort bij een inactiviteitscyclus en een login begint
    een nieuwe. Alle vier de inlogpaden gebruiken hetzelfde statement uit
    core/retention.py; een met de hand uitgetypte vijfde kopie zou een
    account dat via dat ene pad inlogt permanent boven de drempel laten
    hangen."""
    import re
    from core import retention

    assert "dormant_warning_attempts = 0" in retention.LOGIN_STAMP_SQL

    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hand_written = []
    for name in ("routers/auth.py", "routers/mfa.py"):
        with open(os.path.join(backend_root, name), encoding="utf-8") as fh:
            body = fh.read()
        hand_written += [
            f"{name}: {m}" for m in re.findall(r'"UPDATE users SET last_login_at = NOW\(\)[^"]*"', body)
        ]
    assert hand_written == [], hand_written


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

    # B7: de tokenrij vóór de verzending, de stempel erna.
    sqls = [sql for sql, _ in executed]
    assert any("INSERT INTO job_alert_sends" in sql for sql in sqls)
    assert any("job_alert_last_sent_at = NOW()" in sql for sql in sqls)
    assert not any("DELETE FROM job_alert_sends" in sql for sql in sqls)


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
    """B7. De tokenrij wordt nu vóór de verzending geschreven -- anders kon
    een mislukte INSERT ná een geslaagde verzending een dode afmeldlink
    achterlaten, onzichtbaar omdat het afmeldendpoint met opzet altijd
    hetzelfde antwoordt. Mislukt de verzending, dan gaat die rij dus weer
    weg, en de stempel komt er sowieso niet."""
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
    sqls = [sql for sql, _ in executed]
    assert any("INSERT INTO job_alert_sends" in sql for sql in sqls)
    assert any("DELETE FROM job_alert_sends" in sql for sql in sqls)
    assert not any("job_alert_last_sent_at" in sql for sql in sqls), (
        "een mislukte verzending mag het venster van morgen niet dichtschuiven"
    )


def test_job_alert_job_writes_the_token_row_before_it_sends(monkeypatch, stub_email):
    """B7, de volgorde zelf. Een string-assertie kan hem niet zien, dus
    deze test legt het moment van verzenden vast tussen de statements."""
    order = []

    executed = _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={
            "FROM candidates c": [_alert_candidate()],
            "FROM matches m": _alert_job_rows(),
            "FROM suppression_list": [],
        },
    )

    real_send = stub_email.send_template

    async def _tracking_send(*a, **kw):
        order.append(("send", len(executed)))
        return await real_send(*a, **kw)

    stub_email.send_template = _tracking_send
    monkeypatch.setattr(settings, "job_alerts_enabled", True)
    monkeypatch.setattr(sched, "_flag_enabled", lambda key: _true())

    _run(sched.job_alert_job())

    statements_before_send = order[0][1]
    assert statements_before_send == 1
    assert "INSERT INTO job_alert_sends" in executed[0][0]


def test_job_alert_suppression_check_survives_two_rows_with_one_address(monkeypatch):
    """B8. De map ging van hash naar id, dus twee kandidaatrijen met
    hetzelfde adres lieten er één door -- en die kreeg zijn mail, terwijl
    het adres op de blokkeerlijst stond. Precies de fout die dit hulpje
    moet voorkomen, alleen in Python."""
    from core import privacy

    shared = "dubbel@example.com"
    rows = [
        {"id": 1, "email": shared},
        {"id": 2, "email": shared},
        {"id": 3, "email": "anders@example.com"},
    ]
    _stub_scheduler_db(
        monkeypatch,
        rows_by_sql={"FROM suppression_list": [{"email_hash": privacy.email_hash(shared)}]},
    )

    assert _run(sched._job_alert_suppressed_ids(rows)) == {1, 2}


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


# ══════════════════════════════════════════════════════════════════════
# B13 -- de guards die niemand testte
# ══════════════════════════════════════════════════════════════════════
#
# Elk van deze guards was op zichzelf juist, maar door geen enkele test
# gedekt: wie hem morgen weghaalt, ziet een groene suite. Ze zijn stuk
# voor stuk met een mutatie gecontroleerd (guard eruit -> test faalt);
# welke, staat in het eindrapport van deze ronde.


def test_job_alerts_switch_refuses_a_non_candidate_role():
    """routers/candidate.py's rolcheck. get_verified_user bewijst alleen
    dat het account bestaat en geverifieerd is -- een klant- of
    beheerdersaccount haalt die dependency net zo goed, en zou zonder deze
    regel een kandidaatvoorkeur zetten op de kandidaatrij die
    get_or_create_candidate_id voor hem zou aanmaken."""
    import asyncio

    from fastapi import HTTPException
    from models.schemas import CandidateJobAlertsUpdate
    from routers import candidate as candidate_router

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            candidate_router.update_job_alerts(
                CandidateJobAlertsUpdate(enabled=True),
                current_user={"id": 1, "role": "client", "email": "c@example.com"},
            )
        )
    assert exc.value.status_code == 403


def _stub_candidate_router_db(monkeypatch, row):
    """fetch_one/execute/_get_candidate_id op routers.candidate."""
    calls = []
    from routers import candidate as candidate_router

    async def _fake_get_candidate_id(user_id):
        return 42

    async def _fake_fetch_one(sql, *args):
        calls.append((sql, args))
        return row

    async def _fake_execute(sql, *args):
        calls.append((sql, args))
        return "INSERT 1"

    monkeypatch.setattr(candidate_router, "_get_candidate_id", _fake_get_candidate_id)
    monkeypatch.setattr(candidate_router, "fetch_one", _fake_fetch_one)
    monkeypatch.setattr(candidate_router, "execute", _fake_execute)
    return calls


def test_job_alerts_switch_writes_json_not_a_raw_dict_to_the_audit_log(monkeypatch):
    """De jsonb-valkuil uit CLAUDE.md (commit 72b4bcd): audit_log.changes
    is jsonb en asyncpg kan een ruwe dict niet binden. Zonder json.dumps
    crasht deze endpoint pas in productie, op de audit-regel, nadat de
    voorkeur al is weggeschreven."""
    import asyncio
    import json as _json

    from models.schemas import CandidateJobAlertsUpdate
    from routers import candidate as candidate_router

    calls = _stub_candidate_router_db(
        monkeypatch,
        {"id": 42, "job_alert_optin_at": "now", "job_alert_unsubscribed_at": None, "eligible": True},
    )
    asyncio.run(
        candidate_router.update_job_alerts(
            CandidateJobAlertsUpdate(enabled=True),
            current_user={"id": 1, "role": "candidate", "email": "k@example.com"},
        )
    )

    audit = [args for sql, args in calls if "INSERT INTO audit_log" in sql]
    assert audit, "elke mutatie schrijft een audit-regel"
    changes = audit[0][-1]
    assert isinstance(changes, str), "changes moet json.dumps'd zijn, nooit een ruwe dict"
    assert _json.loads(changes)["source"] == "portal"


def test_job_alerts_switch_reports_eligibility_from_the_shared_selector(monkeypatch):
    """CR R6: het portaal moet kunnen tonen dat de schakelaar aan staat
    terwijl de selector deze persoon nooit oppikt."""
    import asyncio

    from models.schemas import CandidateJobAlertsUpdate
    from routers import candidate as candidate_router

    _stub_candidate_router_db(
        monkeypatch,
        {"id": 42, "job_alert_optin_at": "now", "job_alert_unsubscribed_at": None, "eligible": False},
    )
    out = asyncio.run(
        candidate_router.update_job_alerts(
            CandidateJobAlertsUpdate(enabled=True),
            current_user={"id": 1, "role": "candidate", "email": "k@example.com"},
        )
    )

    assert out["enabled"] is True
    assert out["eligible"] is False
    # Niet nagebouwd maar letterlijk gedeeld met job_alert_job, en de
    # constante staat in core/retention.py zodat deze router niet de hele
    # scheduler hoeft te importeren (R3).
    assert retention.JOB_ALERT_ELIGIBILITY_SQL in sched.JOB_ALERT_CANDIDATE_SQL
    assert candidate_router.JOB_ALERT_ELIGIBILITY_SQL is retention.JOB_ALERT_ELIGIBILITY_SQL


def test_job_alert_selection_skips_a_candidate_without_an_address():
    """`AND c.email IS NOT NULL`: een geanonimiseerde of nooit ingevulde
    kandidaatrij heeft geen adres, en send_template zou er een lege
    ontvanger van maken."""
    assert "c.email IS NOT NULL" in sched.JOB_ALERT_CANDIDATE_SQL


def test_job_alert_selection_requires_a_consent_that_still_runs():
    """B4: `consent_scope` zegt alleen dat er ooit toestemming is gegeven,
    niet dat hij nog geldt. Talentpool-toestemming verloopt na 12 maanden
    zonder dat er een kolom verandert."""
    sql = sched.JOB_ALERT_CANDIDATE_SQL
    assert "c.consent_talentpool_until IS NOT NULL AND c.consent_talentpool_until > NOW()" in sql
    assert "c.lawful_basis = 'portal_registratie'" in sql


def test_dormant_warning_job_passes_the_cap_to_the_query(monkeypatch, stub_email):
    """Het dagplafond zit in SQL (LIMIT $1) en niet meer in een Python-
    slice, dus de test kijkt naar wat de job meegeeft."""
    seen = []

    async def _fake_fetch_all(sql, *args):
        seen.append((sql, args))
        if "FROM suppression_list" in sql:
            return []
        return []

    async def _fake_fetch_one(sql, *args):
        return {"due": 0}

    monkeypatch.setattr(sched, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(sched, "fetch_one", _fake_fetch_one)
    monkeypatch.setattr(settings, "dormant_warning_enabled", False)

    _run(sched.dormant_account_warning_job())

    selects = [args for sql, args in seen if "FROM users u" in sql]
    assert selects and selects[0] == (sched.DORMANT_WARNING_CAP,)


def test_one_click_url_uses_the_api_host_not_the_website_host():
    """De List-Unsubscribe-URL moet naar de API wijzen: een mailclient
    POST'et hem rechtstreeks, zonder browser en zonder de frontend. Wees
    hij naar settings.frontend_url, dan kwam die POST op een statische
    host terecht en deed het afmelden niets."""
    footer, one_click = sched._job_alert_unsubscribe_links(
        secrets.token_urlsafe(32), secrets.token_urlsafe(32),
    )
    assert one_click.startswith(settings.api_base_url)
    assert "/api/public/unsubscribe?" in one_click
    assert footer.startswith(settings.frontend_url)


def test_the_two_unsubscribe_links_never_carry_the_same_token():
    """B1. Zolang de voettekstlink en de List-Unsubscribe-URL hetzelfde
    token droegen, kon wie een one-click-URL uit een log haalde datzelfde
    token in de body plakken en `scope=all` bereiken. Twee losse tokens
    maken van "welke scope mag dit" een eigenschap van het token."""
    footer_token = secrets.token_urlsafe(32)
    oneclick_token = secrets.token_urlsafe(32)
    footer, one_click = sched._job_alert_unsubscribe_links(footer_token, oneclick_token)

    assert f"#token={footer_token}" in footer
    assert footer_token not in one_click, "het fragmenttoken mag nooit in een querystring staan"
    assert f"token={oneclick_token}" in one_click
    assert oneclick_token not in footer


def test_unsubscribe_audit_row_is_skipped_for_an_unknown_token():
    """`WHERE $1::int IS NOT NULL` op de audit-INSERT: een onbekend token
    is geen gebeurtenis, en zonder deze regel kan iedereen met een
    verzonnen token de audit-log volschrijven -- ruis die een aanvaller
    zelf produceert, in de tabel waar een incident juist uit gelezen moet
    worden."""
    import inspect

    from routers import public as public_router

    src = inspect.getsource(public_router.unsubscribe)
    assert "INSERT INTO audit_log" in src
    assert "WHERE $1::int IS NOT NULL" in src


def test_unsubscribe_token_is_single_use_and_expires():
    """`used_at IS NULL` maakt hergebruik onmogelijk zonder een aparte
    check (die zelf weer een tijdsverschil zou zijn), en sinds R3 verloopt
    een token na 90 dagen."""
    import inspect

    from routers import public as public_router

    src = inspect.getsource(public_router.unsubscribe)
    assert "UPDATE job_alert_sends SET used_at = NOW()" in src
    assert "used_at IS NULL" in src
    assert "sent_at > NOW() - INTERVAL '90 days'" in src


def test_unsubscribe_scope_falls_back_to_the_narrowest():
    """Een onbekende scope betekent 'alerts', nooit 'all': een afmelding
    mag nooit méér intrekken dan de betrokkene bedoelde. De
    scope-validatie zelf staat in models/schemas.py."""
    from models.schemas import UNSUBSCRIBE_SCOPES
    from routers.public import _unsubscribe_field

    assert UNSUBSCRIBE_SCOPES == ("alerts", "all")
    assert _unsubscribe_field("scope", "bogus") is None
    assert _unsubscribe_field("scope", "all") == "all"
    # R1: een onbruikbare scope sleept het token er niet mee in.
    token = secrets.token_urlsafe(32)
    assert _unsubscribe_field("token", token) == token


def test_talentpool_confirm_never_reenrolls_an_unsubscriber():
    """Een afmelding is een intrekking. Alleen de persoon zelf, ingelogd,
    kan hem opheffen (PUT /api/v1/candidate/job-alerts); een tweede
    talentpool-bevestiging met het alert-vinkje aan mag dat niet."""
    import inspect

    from routers import public as public_router

    src = inspect.getsource(public_router.talentpool_confirm)
    assert "WHEN $7 AND job_alert_unsubscribed_at IS NULL" in src


def test_confirmed_referral_becomes_a_talentpool_consent():
    """B1: zonder deze omzetting hield een bevestigde referral
    lawful_basis='toestemming_referral' en viel hij buiten elke
    retentierij, buiten de matching-poort en buiten de
    outreach-weigering."""
    import inspect

    from routers import public as public_router

    src = inspect.getsource(public_router.talentpool_confirm)
    assert 'is_referral and existing["lawful_basis"] == "toestemming_referral"' in src
    # De rij waar hij daarna wél in valt.
    assert "lawful_basis = 'opt_in_talentpool'" in retention.TALENTPOOL_EXPIRED_SQL
