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

# VERWERKINGSREGISTER.md §1.3 (OpenRouter-rij): the recipient's real name
# is personal data and never leaves this process. The model only ever sees
# this placeholder token and is instructed to use it verbatim wherever it
# would greet the recipient by name; draft_email() fills in the real name
# itself, locally, after the model has returned the text (see
# _fill_recipient_name() below).
NAME_PLACEHOLDER = "{{RECIPIENT_NAME}}"

SYSTEM_PROMPT = f"""You are the outreach copywriter for GSP Recruitment, a young, specialized \
tech recruitment firm based in the Brainport Eindhoven region (Netherlands).

Rules you must always follow:
- Write professional, honest recruitment outreach in Dutch (or English if asked).
- NEVER invent statistics, client names, placement numbers, or other fake claims. \
Only reference the specific job/company context you are given.
- NEVER mention or sign with an individual founder or recruiter's name. Always write \
in the team voice and sign off as "Team GSP Recruitment".
- You have NOT been given the recipient's real name. Wherever you would address them \
by name (e.g. in the greeting), use exactly this literal placeholder token, unchanged \
and untranslated: {NAME_PLACEHOLDER}. Never invent, guess, or substitute a different \
name or greeting word for it.
- Keep the email body to roughly 150 words or fewer.
- Always end the body with this exact opt-out line on its own line: \
"Wil je geen berichten meer ontvangen? Antwoord met STOP."
- Mention the specific job title/company context provided to you.
- Respond ONLY with a JSON object of the form {{"subject": "...", "body": "..."}} — \
no markdown, no code fences, no extra commentary.
"""


def _build_user_prompt(target: Dict[str, Any], context: Dict[str, Any], language: str) -> str:
    lang_label = "Dutch" if language == "nl" else "English"
    lines = [
        f"Write a {lang_label} recruitment outreach email.",
        f"Recipient name to use in the greeting: the literal token {NAME_PLACEHOLDER} "
        "(you have not been given their real name — see system instructions).",
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


# Matches the token in any form a model might mangle it into: the exact
# braces, a bracket variant, or just the bare word — case-insensitive.
# This is the one regex both _fill_recipient_name() (always substitutes)
# and contains_placeholder_leak() (the storage/approval fail-closed check
# in routers/outreach.py) are built on, so they can never disagree about
# what counts as "leaked".
_PLACEHOLDER_LEAK_RE = re.compile(
    r"\{\{\s*recipient_name\s*\}\}|\[\s*recipient_name\s*\]|recipient_name",
    re.IGNORECASE,
)


def _fill_recipient_name(text: str, name: str) -> str:
    """Replace the AI-facing name placeholder with the real recipient name,
    locally, after the model has already returned its text. Covers the
    exact token plus mangled variants (see _PLACEHOLDER_LEAK_RE) so a
    placeholder can never survive into the returned draft."""
    if not text:
        return text
    return _PLACEHOLDER_LEAK_RE.sub(name, text)


def contains_placeholder_leak(*texts: Optional[str]) -> bool:
    """True if any given string still contains the name placeholder in any
    recognisable form. draft_email() always substitutes it before
    returning (see _fill_recipient_name()) — this is the shared fail-closed
    check callers use before a draft is ever stored or approved, in case a
    future prompt change or an unrelated draft source (e.g. the external
    POST /drafts endpoint) lets one slip through."""
    return any(_PLACEHOLDER_LEAK_RE.search(t or "") for t in texts)


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

    The recipient's real name is never sent to OpenRouter (VERWERKINGSREGISTER.md
    §1.3): the model only sees NAME_PLACEHOLDER and this function fills in
    the real name itself, locally, once the model has returned its text.
    """
    recipient_name = str(target.get("name") or target.get("full_name") or "").strip()
    # No known name at all (e.g. a prospect record with only a title) —
    # fall back to a neutral greeting word rather than leaving the
    # placeholder or an empty string in the sent draft.
    fill_name = recipient_name or ("daar" if language == "nl" else "there")

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

    parsed = _parse_json_response(raw_content or "")
    parsed["subject"] = _fill_recipient_name(parsed["subject"], fill_name)
    parsed["body"] = _fill_recipient_name(parsed["body"], fill_name)
    return parsed


# ── Blog drafting ─────────────────────────────────────────────────────────

BLOG_SYSTEM_PROMPT = """You are an expert tech-recruitment content writer for GSP \
Recruitment, a young, specialized tech recruitment firm based in the Brainport \
Eindhoven region (Netherlands).

Rules you must always follow:
- Write honest, specific, well-informed content about the Brainport tech job \
market, hiring, salaries, and engineering careers.
- NEVER invent statistics, survey results, client names, or placement numbers. \
You MAY reference "onze interne benchmarks" (our internal benchmarks) when \
discussing salary ranges, but do not attach fake precise numbers or sources to it.
- Write in the team voice. Do not mention or sign with an individual founder or \
recruiter's name.
- Each body must be approximately 600 words of clean HTML using ONLY <h2>, <p>, \
and <ul>/<li> tags — no other tags, no inline styles, no markdown.
- Produce both a Dutch (nl) and an English (en) version of the full article — \
not translations of each other word-for-word, but both complete, well-written \
articles covering the same topic and structure.
- The slug must be a short, URL-safe, lowercase, hyphenated string derived from \
the English title (matching ^[a-z0-9-]+$).
- Respond ONLY with a JSON object of the form:
{"slug": "...", "title_nl": "...", "title_en": "...", "excerpt_nl": "...", \
"excerpt_en": "...", "body_nl": "...", "body_en": "...", "tags": ["...", "..."], \
"read_time_min": 5}
No markdown, no code fences, no extra commentary — JSON only.
"""


def _parse_blog_json_response(raw: str) -> Dict[str, Any]:
    """Defensively parse the model's blog JSON response, tolerating code
    fences, stray commentary, and malformed JSON."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    data: Dict[str, Any] = {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # Fallback: try to salvage a JSON object embedded in extra text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except (json.JSONDecodeError, TypeError):
                data = {}

    if not isinstance(data, dict):
        data = {}

    slug = str(data.get("slug", "")).strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-") or "untitled-post"

    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]

    try:
        read_time_min = int(data.get("read_time_min", 5))
    except (TypeError, ValueError):
        read_time_min = 5

    return {
        "slug": slug,
        "title_nl": str(data.get("title_nl", "")).strip(),
        "title_en": str(data.get("title_en", "")).strip(),
        "excerpt_nl": str(data.get("excerpt_nl", "")).strip(),
        "excerpt_en": str(data.get("excerpt_en", "")).strip(),
        "body_nl": str(data.get("body_nl", "")).strip(),
        "body_en": str(data.get("body_en", "")).strip(),
        "tags": tags,
        "read_time_min": read_time_min,
    }


async def draft_blog(topic: str) -> Dict[str, Any]:
    """
    Draft a full bilingual (nl/en) blog post for the given topic using
    OpenRouter chat completions. Returns a dict with slug, title_nl,
    title_en, excerpt_nl, excerpt_en, body_nl, body_en, tags, read_time_min.
    This is ALWAYS a draft — routers/blog_admin.py requires an explicit
    human "publish" action before anything appears on the public site.
    """
    user_prompt = (
        f"Write a blog post about: {topic}\n\n"
        "Follow the system instructions exactly, including the JSON response format."
    )

    payload = {
        "model": settings.openrouter_chat_model,
        "messages": [
            {"role": "system", "content": BLOG_SYSTEM_PROMPT},
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
        timeout=90.0,
    ) as client:
        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        raw_content: Optional[str] = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        logger.error("outreach_ai: unexpected OpenRouter response shape (blog): %s", data)
        raw_content = ""

    return _parse_blog_json_response(raw_content or "")
