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

`lang` is standaard None: dan komt NL gevolgd door EN in één bericht terug
(zoals de oude f-string-bodies dat ook deden), want geen enkele aanroeper
kent de taal van de ontvanger. Een aanroeper die de taal wel kent geeft
'nl' of 'en' expliciet mee voor een eentalig bericht.

Uitvoering: één kolom, systeemlettertypen, navy kop (#0A1628), precies
één link, geen afbeeldingen, geen tracking-pixel. Gedeelde voettekst op
elk bericht.

Over de STOP-regel en het Art. 14-blok (SOP §3.2/§3.3), want die lijn
loopt dwars door deze module:

  - `verify_email`, `reset_password`, `talentpool_confirm`,
    `talentpool_reminder`, `client_team_invite`, `dormant_warning` en
    `job_alert` gaan naar iemand die zelf iets deed (registreren, opt-in,
    wachtwoord vergeten, een portaalaccount openen, zich aanmelden voor
    alerts). Dat is art. 13, niet art. 14: geen kennisgevingsblok. Wel
    een afmeldmogelijkheid waar er iets terugkerends wordt gestuurd --
    `job_alert` draagt daarom een eigen een-klik-afmeldlink.
  - `owner_notify` is intern, aan de eigenaar zelf.
  - `referral_confirm` (WS3b) is de enige uitzondering en de enige
    template die wél het volledige Art. 14-blok plus de STOP-regel
    draagt: de gegevens van deze persoon zijn niet van hemzelf verkregen
    maar via een referrer (SOP §1.3, `lawful_basis =
    'toestemming_referral'`), dus art. 14 geldt en het blok is verplicht
    in dit eerste bericht. De tekst is de referral-variant uit
    docs/VERWERKINGSREGISTER.md §4 / docs/SOURCING-SOP.md §3.2, waarbij
    de bronzin volledig is vervangen zoals die twee documenten
    voorschrijven.

Dat `referral_confirm` hier staat en niet in routers/outreach.py maakt
geen nieuw verzendpad naar gesourcete personen: outreach blijft
draft-only. Deze mail gaat uitsluitend uit op een handeling van een
beheerder (POST /api/v1/admin/candidates/referral), één keer per
referral, en vraagt de ontvanger om zelf te bevestigen voordat er iets
met zijn gegevens gebeurt.
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


def _shell(sections) -> str:
    """One HTML shell shared by every template: system fonts, one or more
    heading+body sections, then a single shared footer. No images, no
    tracking pixel, no external stylesheet -- every style is inline so the
    page renders the same in any mail client.

    `sections` is a list of (heading, body_html) pairs. A single-language
    render passes one section. The bilingual default (render() with
    lang=None) passes two -- NL then EN -- stacked in this same shell with
    one divider between them and one footer at the end, not two separate
    e-mails glued together."""
    parts = []
    for i, (heading, body_html) in enumerate(sections):
        if i > 0:
            parts.append('<hr style="margin:24px 0;border:none;border-top:1px solid #E2E8F0;">')
        parts.append(f'<h1 style="font-size:20px;color:#0A1628;margin:0 0 16px;">{heading}</h1>')
        parts.append(body_html)
    return (
        f'<div style="font-family:{_FONT_STACK};max-width:480px;margin:0 auto;'
        'padding:24px;color:#1E293B;font-size:15px;line-height:1.5;">'
        f'{"".join(parts)}'
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


def _verify_email_parts(ctx: dict, lang: str):
    """(subject, heading, text, body_html) for one language -- the single-
    language render and the NL+EN bilingual default in render() both build
    on this, so the two never drift apart."""
    subject = _VERIFY_SUBJECT[lang].substitute()
    text = _VERIFY_TEXT[lang].substitute(full_name=ctx.get("full_name") or "", link=ctx["link"], ttl_hours=ctx["ttl_hours"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    body_html = _VERIFY_HTML_BODY[lang].substitute(full_name=_esc(ctx.get("full_name")), ttl_hours=_esc(ctx["ttl_hours"]), link_html=link_html)
    return subject, _VERIFY_HEADING[lang], text, body_html


def _render_verify_email(ctx: dict, lang: str):
    subject, heading, text, body_html = _verify_email_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


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


def _reset_password_parts(ctx: dict, lang: str):
    subject = _RESET_SUBJECT[lang].substitute()
    text = _RESET_TEXT[lang].substitute(full_name=ctx.get("full_name") or "", link=ctx["link"], ttl_hours=ctx["ttl_hours"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    body_html = _RESET_HTML_BODY[lang].substitute(full_name=_esc(ctx.get("full_name")), ttl_hours=_esc(ctx["ttl_hours"]), link_html=link_html)
    return subject, _RESET_HEADING[lang], text, body_html


def _render_reset_password(ctx: dict, lang: str):
    subject, heading, text, body_html = _reset_password_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


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


def _talentpool_confirm_parts(ctx: dict, lang: str):
    job_title = ctx.get("job_title")
    job_line = _TP_JOB_LINE_TEXT[lang].substitute(job_title=job_title) if job_title else ""
    job_line_html = _TP_JOB_LINE_HTML[lang].substitute(job_title=_esc(job_title)) if job_title else ""
    subject = _TP_CONFIRM_SUBJECT[lang].substitute()
    text = _TP_CONFIRM_TEXT[lang].substitute(job_line=job_line, link=ctx["link"], ttl_hours=ctx["ttl_hours"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    body_html = _TP_CONFIRM_HTML_BODY[lang].substitute(job_line_html=job_line_html, ttl_hours=_esc(ctx["ttl_hours"]), link_html=link_html)
    return subject, _TP_CONFIRM_HEADING[lang], text, body_html


def _render_talentpool_confirm(ctx: dict, lang: str):
    subject, heading, text, body_html = _talentpool_confirm_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


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


def _talentpool_reminder_parts(ctx: dict, lang: str):
    subject = _TP_REMINDER_SUBJECT[lang].substitute()
    text = _TP_REMINDER_TEXT[lang].substitute(full_name=ctx.get("full_name") or "", link=ctx["link"])
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    body_html = _TP_REMINDER_HTML_BODY[lang].substitute(full_name=_esc(ctx.get("full_name")), link_html=link_html)
    return subject, _TP_REMINDER_HEADING[lang], text, body_html


def _render_talentpool_reminder(ctx: dict, lang: str):
    subject, heading, text, body_html = _talentpool_reminder_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


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


def _client_team_invite_parts(ctx: dict, lang: str):
    subject = _TEAM_INVITE_SUBJECT[lang].substitute()
    text = _TEAM_INVITE_TEXT[lang].substitute(
        full_name=ctx.get("full_name") or "", inviter_company=ctx.get("inviter_company") or "GSP Recruitment", link=ctx["link"],
    )
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    body_html = _TEAM_INVITE_HTML_BODY[lang].substitute(
        full_name=_esc(ctx.get("full_name")), inviter_company=_esc(ctx.get("inviter_company") or "GSP Recruitment"), link_html=link_html,
    )
    return subject, _TEAM_INVITE_HEADING[lang], text, body_html


def _render_client_team_invite(ctx: dict, lang: str):
    subject, heading, text, body_html = _client_team_invite_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


# ── referral_confirm (WS3b) ───────────────────────────────────────────────
# ctx: full_name, referred_by, date_found, link, ttl_hours
#
# De enige template hier met het volledige Art. 14-kennisgevingsblok (SOP
# §3.2 / VERWERKINGSREGISTER §4), in de referral-variant: de tweede zin
# ("Wij vonden uw [bron-omschrijving] op [datum] ...") is volledig
# vervangen door de voorgeschreven referral-zin, de rest van het blok
# (grondslag, bewaartermijn, rechten, art. 21, STOP met blokkeerlijst,
# klachtrecht) staat er ongewijzigd onder. De markers waar
# routers/outreach.py's _has_art14_block()/_has_optout_line() op
# controleren ("art. 21", "autoriteit persoonsgegevens", "blokkeerlijst",
# "3 maanden na" respectievelijk "art. 21", "data protection authority",
# "suppression list", "3 months after", plus de STOP-zin) zitten er
# letterlijk in, zodat dezelfde weigeringslogica deze tekst zou
# goedkeuren als hij langs die poort was gekomen -- code-getest in
# tests/test_ws3bc_referral_alerts.py.

_REFERRAL_ART14_NL = (
    'Dit bericht komt van GSP Recruitment (Brainport/Eindhoven), info@gsprecruitment.nl. '
    'Wij hebben uw gegevens op $date_found gekregen via een aanbeveling van $referred_by, met uw toestemming. '
    'Grondslag: toestemming, gegeven vóór dit eerste contact. '
    'Wij bewaren deze gegevens 3 maanden na $date_found als u niet reageert; bij interesse gelden de '
    'bewaartermijnen op gsprecruitment.nl/privacy. U kunt op elk moment inzage, correctie of verwijdering vragen. '
    'U heeft het recht om bezwaar te maken tegen deze verwerking (art. 21 AVG). '
    'U kunt zich afmelden door te antwoorden met "STOP" -- wij verwerken dat binnen 24 uur: wij verwijderen uw '
    'gegevens uit onze actieve bestanden en uw e-mailadres blijft alleen op een blokkeerlijst zodat wij u niet '
    'opnieuw benaderen. Een klacht over deze verwerking kunt u indienen bij de Autoriteit Persoonsgegevens '
    '(autoriteitpersoonsgegevens.nl).'
)
_REFERRAL_ART14_EN = (
    'This message is from GSP Recruitment (Brainport/Eindhoven, NL), info@gsprecruitment.nl. '
    'We received your details on $date_found through a recommendation from $referred_by, with your consent. '
    'Legal basis: consent, given before this first contact. '
    'We retain this data for 3 months after $date_found if you do not respond; if you show interest, the '
    'retention periods at gsprecruitment.nl/privacy apply. You can request access, correction or deletion at '
    'any time. You have the right to object to this processing (Art. 21 GDPR). '
    'You can opt out by replying "STOP" -- we process that within 24 hours: we remove your data from our active '
    'files, and your e-mail address is kept only on a suppression list so we do not contact you again. '
    'You can file a complaint about this processing with the Dutch Data Protection Authority '
    '(Autoriteit Persoonsgegevens, autoriteitpersoonsgegevens.nl).'
)

_REFERRAL_TEXT = {
    "nl": Template(
        "Beste $full_name,\n\n"
        "$art14\n\n"
        "Wij doen niets met uw gegevens tot u dit zelf bevestigt. Bevestig via onderstaande link:\n$link\n\n"
        "Deze link is $ttl_hours uur geldig. Doet u niets, dan verwijderen wij uw gegevens weer.\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Dear $full_name,\n\n"
        "$art14\n\n"
        "We do nothing with your details until you confirm this yourself. Please confirm via the link below:\n$link\n\n"
        "This link is valid for $ttl_hours hours. If you do nothing, we will delete your details again.\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_REFERRAL_SUBJECT = {
    "nl": Template("U bent bij ons aangedragen - bevestig graag zelf - GSP Recruitment"),
    "en": Template("You were introduced to us - please confirm yourself - GSP Recruitment"),
}
_REFERRAL_HEADING = {"nl": "U bent bij ons aangedragen", "en": "You were introduced to us"}
_REFERRAL_HTML_BODY = {
    "nl": Template(
        "<p>Beste $full_name,</p>"
        "<p>$art14</p>"
        "<p>Wij doen niets met uw gegevens tot u dit zelf bevestigt. Bevestig via onderstaande link:</p>"
        "$link_html"
        "<p>Deze link is $ttl_hours uur geldig. Doet u niets, dan verwijderen wij uw gegevens weer.</p>"
    ),
    "en": Template(
        "<p>Dear $full_name,</p>"
        "<p>$art14</p>"
        "<p>We do nothing with your details until you confirm this yourself. Please confirm via the link below:</p>"
        "$link_html"
        "<p>This link is valid for $ttl_hours hours. If you do nothing, we will delete your details again.</p>"
    ),
}
_REFERRAL_ART14_TEMPLATES = {"nl": Template(_REFERRAL_ART14_NL), "en": Template(_REFERRAL_ART14_EN)}


def _referral_confirm_parts(ctx: dict, lang: str):
    referred_by = ctx.get("referred_by") or ("een bekende van u" if lang == "nl" else "someone you know")
    date_found = ctx.get("date_found") or ""
    art14 = _REFERRAL_ART14_TEMPLATES[lang].substitute(referred_by=referred_by, date_found=date_found)
    art14_html = _REFERRAL_ART14_TEMPLATES[lang].substitute(
        referred_by=_esc(referred_by), date_found=_esc(date_found),
    )
    subject = _REFERRAL_SUBJECT[lang].substitute()
    text = _REFERRAL_TEXT[lang].substitute(
        full_name=ctx.get("full_name") or "", art14=art14, link=ctx["link"], ttl_hours=ctx["ttl_hours"],
    )
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    body_html = _REFERRAL_HTML_BODY[lang].substitute(
        full_name=_esc(ctx.get("full_name")), art14=art14_html,
        ttl_hours=_esc(ctx["ttl_hours"]), link_html=link_html,
    )
    return subject, _REFERRAL_HEADING[lang], text, body_html


def _render_referral_confirm(ctx: dict, lang: str):
    subject, heading, text, body_html = _referral_confirm_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


# ── dormant_warning (WS3b) ────────────────────────────────────────────────
# ctx: full_name (mag leeg zijn), link, deadline
#
# Deze mail mag niets beloven wat de code niet doet. Wat de code doet:
# core/retention.py's PORTAL_ACCOUNT_INACTIVE_SQL zet een account pas op
# de maandelijkse beoordelingslijst als het 18 maanden niet is gebruikt
# EN deze waarschuwing minstens 30 dagen geleden is verstuurd. Die lijst
# is een goedkeuringslijst voor een beheerder, geen wisknop: er wordt
# niets automatisch verwijderd. De tekst zegt daarom "komt je account op
# de maandelijkse verwijderlijst", niet "wordt je account verwijderd", en
# noemt de datum die de aanroeper doorgeeft (verzenddatum + 30 dagen).
# Inloggen alleen is genoeg: elk inlogpad stempelt users.last_login_at
# (routers/auth.py login/google, routers/mfa.py), waarmee het account uit
# beide selectors valt.

_DORMANT_TEXT = {
    "nl": Template(
        "Beste $full_name,\n\n"
        "Je hebt je GSP Recruitment-account al 18 maanden niet gebruikt.\n\n"
        "Log in vóór $deadline om je account actief te houden:\n$link\n\n"
        "Doe je dat niet, dan komt je account daarna op onze maandelijkse verwijderlijst: een beheerder "
        "beoordeelt die lijst en verwijdert je account en profiel. Inloggen is genoeg, je hoeft verder niets te doen.\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Dear $full_name,\n\n"
        "You have not used your GSP Recruitment account for 18 months.\n\n"
        "Log in before $deadline to keep your account active:\n$link\n\n"
        "If you do not, your account goes onto our monthly deletion list after that date: an administrator "
        "reviews that list and deletes your account and profile. Logging in is enough, there is nothing else to do.\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_DORMANT_SUBJECT = {
    "nl": Template("Je account is al 18 maanden ongebruikt - GSP Recruitment"),
    "en": Template("Your account has been unused for 18 months - GSP Recruitment"),
}
_DORMANT_HEADING = {"nl": "Je account is al 18 maanden ongebruikt", "en": "Your account has been unused for 18 months"}
_DORMANT_HTML_BODY = {
    "nl": Template(
        "<p>Beste $full_name,</p>"
        "<p>Je hebt je GSP Recruitment-account al 18 maanden niet gebruikt. Log in vóór $deadline om je "
        "account actief te houden:</p>"
        "$link_html"
        "<p>Doe je dat niet, dan komt je account daarna op onze maandelijkse verwijderlijst: een beheerder "
        "beoordeelt die lijst en verwijdert je account en profiel. Inloggen is genoeg, je hoeft verder niets te doen.</p>"
    ),
    "en": Template(
        "<p>Dear $full_name,</p>"
        "<p>You have not used your GSP Recruitment account for 18 months. Log in before $deadline to keep "
        "your account active:</p>"
        "$link_html"
        "<p>If you do not, your account goes onto our monthly deletion list after that date: an administrator "
        "reviews that list and deletes your account and profile. Logging in is enough, there is nothing else to do.</p>"
    ),
}


def _dormant_warning_parts(ctx: dict, lang: str):
    subject = _DORMANT_SUBJECT[lang].substitute()
    text = _DORMANT_TEXT[lang].substitute(
        full_name=ctx.get("full_name") or "", link=ctx["link"], deadline=ctx["deadline"],
    )
    link_html = _link_html(_esc(ctx["link"]), _esc(ctx["link"]))
    body_html = _DORMANT_HTML_BODY[lang].substitute(
        full_name=_esc(ctx.get("full_name")), deadline=_esc(ctx["deadline"]), link_html=link_html,
    )
    return subject, _DORMANT_HEADING[lang], text, body_html


def _render_dormant_warning(ctx: dict, lang: str):
    subject, heading, text, body_html = _dormant_warning_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


# ── job_alert (WS3c) ──────────────────────────────────────────────────────
# ctx: full_name (mag leeg zijn), jobs (lijst dicts met title/location/url),
#      unsubscribe_link
#
# Servicemail aan iemand die zich zélf voor alerts heeft aangemeld
# (job_alert_optin_at): geen Art. 14-blok (art. 13-grondslag), wél op elk
# bericht een afmeldlink, want dit is het enige terugkerende bericht dat
# deze codebase verstuurt. Die link is per verzending uniek en werkt met
# één klik (geen inloggen, geen formulier) -- dezelfde token die in de
# List-Unsubscribe-headers zit (services/scheduler.py job_alert_job).
#
# `jobs` is al begrensd op vijf door de aanroeper; deze module rendert
# wat zij krijgt en escapet elke titel/locatie los in de HTML-variant.

_JOB_ALERT_TEXT = {
    "nl": Template(
        "Beste $full_name,\n\n"
        "Deze vacatures passen bij je profiel:\n\n"
        "$job_lines\n"
        "Wil je geen vacature-alerts meer ontvangen? Meld je hier met één klik af:\n$unsubscribe_link\n\n"
        "Met vriendelijke groet,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
    "en": Template(
        "Dear $full_name,\n\n"
        "These vacancies match your profile:\n\n"
        "$job_lines\n"
        "No longer want job alerts? Unsubscribe here with one click:\n$unsubscribe_link\n\n"
        "Kind regards,\nGSP Recruitment\ninfo@gsprecruitment.nl\n"
    ),
}
_JOB_ALERT_SUBJECT = {
    "nl": Template("Nieuwe vacatures die bij je passen - GSP Recruitment"),
    "en": Template("New vacancies that match your profile - GSP Recruitment"),
}
_JOB_ALERT_HEADING = {"nl": "Nieuwe vacatures die bij je passen", "en": "New vacancies that match your profile"}
_JOB_ALERT_HTML_BODY = {
    "nl": Template(
        "<p>Beste $full_name,</p>"
        "<p>Deze vacatures passen bij je profiel:</p>"
        "$job_list_html"
        "<p>Wil je geen vacature-alerts meer ontvangen? Meld je hier met één klik af:</p>"
        "$unsubscribe_html"
    ),
    "en": Template(
        "<p>Dear $full_name,</p>"
        "<p>These vacancies match your profile:</p>"
        "$job_list_html"
        "<p>No longer want job alerts? Unsubscribe here with one click:</p>"
        "$unsubscribe_html"
    ),
}
_JOB_ALERT_UNSUB_LABEL = {"nl": "Afmelden voor vacature-alerts", "en": "Unsubscribe from job alerts"}


def _job_alert_parts(ctx: dict, lang: str):
    jobs = ctx.get("jobs") or []
    text_lines = []
    html_items = []
    for job in jobs:
        title = job.get("title") or ""
        location = job.get("location") or ""
        url = job.get("url") or ""
        suffix = f" ({location})" if location else ""
        text_lines.append(f"- {title}{suffix}\n  {url}")
        html_items.append(
            f'<li><a href="{_esc(url)}" style="color:#0A1628;">{_esc(title)}</a>{_esc(suffix)}</li>'
        )
    job_lines = "\n".join(text_lines) + "\n\n" if text_lines else ""
    job_list_html = f'<ul>{"".join(html_items)}</ul>' if html_items else ""

    subject = _JOB_ALERT_SUBJECT[lang].substitute()
    text = _JOB_ALERT_TEXT[lang].substitute(
        full_name=ctx.get("full_name") or "", job_lines=job_lines,
        unsubscribe_link=ctx["unsubscribe_link"],
    )
    unsubscribe_html = _link_html(_esc(ctx["unsubscribe_link"]), _esc(_JOB_ALERT_UNSUB_LABEL[lang]))
    body_html = _JOB_ALERT_HTML_BODY[lang].substitute(
        full_name=_esc(ctx.get("full_name")), job_list_html=job_list_html,
        unsubscribe_html=unsubscribe_html,
    )
    return subject, _JOB_ALERT_HEADING[lang], text, body_html


def _render_job_alert(ctx: dict, lang: str):
    subject, heading, text, body_html = _job_alert_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


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


def _owner_notify_parts(ctx: dict, lang: str):
    event_label = ctx.get("event_label") or ""
    detail = ctx.get("detail") or ""
    deeplink = ctx["deeplink"]
    subject = _OWNER_NOTIFY_SUBJECT[lang].substitute(event_label=event_label)
    text = _OWNER_NOTIFY_TEXT[lang].substitute(event_label=event_label, detail=detail, deeplink=deeplink)
    link_html = _link_html(_esc(deeplink), _esc(deeplink))
    body_html = _OWNER_NOTIFY_HTML_BODY[lang].substitute(detail=_esc(detail), link_html=link_html)
    return subject, _esc(event_label), text, body_html


def _render_owner_notify(ctx: dict, lang: str):
    subject, heading, text, body_html = _owner_notify_parts(ctx, lang)
    return subject, text, _shell([(heading, body_html)])


_RENDERERS = {
    "verify_email": _render_verify_email,
    "reset_password": _render_reset_password,
    "talentpool_confirm": _render_talentpool_confirm,
    "talentpool_reminder": _render_talentpool_reminder,
    "client_team_invite": _render_client_team_invite,
    "referral_confirm": _render_referral_confirm,
    "dormant_warning": _render_dormant_warning,
    "job_alert": _render_job_alert,
    "owner_notify": _render_owner_notify,
}

# (subject, heading, text, body_html) for one language -- render()'s
# bilingual default (lang=None) uses these directly instead of the
# _RENDERERS entry above, so it can place NL and EN in one shared _shell()
# instead of two independent single-language e-mails glued together.
_PARTS = {
    "verify_email": _verify_email_parts,
    "reset_password": _reset_password_parts,
    "talentpool_confirm": _talentpool_confirm_parts,
    "talentpool_reminder": _talentpool_reminder_parts,
    "client_team_invite": _client_team_invite_parts,
    "referral_confirm": _referral_confirm_parts,
    "dormant_warning": _dormant_warning_parts,
    "job_alert": _job_alert_parts,
    "owner_notify": _owner_notify_parts,
}

_BILINGUAL_TEXT_SEPARATOR = "\n" + ("-" * 40) + "\n\n"


def render(name: str, ctx: dict, lang: Optional[str] = None):
    """Render template `name` with context dict `ctx`.

    `lang` is 'nl', 'en', or None (the default). None renders NL followed
    by EN in a single message -- Dutch-first, English included -- because
    none of the email service's callers know the recipient's language
    (UserRegister has no language field) and defaulting to NL-only would
    silently drop the English half every one of these servicemails used
    to carry as an f-string body before this module existed. A caller
    that does know the language may still pass 'nl' or 'en' for a
    single-language message; an unrecognised value falls back to 'nl'.

    Returns (subject, text, html). Raises KeyError for an unknown
    template name or a required ctx field the caller forgot -- both are
    programming errors, not something to swallow silently."""
    try:
        renderer = _RENDERERS[name]
        parts_fn = _PARTS[name]
    except KeyError:
        raise KeyError(f"Unknown email template: {name!r}") from None

    if lang is None:
        subject_nl, heading_nl, text_nl, body_nl = parts_fn(ctx, "nl")
        _subject_en, heading_en, text_en, body_en = parts_fn(ctx, "en")
        text = text_nl + _BILINGUAL_TEXT_SEPARATOR + text_en
        html = _shell([(heading_nl, body_nl), (heading_en, body_en)])
        return subject_nl, text, html

    if lang not in ("nl", "en"):
        lang = "nl"
    return renderer(ctx, lang)
