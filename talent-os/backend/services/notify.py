"""
Talent OS -- WS3: owner-melding bij nieuwe activiteit.

notify_owner(event, fields) is de enige plek die beide kanalen aanroept:

  (a) Telegram, via de bestaande services/telegram.py -- nooit een naam
      of e-mailadres, alleen het event en een tijdstip, hetzelfde principe
      als telegram.notify_lead() al toepaste (WS-C.10). Voor het
      "lead"-event roept dit precies notify_lead() aan, zodat
      routers/public.py's bestaande Telegram-tekst voor een lead
      onveranderd blijft -- alleen de aanroep verhuist hierheen.

  (b) een e-mail naar OWNER_NOTIFY_EMAIL (core/config.py), alleen als die
      setting gezet is -- leeg (de default) betekent geen eigenaarsmail,
      alleen Telegram. Deze mail mag naam, interesse of vacaturetitel
      bevatten plus een deeplink naar het adminpaneel -- niet meer dan
      dat: geen e-mailadres en geen bedrijfsnaam. De deeplink ontsluit die
      gegevens al in het adminpaneel zelf, dus een kopie ervan in de
      eigenaarsmailbox (bij Google of een andere derde) is overbodig en
      een wissing in het adminpaneel bereikt die kopie niet.

Best-effort: een falende Telegram-call of e-mail mag nooit een exception
laten ontsnappen naar de aanroeper -- de lead-, register- en
talentpool-confirm-endpoints die dit aanroepen mogen nooit mislukken
omdat een melding niet aankwam.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from core.config import settings
from services import telegram
from services.email_service import email_service

logger = logging.getLogger("talent_os.notify")

# Dutch label per event, used both for the Telegram fallback text and the
# owner_notify e-mail subject/heading -- never the raw event key, which is
# an internal identifier, not something to put in front of the owner.
_EVENT_LABELS = {
    "lead": "Nieuwe lead",
    "candidate_registered": "Nieuwe kandidaat geregistreerd",
    "client_registered": "Nieuwe klant geregistreerd",
    "google_signup": "Nieuwe gebruiker via Google Sign-In",
    "talentpool_confirmed": "Talentpool-aanmelding bevestigd",
    "client_job_created": "Nieuwe vacature van een klant",
}

_DEFAULT_ANCHOR = "leads"


async def _notify_telegram(event: str, fields: dict) -> None:
    if event == "lead":
        # Exact pre-existing behaviour (routers/public.py used to call
        # this directly) -- only interest_type and a timestamp, never the
        # submitter's name or e-mail.
        await telegram.notify_lead(fields.get("interest_type") or "", fields.get("submitted_at"))
        return

    # Every other event: same no-PII shape as notify_lead, generalised --
    # the event label and a timestamp, nothing from `fields` that could
    # carry a name or address.
    when = fields.get("submitted_at") or datetime.now(timezone.utc)
    text = f"{_EVENT_LABELS.get(event, event)} at {when.strftime('%Y-%m-%d %H:%M UTC')}"
    await telegram._send(text)


def _owner_email_detail(fields: dict) -> str:
    """Build the one-or-two-line detail block for the owner_notify
    e-mail -- unlike Telegram, this mail is allowed to carry the name,
    interest or vacancy title (contract: an internal notification to the
    owner themself, not a message to the person it is about). Never the
    e-mail address or company: the deeplink already opens the record in
    the admin panel, so a copy of the address in the owner's mailbox
    (at Google or elsewhere) would only be a second, unmanaged copy of
    personal data that a GDPR erasure request in the admin panel never
    reaches. Callers must not pass "email" or "company" in `fields`."""
    parts = []
    if fields.get("full_name"):
        parts.append(f"Naam: {fields['full_name']}")
    if fields.get("interest_type"):
        parts.append(f"Interesse: {fields['interest_type']}")
    if fields.get("job_title") or fields.get("applied_job"):
        parts.append(f"Vacature: {fields.get('job_title') or fields.get('applied_job')}")
    return "\n".join(parts) if parts else "Geen aanvullende gegevens."


async def _notify_owner_email(event: str, fields: dict) -> None:
    if not settings.owner_notify_email:
        return
    anchor = fields.get("anchor") or _DEFAULT_ANCHOR
    ctx = {
        "event_label": _EVENT_LABELS.get(event, event),
        "detail": _owner_email_detail(fields),
        "deeplink": f"{settings.frontend_url}/admin/#{anchor}",
    }
    await email_service.send_template("owner_notify", settings.owner_notify_email, ctx)


async def notify_owner(event: str, fields: Optional[dict] = None) -> None:
    """Best-effort owner notification for `event` (see _EVENT_LABELS for
    the recognised keys -- an unknown key still sends, using the key
    itself as the label, rather than raising). Never lets an exception
    from either channel escape to the caller."""
    fields = fields or {}
    try:
        await _notify_telegram(event, fields)
    except Exception:
        logger.warning("notify_owner: Telegram notification failed for event=%s", event, exc_info=True)

    try:
        await _notify_owner_email(event, fields)
    except Exception:
        logger.warning("notify_owner: owner e-mail failed for event=%s", event, exc_info=True)
