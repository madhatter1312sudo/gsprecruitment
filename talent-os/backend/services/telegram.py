"""
Talent OS — Telegram notifications (WS-C.10).

No Python code in this repo talked to Telegram before this (grep TELEGRAM
turned up only talent-os/scripts/backup.sh, a bash script, and the
Routines listed in the root CLAUDE.md, which run outside this repo
entirely) -- this is the first API-side helper, used by
routers/public.py's submit_lead() to ping ops when a new lead comes in.

TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are the same two env var names
talent-os/.env.example already documents for backup.sh's alerts (they can
share one bot/chat, or use separate ones -- this module doesn't care).
Read directly via os.getenv rather than core/config.py's Settings so a
missing/blank value never affects app startup (Settings validates some
fields at import time; this must stay a soft no-op, not a boot-time
requirement).

No secrets are read from anywhere but the environment, and nothing here
ever logs the token or a recipient's personal data -- notify_lead() is
explicitly told (WS-C.10 spec) to never carry the person's name or e-mail,
only interest_type and a timestamp.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("talent_os.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"


def is_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID"))


async def _send(text: str) -> bool:
    """No-ops (returns False, logs at debug level) when TELEGRAM_BOT_TOKEN
    or TELEGRAM_CHAT_ID isn't set -- this must never block or fail the
    caller's request just because ops hasn't configured a bot yet."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.debug("Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset) -- skipping notification")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text},
            )
            resp.raise_for_status()
        return True
    except Exception as e:
        # A failed notification must never break lead submission -- log
        # and move on.
        logger.warning(f"Telegram notification failed: {e}")
        return False


async def notify_lead(interest_type: str, submitted_at: Optional[datetime] = None) -> bool:
    """Notify ops of a new lead. Deliberately carries only interest_type
    and a timestamp -- WS-C.10 spec: never the person's name or e-mail in
    the Telegram message (contact_submissions rows, with those fields, are
    reviewed in the admin panel behind auth instead)."""
    when = submitted_at or datetime.now(timezone.utc)
    text = f"New lead ({interest_type}) at {when.strftime('%Y-%m-%d %H:%M UTC')}"
    return await _send(text)
