"""
WS3 -- services/email_templates.py: snapshot assertions per template/taal
plus the html.escape() guarantee.

Pure unit tests, no DB/network -- render() is a pure function of
(name, ctx, lang). Same style as tests/test_ws_e2_e3_verification.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest

from services import email_templates


# ── verify_email ──────────────────────────────────────────────────────────

def test_verify_email_nl_snapshot():
    subject, text, html = email_templates.render(
        "verify_email", {"full_name": "Jan Jansen", "link": "https://gsprecruitment.nl/verify?token=abc", "ttl_hours": 24}, "nl",
    )
    assert subject == "Bevestig je e-mailadres - GSP Recruitment"
    assert "Beste Jan Jansen," in text
    assert "https://gsprecruitment.nl/verify?token=abc" in text
    assert "24 uur geldig" in text
    assert "GSP Recruitment, KvK 75545586, info@gsprecruitment.nl" in html


def test_verify_email_en_snapshot():
    subject, text, html = email_templates.render(
        "verify_email", {"full_name": "Jane Doe", "link": "https://gsprecruitment.nl/verify?token=xyz", "ttl_hours": 24}, "en",
    )
    assert subject == "Confirm your e-mail address - GSP Recruitment"
    assert "Dear Jane Doe," in text
    assert "https://gsprecruitment.nl/verify?token=xyz" in text
    assert "valid for 24 hours" in text


def test_verify_email_defaults_to_nl_for_unknown_lang():
    subject_nl, _, _ = email_templates.render("verify_email", {"full_name": "X", "link": "l", "ttl_hours": 1}, "nl")
    subject_unknown, _, _ = email_templates.render("verify_email", {"full_name": "X", "link": "l", "ttl_hours": 1}, "de")
    assert subject_unknown == subject_nl


# ── reset_password ────────────────────────────────────────────────────────

def test_reset_password_nl_snapshot():
    subject, text, html = email_templates.render(
        "reset_password", {"full_name": "Jan Jansen", "link": "https://gsprecruitment.nl/reset-password?token=abc", "ttl_hours": 1}, "nl",
    )
    assert subject == "Wachtwoord resetten - GSP Recruitment"
    assert "wachtwoord reset aangevraagd" in text
    assert "https://gsprecruitment.nl/reset-password?token=abc" in text
    assert "1 uur geldig" in text


def test_reset_password_en_snapshot():
    subject, text, html = email_templates.render(
        "reset_password", {"full_name": "Jane Doe", "link": "https://gsprecruitment.nl/reset-password?token=xyz", "ttl_hours": 1}, "en",
    )
    assert subject == "Reset your password - GSP Recruitment"
    assert "You requested a password reset" in text
    assert "https://gsprecruitment.nl/reset-password?token=xyz" in text


# ── talentpool_confirm ────────────────────────────────────────────────────

def test_talentpool_confirm_without_job_title():
    subject, text, html = email_templates.render(
        "talentpool_confirm", {"link": "https://gsprecruitment.nl/talentpool-confirm#token=abc", "ttl_hours": 48, "job_title": None}, "nl",
    )
    assert subject == "Bevestig je talentpool-aanmelding - GSP Recruitment"
    # No job line at all when job_title is None/absent -- and, above all,
    # $job_line must not have swallowed the next word (regression guard
    # for the string.Template concatenation bug this spoor found: a bare
    # "$job_line" directly followed by "Bevestig" is parsed as one longer
    # identifier "job_lineBevestig" and substitute() raises KeyError).
    assert "Bevestig via onderstaande link" in text
    assert "vacature" not in text.lower()


def test_talentpool_confirm_with_job_title_nl():
    subject, text, html = email_templates.render(
        "talentpool_confirm",
        {"link": "https://gsprecruitment.nl/talentpool-confirm#token=abc", "ttl_hours": 48, "job_title": "Senior Embedded C++ Engineer"},
        "nl",
    )
    assert "Je reageerde op de vacature: Senior Embedded C++ Engineer." in text
    assert "Bevestig via onderstaande link" in text
    assert "Senior Embedded C++ Engineer" in html


def test_talentpool_confirm_with_job_title_en():
    subject, text, html = email_templates.render(
        "talentpool_confirm",
        {"link": "https://gsprecruitment.nl/talentpool-confirm#token=abc", "ttl_hours": 48, "job_title": "Senior Embedded C++ Engineer"},
        "en",
    )
    assert "You applied to the vacancy: Senior Embedded C++ Engineer." in text
    assert "Please confirm via the link below" in text


# ── talentpool_reminder ───────────────────────────────────────────────────

def test_talentpool_reminder_nl_snapshot():
    subject, text, html = email_templates.render(
        "talentpool_reminder", {"full_name": "Jan Jansen", "link": "https://gsprecruitment.nl/kandidaten#talentpoolOptin"}, "nl",
    )
    assert subject == "Je talentpool-aanmelding loopt bijna af - GSP Recruitment"
    assert "bewaartermijn 12 maanden" in text
    assert "https://gsprecruitment.nl/kandidaten#talentpoolOptin" in text


def test_talentpool_reminder_handles_empty_full_name():
    """scheduler.py passes full_name="" for a candidate row with no
    full_name on file -- must not raise, and the empty value must not
    silently become the literal string "None"."""
    subject, text, html = email_templates.render(
        "talentpool_reminder", {"full_name": "", "link": "https://gsprecruitment.nl/kandidaten#talentpoolOptin"}, "nl",
    )
    assert "None" not in text
    assert "Beste ,\n\n" in text


# ── client_team_invite ────────────────────────────────────────────────────

def test_client_team_invite_nl_snapshot():
    subject, text, html = email_templates.render(
        "client_team_invite",
        {"full_name": "Piet", "inviter_company": "Acme B.V.", "link": "https://gsprecruitment.nl/verify?token=abc&mode=set-password"},
        "nl",
    )
    assert subject == "Uitnodiging teamlid - GSP Recruitment"
    assert "team van Acme B.V." in text
    assert "24 uur geldig" in text


# ── owner_notify ───────────────────────────────────────────────────────────

def test_owner_notify_snapshot():
    subject, text, html = email_templates.render(
        "owner_notify",
        {"event_label": "Nieuwe lead", "detail": "Interesse: embedded", "deeplink": "https://gsprecruitment.nl/admin/#leads"},
        "nl",
    )
    assert subject == "Nieuwe lead - GSP Recruitment admin"
    assert "Interesse: embedded" in text
    assert "https://gsprecruitment.nl/admin/#leads" in text


# ── Unknown template / missing ctx field ──────────────────────────────────

def test_render_raises_keyerror_for_unknown_template():
    with pytest.raises(KeyError):
        email_templates.render("does_not_exist", {}, "nl")


def test_render_raises_for_missing_required_ctx_field():
    with pytest.raises(KeyError):
        email_templates.render("verify_email", {"full_name": "X"}, "nl")  # no link/ttl_hours


# ── html.escape() on every ctx value (injection guard) ────────────────────

_XSS_PAYLOAD = "<b>owned</b>"


@pytest.mark.parametrize("lang", ["nl", "en"])
def test_verify_email_html_escapes_full_name(lang):
    _, _, html = email_templates.render(
        "verify_email", {"full_name": _XSS_PAYLOAD, "link": "https://x/y", "ttl_hours": 1}, lang,
    )
    assert "<b>owned</b>" not in html
    assert "&lt;b&gt;owned&lt;/b&gt;" in html


def test_reset_password_html_escapes_full_name():
    _, _, html = email_templates.render(
        "reset_password", {"full_name": _XSS_PAYLOAD, "link": "https://x/y", "ttl_hours": 1}, "nl",
    )
    assert "<b>owned</b>" not in html
    assert "&lt;b&gt;owned&lt;/b&gt;" in html


def test_talentpool_confirm_html_escapes_job_title():
    _, _, html = email_templates.render(
        "talentpool_confirm", {"link": "https://x/y", "ttl_hours": 1, "job_title": _XSS_PAYLOAD}, "nl",
    )
    assert "<b>owned</b>" not in html
    assert "&lt;b&gt;owned&lt;/b&gt;" in html


def test_talentpool_reminder_html_escapes_full_name():
    _, _, html = email_templates.render(
        "talentpool_reminder", {"full_name": _XSS_PAYLOAD, "link": "https://x/y"}, "nl",
    )
    assert "<b>owned</b>" not in html
    assert "&lt;b&gt;owned&lt;/b&gt;" in html


def test_client_team_invite_html_escapes_full_name_and_company():
    _, _, html = email_templates.render(
        "client_team_invite", {"full_name": _XSS_PAYLOAD, "inviter_company": _XSS_PAYLOAD, "link": "https://x/y"}, "nl",
    )
    assert "<b>owned</b>" not in html
    assert html.count("&lt;b&gt;owned&lt;/b&gt;") == 2


def test_owner_notify_html_escapes_event_label_and_detail():
    _, _, html = email_templates.render(
        "owner_notify", {"event_label": _XSS_PAYLOAD, "detail": _XSS_PAYLOAD, "deeplink": "https://x/y"}, "nl",
    )
    assert "<b>owned</b>" not in html
    assert html.count("&lt;b&gt;owned&lt;/b&gt;") == 2


def test_html_escapes_the_link_itself():
    """The link is rendered inside an href= attribute AND as its own
    visible label -- both must be escaped, not just one."""
    malicious_link = 'https://x/y"><script>alert(1)</script>'
    _, _, html = email_templates.render(
        "verify_email", {"full_name": "X", "link": malicious_link, "ttl_hours": 1}, "nl",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── Bilingual default (chief-of-staff FIX FIRST 2) ────────────────────────
# send_template()'s call sites never pass `lang` -- the backend does not
# know the recipient's language (UserRegister has no language field) --
# so render()'s default must carry both languages in one message, the way
# the five original f-string bodies on main did, instead of silently
# dropping to NL-only.

def test_render_default_lang_is_bilingual_nl_then_en():
    subject, text, html = email_templates.render(
        "verify_email", {"full_name": "Jan Jansen", "link": "https://gsprecruitment.nl/verify?token=abc", "ttl_hours": 24},
    )
    # Subject stays NL (there is only one Subject: header on a real e-mail).
    assert subject == "Bevestig je e-mailadres - GSP Recruitment"
    # Both languages appear in the text body, NL first.
    assert "Beste Jan Jansen," in text
    assert "Dear Jan Jansen," in text
    assert text.index("Beste Jan Jansen,") < text.index("Dear Jan Jansen,")
    # Both languages appear in the HTML, sharing one shell (one footer).
    assert "Bevestig je e-mailadres" in html
    assert "Confirm your e-mail address" in html
    assert html.count("GSP Recruitment, KvK 75545586, info@gsprecruitment.nl") == 1


def test_render_default_lang_is_bilingual_for_every_template():
    """Every template gets the same treatment, not just verify_email."""
    cases = [
        ("reset_password", {"full_name": "X", "link": "https://x/y", "ttl_hours": 1}, "wachtwoord reset aangevraagd", "You requested a password reset"),
        ("talentpool_confirm", {"link": "https://x/y", "ttl_hours": 48, "job_title": None}, "talentpool van GSP Recruitment", "GSP Recruitment's talent pool"),
        ("talentpool_reminder", {"full_name": "X", "link": "https://x/y"}, "bewaartermijn 12 maanden", "12-month retention period"),
        ("client_team_invite", {"full_name": "X", "inviter_company": "Acme B.V.", "link": "https://x/y"}, "team van Acme B.V.", "Acme B.V.'s team"),
        ("owner_notify", {"event_label": "Nieuwe lead", "detail": "Interesse: embedded", "deeplink": "https://x/y"}, "Interesse: embedded", "View in the admin panel"),
    ]
    for name, ctx, nl_snippet, en_snippet in cases:
        _, text, _ = email_templates.render(name, ctx)
        assert nl_snippet in text, f"{name}: missing NL text in bilingual default"
        assert en_snippet in text, f"{name}: missing EN text in bilingual default"


def test_render_explicit_lang_still_single_language():
    """A caller that does know the language (none currently do, but the
    contract keeps this path) still gets a single-language message."""
    _, text_nl, _ = email_templates.render(
        "verify_email", {"full_name": "X", "link": "https://x/y", "ttl_hours": 1}, "nl",
    )
    assert "Dear X," not in text_nl
    _, text_en, _ = email_templates.render(
        "verify_email", {"full_name": "X", "link": "https://x/y", "ttl_hours": 1}, "en",
    )
    assert "Beste X," not in text_en


def test_html_never_carries_none_literal_for_missing_full_name():
    """_esc(None) must render as an empty string, never the literal text
    'None' leaking into a real e-mail (e.g. talentpool_reminder's
    full_name, which can be absent for a candidate with no name on file)."""
    _, _, html = email_templates.render(
        "talentpool_reminder", {"full_name": None, "link": "https://x/y"}, "nl",
    )
    assert ">None<" not in html
