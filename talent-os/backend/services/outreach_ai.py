"""
Talent OS — AI-drafted outreach messages via OpenRouter chat completions.
NO models hosted on VPS — all generation goes through OpenRouter, same as
services/matcher.py's embedding calls.

IMPORTANT: this module only ever produces DRAFTS. Nothing here sends email.
A human must review and approve a draft (see routers/outreach.py) before it
is sent via services/email_service.py.
"""
import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from core.config import settings

logger = logging.getLogger("talent_os.outreach_ai")

SYSTEM_PROMPT = """You are the outreach copywriter for GSP Recruitment, a young, specialized \
tech recruitment firm based in the Brainport Eindhoven region (Netherlands).

Rules you must always follow:
- Write professional, honest recruitment outreach in Dutch (or English if asked).
- NEVER invent statistics, client names, placement numbers, or other fake claims. \
Only reference the specific job/company context you are given.
- NEVER mention or sign with an individual founder or recruiter's name. Always write \
in the team voice and sign off as "Team GSP Recruitment".
- Keep the email body to roughly 150 words or fewer.
- Always end the body with this exact opt-out line on its own line: \
"Wil je geen berichten meer ontvangen? Antwoord met STOP."
- Mention the specific job title/company context provided to you.
- Respond ONLY with a JSON object of the form {"subject": "...", "body": "..."} — \
no markdown, no code fences, no extra commentary.
"""


def _build_user_prompt(target: Dict[str, Any], context: Dict[str, Any], language: str) -> str:
    lang_label = "Dutch" if language == "nl" else "English"
    lines = [
        f"Write a {lang_label} recruitment outreach email.",
        f"Target name: {target.get('name') or target.get('full_name') or 'there'}",
    ]
    if target.get("company"):
        lines.append(f"Target's current company: {target['company']}")
    if context.get("job_title"):
        lines.append(f"Job title to mention: {context['job_title']}")
    if context.get("job_company"):
        lines.append(f"Hiring company: {context['job_company']}")
    if context.get("job_description"):
        lines.append(f"Job context: {context['job_description'][:800]}")
    if context.get("notes"):
        lines.append(f"Additional notes: {context['notes']}")
    return "\n".join(lines)


def _parse_json_response(raw: str) -> Dict[str, str]:
    """Defensively parse the model's JSON response, tolerating code fences etc."""
    text = raw.strip()
    # Strip markdown code fences if the model added them anyway
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        subject = str(data.get("subject", "")).strip()
        body = str(data.get("body", "")).strip()
        if subject and body:
            return {"subject": subject, "body": body}
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    # Fallback: try to salvage a subject/body out of loosely structured text
    subject_match = re.search(r"subject[\"']?\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    subject = subject_match.group(1).strip().strip('"').strip(",") if subject_match else "GSP Recruitment"
    body = text
    return {"subject": subject[:500], "body": body}


async def draft_email(
    target: Dict[str, Any],
    context: Dict[str, Any],
    language: str = "nl",
) -> Dict[str, str]:
    """
    Draft an outreach email subject + body for a target (candidate or client
    prospect) using OpenRouter chat completions. Returns a dict with
    "subject" and "body" — this is ALWAYS a draft, never sent automatically.
    """
    user_prompt = _build_user_prompt(target, context, language)

    payload = {
        "model": settings.openrouter_chat_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(
        base_url=settings.openrouter_base_url,
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    ) as client:
        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        raw_content: Optional[str] = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logger.error("outreach_ai: unexpected OpenRouter response shape: %s", data)
        raw_content = ""

    return _parse_json_response(raw_content or "")
