"""
Talent OS -- WS3: e-mailtemplates (NL/EN).

Eén `string.Template` per template per taal, hier vastgelegd zodat
services/email_service.py's `send_template(name, to_email, ctx, lang)`
nooit zelf tekst samenstelt. Vervangt de vijf losse f-string-bodies die
tot dit spoor in routers/auth.py, routers/public.py, routers/client.py en
services/scheduler.py stonden -- dezelfde links en dezelfde beloften,
alleen nu op één plek, per taal apart (in plaats van NL en EN
achtereenvolgens in één bericht).

`render(name, ctx, lang)` geeft (subject, text, html) terug. De platte
tekst krijgt de ruwe ctx-waarden (een e-mailclient toont platte tekst
zonder opmaak, er is niets om te ontsnappen). De HTML-variant haalt elke
losse ctx-waarde eerst door `html.escape()` -- geen enkele aanroeper mag
hierop vertrouwen zonder dat deze module het zelf afdwingt, dus dit
gebeurt hier centraal in `_esc()`, nooit door de aanroeper.

Uitvoering: één kolom, systeemlettertypen, navy kop (#0A1628), precies
één link, geen afbeeldingen, geen tracking-pixel. Gedeelde voettekst op
elk bericht. Geen STOP-regel: geen van deze templates gaat naar een
gesourcete persoon (die blijven draft-only via routers/outreach.py) --
elk bericht hier is een servicemail aan iemand die zelf iets deed
(registreren, opt-in, wachtwoord vergeten) of een interne melding aan de
eigenaar (owner_notify).
"""
import html as _html
from string import Template
from typing import Optional

FOOTER_TEXT = "GSP Recruitment, KvK 75545586, info@gsprecruitment.nl"

_FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"


def _esc(value: Optional[object]) -> str:
    """html.escape() on the string form of any ctx value; None becomes ''
    rather than the literal string 'None' leaking into an e-mail."""
    if value is None:
        return ""
    return _html.escape(str(value))


def _shell(heading: str, body_html: str) -> str:
    """One-column HTML shell shared by every template: system fonts, a
    navy heading, the template's own body, then the shared footer. No
    images, no tracking pixel, no external stylesheet -- every style is
    inline so the page renders the same in any mail client."""
    return (
        f'<div style="font-family:{_FONT_STACK};max-width:480px;margin:0 auto;'
        'padding:24px;color:#1E293B;font-size:15px;line-height:1.5;">'
        f'<h1 style="font-size:20px;color:#0A1628;margin:0 0 16px;">{heading}</h1>'
        f'{body_html}'
        '<p style="margin:24px 0 0;padding-top:16px;border-top:1px solid #E2E8F0;'
        f'font-size:12px;color:#64748B;">{FOOTER_TEXT}</p>'
        '</div>'
    )


def _link_html(url_escaped: str, label_escaped: str) -> str:
    """The one link a template body is allowed -- `url_escaped` and
    `label_escaped` must already be html.escape()'d by the caller."""
    return f'<p><a href="{url_escaped}" style="color:#0A1628;">{label_escaped}</a></p>'


# ── verify_email ──────────────────────────────────────────────────────────
# ctx: full_name, link, ttl_hours

_VERIFY_TEXT = {
    "nl": Template(
        "Beste $full_name,\n\n"
        "Bedankt voor je registratie bij GSP Recruitment. Bevestig je e-mailadres via onderstaande link:\n"
        "$link\n\n"
        "Deze link is $ttl_hours uur geldig.\n\n"
        "Heb je dit account niet aangemaakt? Dan kun je dit bericht negeren.\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Dear $full_name,\n\n"
        "Thank you for registering with GSP Recruitment. Please confirm your e-mail address via the link below:\n"
        "$link\n\n"
        "This link is valid for $ttl_hours hours.\n\n"
        "Didn't create this account? You can ignore this message.\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_VERIFY_SUBJECT = {
    "nl": Template("Bevestig je e-mailadres - GSP Recruitment"),
    "en": Template("Confirm your e-mail address - GSP Recruitment"),
}
_VERIFY_HEADING = {"nl": "Bevestig je e-mailadres", "en": "Confirm your e-mail address"}
_VERIFY_HTML_BODY = {
    "nl": Template(
        "<p>Beste $full_name,</p>"
        "<p>Bedankt voor je registratie bij GSP Recruitment. Bevestig je e-mailadres via onderstaande link:</p>"
        "$link_html"
        "<p>Deze link is $ttl_hours uur geldig. Heb je dit account niet aangemaakt? "
        "Dan kun je dit bericht negeren.</p>"
    ),
    "en": Template(
        "<p>Dear $full_name,</p>"
        "<p>Thank you for registering with GSP Recruitment. Please confirm your e-mail address via the link below:</p>"
        "$link_html"
        "<p>This link is valid for $ttl_hours hours. Didn't create this account? "
        "You can ignore this message.</p>"
    ),
}


def _render_verify_email(ctx: dict, lang: str):
    subject = _VERIFY_SUBJECT[lang].substitute()
    text = _VERIFY_TEXT[lang].substitute(full_name=ctx.get("full_name") or "", link=ctx["link"], ttl_hours=ctx["ttl_hours"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    html = _shell(
        _VERIFY_HEADING[lang],
        _VERIFY_HTML_BODY[lang].substitute(full_name=_esc(ctx.get("full_name")), ttl_hours=_esc(ctx["ttl_hours"]), link_html=link_html),
    )
    return subject, text, html


# ── reset_password ────────────────────────────────────────────────────────
# ctx: full_name, link, ttl_hours

_RESET_TEXT = {
    "nl": Template(
        "Beste $full_name,\n\n"
        "Je hebt een wachtwoord reset aangevraagd voor je GSP Recruitment account.\n\n"
        "Klik op de volgende link om je wachtwoord te resetten:\n$link\n\n"
        "Deze link is $ttl_hours uur geldig.\n\n"
        "Als je geen wachtwoord reset hebt aangevraagd, kun je dit bericht negeren.\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Dear $full_name,\n\n"
        "You requested a password reset for your GSP Recruitment account.\n\n"
        "Click the link below to reset your password:\n$link\n\n"
        "This link is valid for $ttl_hours hours.\n\n"
        "If you did not request a password reset, you can ignore this message.\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_RESET_SUBJECT = {
    "nl": Template("Wachtwoord resetten - GSP Recruitment"),
    "en": Template("Reset your password - GSP Recruitment"),
}
_RESET_HEADING = {"nl": "Wachtwoord resetten", "en": "Reset your password"}
_RESET_HTML_BODY = {
    "nl": Template(
        "<p>Beste $full_name,</p>"
        "<p>Je hebt een wachtwoord reset aangevraagd voor je GSP Recruitment account.</p>"
        "$link_html"
        "<p>Deze link is $ttl_hours uur geldig. Als je geen wachtwoord reset hebt aangevraagd, "
        "kun je dit bericht negeren.</p>"
    ),
    "en": Template(
        "<p>Dear $full_name,</p>"
        "<p>You requested a password reset for your GSP Recruitment account.</p>"
        "$link_html"
        "<p>This link is valid for $ttl_hours hours. If you did not request a password reset, "
        "you can ignore this message.</p>"
    ),
}


def _render_reset_password(ctx: dict, lang: str):
    subject = _RESET_SUBJECT[lang].substitute()
    text = _RESET_TEXT[lang].substitute(full_name=ctx.get("full_name") or "", link=ctx["link"], ttl_hours=ctx["ttl_hours"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    html = _shell(
        _RESET_HEADING[lang],
        _RESET_HTML_BODY[lang].substitute(full_name=_esc(ctx.get("full_name")), ttl_hours=_esc(ctx["ttl_hours"]), link_html=link_html),
    )
    return subject, text, html


# ── talentpool_confirm ────────────────────────────────────────────────────
# ctx: link, ttl_hours, job_title (optional)

_TP_CONFIRM_TEXT = {
    # ${job_line}, braced -- a bare $job_line directly followed by a
    # letter ("Bevestig"/"Please") is parsed by string.Template as one
    # longer identifier ("job_lineBevestig"), not "$job_line" + literal
    # text, and substitute() raises KeyError on the real (non-empty)
    # job_line value. Braces are the only fix; a space cannot separate
    # them without adding a stray space when job_line is "".
    "nl": Template(
        "Bedankt voor je aanmelding voor de talentpool van GSP Recruitment. ${job_line}"
        "Bevestig via onderstaande link:\n$link\n\n"
        "Deze link is $ttl_hours uur geldig. Heb je dit niet aangevraagd? Dan kun je dit bericht negeren.\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Thank you for signing up for GSP Recruitment's talent pool. ${job_line}"
        "Please confirm via the link below:\n$link\n\n"
        "This link is valid for $ttl_hours hours. Didn't request this? You can ignore this message.\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_TP_CONFIRM_SUBJECT = {
    "nl": Template("Bevestig je talentpool-aanmelding - GSP Recruitment"),
    "en": Template("Confirm your talent pool sign-up - GSP Recruitment"),
}
_TP_CONFIRM_HEADING = {"nl": "Bevestig je talentpool-aanmelding", "en": "Confirm your talent pool sign-up"}
_TP_CONFIRM_HTML_BODY = {
    "nl": Template(
        "<p>Bedankt voor je aanmelding voor de talentpool van GSP Recruitment. $job_line_html</p>"
        "<p>Bevestig via onderstaande link:</p>"
        "$link_html"
        "<p>Deze link is $ttl_hours uur geldig. Heb je dit niet aangevraagd? Dan kun je dit bericht negeren.</p>"
    ),
    "en": Template(
        "<p>Thank you for signing up for GSP Recruitment's talent pool. $job_line_html</p>"
        "<p>Please confirm via the link below:</p>"
        "$link_html"
        "<p>This link is valid for $ttl_hours hours. Didn't request this? You can ignore this message.</p>"
    ),
}
_TP_JOB_LINE_TEXT = {
    "nl": Template("Je reageerde op de vacature: $job_title.\n\n"),
    "en": Template("You applied to the vacancy: $job_title.\n\n"),
}
_TP_JOB_LINE_HTML = {
    "nl": Template("Je reageerde op de vacature: $job_title."),
    "en": Template("You applied to the vacancy: $job_title."),
}


def _render_talentpool_confirm(ctx: dict, lang: str):
    job_title = ctx.get("job_title")
    job_line = _TP_JOB_LINE_TEXT[lang].substitute(job_title=job_title) if job_title else ""
    job_line_html = _TP_JOB_LINE_HTML[lang].substitute(job_title=_esc(job_title)) if job_title else ""
    subject = _TP_CONFIRM_SUBJECT[lang].substitute()
    text = _TP_CONFIRM_TEXT[lang].substitute(job_line=job_line, link=ctx["link"], ttl_hours=ctx["ttl_hours"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    html = _shell(
        _TP_CONFIRM_HEADING[lang],
        _TP_CONFIRM_HTML_BODY[lang].substitute(job_line_html=job_line_html, ttl_hours=_esc(ctx["ttl_hours"]), link_html=link_html),
    )
    return subject, text, html


# ── talentpool_reminder ───────────────────────────────────────────────────
# ctx: full_name (may be empty), link

_TP_REMINDER_TEXT = {
    "nl": Template(
        "Beste $full_name,\n\n"
        "Je staat in de talentpool van GSP Recruitment. Over ongeveer een maand loopt je toestemming af "
        "(bewaartermijn 12 maanden). Wil je verlengd blijven staan, meld je dan hier opnieuw aan:\n$link\n\n"
        "Doe je niets, dan verwijderen wij je gegevens uit de talentpool zodra de termijn is verstreken.\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Dear $full_name,\n\n"
        "You are in GSP Recruitment's talent pool. Your consent expires in about a month "
        "(12-month retention period). To stay in the pool, sign up again here:\n$link\n\n"
        "If you do nothing, we will remove your data from the talent pool once the period has passed.\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_TP_REMINDER_SUBJECT = {
    "nl": Template("Je talentpool-aanmelding loopt bijna af - GSP Recruitment"),
    "en": Template("Your talent pool sign-up is about to expire - GSP Recruitment"),
}
_TP_REMINDER_HEADING = {"nl": "Je talentpool-aanmelding loopt bijna af", "en": "Your talent pool sign-up is about to expire"}
_TP_REMINDER_HTML_BODY = {
    "nl": Template(
        "<p>Beste $full_name,</p>"
        "<p>Je staat in de talentpool van GSP Recruitment. Over ongeveer een maand loopt je toestemming af "
        "(bewaartermijn 12 maanden). Wil je verlengd blijven staan, meld je dan hier opnieuw aan:</p>"
        "$link_html"
        "<p>Doe je niets, dan verwijderen wij je gegevens uit de talentpool zodra de termijn is verstreken.</p>"
    ),
    "en": Template(
        "<p>Dear $full_name,</p>"
        "<p>You are in GSP Recruitment's talent pool. Your consent expires in about a month "
        "(12-month retention period). To stay in the pool, sign up again here:</p>"
        "$link_html"
        "<p>If you do nothing, we will remove your data from the talent pool once the period has passed.</p>"
    ),
}


def _render_talentpool_reminder(ctx: dict, lang: str):
    subject = _TP_REMINDER_SUBJECT[lang].substitute()
    text = _TP_REMINDER_TEXT[lang].substitute(full_name=ctx.get("full_name") or "", link=ctx["link"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    html = _shell(
        _TP_REMINDER_HEADING[lang],
        _TP_REMINDER_HTML_BODY[lang].substitute(full_name=_esc(ctx.get("full_name")), link_html=link_html),
    )
    return subject, text, html


# ── client_team_invite ────────────────────────────────────────────────────
# ctx: full_name, link, inviter_company

_TEAM_INVITE_TEXT = {
    "nl": Template(
        "Beste $full_name,\n\n"
        "Je bent uitgenodigd om je aan te sluiten bij het team van $inviter_company op GSP Recruitment. "
        "Stel je wachtwoord in via onderstaande link om je account te activeren:\n$link\n\n"
        "Deze link is 24 uur geldig.\n\n"
        "Als je deze uitnodiging niet verwachtte, kun je dit bericht negeren.\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Dear $full_name,\n\n"
        "You have been invited to join $inviter_company's team on GSP Recruitment. "
        "Set your password via the link below to activate your account:\n$link\n\n"
        "This link is valid for 24 hours.\n\n"
        "If you did not expect this invitation, you can ignore this message.\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_TEAM_INVITE_SUBJECT = {
    "nl": Template("Uitnodiging teamlid - GSP Recruitment"),
    "en": Template("Team invitation - GSP Recruitment"),
}
_TEAM_INVITE_HEADING = {"nl": "Uitnodiging teamlid", "en": "Team invitation"}
_TEAM_INVITE_HTML_BODY = {
    "nl": Template(
        "<p>Beste $full_name,</p>"
        "<p>Je bent uitgenodigd om je aan te sluiten bij het team van $inviter_company op GSP Recruitment. "
        "Stel je wachtwoord in via onderstaande link om je account te activeren:</p>"
        "$link_html"
        "<p>Deze link is 24 uur geldig. Als je deze uitnodiging niet verwachtte, kun je dit bericht negeren.</p>"
    ),
    "en": Template(
        "<p>Dear $full_name,</p>"
        "<p>You have been invited to join $inviter_company's team on GSP Recruitment. "
        "Set your password via the link below to activate your account:</p>"
        "$link_html"
        "<p>This link is valid for 24 hours. If you did not expect this invitation, "
        "you can ignore this message.</p>"
    ),
}


def _render_client_team_invite(ctx: dict, lang: str):
    subject = _TEAM_INVITE_SUBJECT[lang].substitute()
    text = _TEAM_INVITE_TEXT[lang].substitute(
        full_name=ctx.get("full_name") or "", inviter_company=ctx.get("inviter_company") or "GSP Recruitment", link=ctx["link"],
    )
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    html = _shell(
        _TEAM_INVITE_HEADING[lang],
        _TEAM_INVITE_HTML_BODY[lang].substitute(
            full_name=_esc(ctx.get("full_name")), inviter_company=_esc(ctx.get("inviter_company") or "GSP Recruitment"), link_html=link_html,
        ),
    )
    return subject, text, html


# ── owner_notify (intern) ─────────────────────────────────────────────────
# ctx: event_label, detail, deeplink -- services/notify.py is the only caller

_OWNER_NOTIFY_TEXT = {
    "nl": Template(
        "$event_label\n\n$detail\n\nBekijk in het adminpaneel:\n$deeplink\n"
    ),
    "en": Template(
        "$event_label\n\n$detail\n\nView in the admin panel:\n$deeplink\n"
    ),
}
_OWNER_NOTIFY_SUBJECT = {
    "nl": Template("$event_label - GSP Recruitment admin"),
    "en": Template("$event_label - GSP Recruitment admin"),
}
_OWNER_NOTIFY_HTML_BODY = {
    "nl": Template("<p>$detail</p>$link_html"),
    "en": Template("<p>$detail</p>$link_html"),
}


def _render_owner_notify(ctx: dict, lang: str):
    event_label = ctx.get("event_label") or ""
    detail = ctx.get("detail") or ""
    deeplink = ctx["deeplink"]
    subject = _OWNER_NOTIFY_SUBJECT[lang].substitute(event_label=event_label)
    text = _OWNER_NOTIFY_TEXT[lang].substitute(event_label=event_label, detail=detail, deeplink=deeplink)
    link_html = _link_html(_esc(deeplink), _esc(deeplink))
    html = _shell(
        _esc(event_label),
        _OWNER_NOTIFY_HTML_BODY[lang].substitute(detail=_esc(detail), link_html=link_html),
    )
    return subject, text, html


_RENDERERS = {
    "verify_email": _render_verify_email,
    "reset_password": _render_reset_password,
    "talentpool_confirm": _render_talentpool_confirm,
    "talentpool_reminder": _render_talentpool_reminder,
    "client_team_invite": _render_client_team_invite,
    "owner_notify": _render_owner_notify,
}


def render(name: str, ctx: dict, lang: str = "nl"):
    """Render template `name` for `lang` ('nl' or 'en', default 'nl' --
    the site is Dutch-first) with context dict `ctx`.

    Returns (subject, text, html). Raises KeyError for an unknown
    template name or a required ctx field the caller forgot -- both are
    programming errors, not something to swallow silently."""
    if lang not in ("nl", "en"):
        lang = "nl"
    try:
        renderer = _RENDERERS[name]
    except KeyError:
        raise KeyError(f"Unknown email template: {name!r}") from None
    return renderer(ctx, lang)
