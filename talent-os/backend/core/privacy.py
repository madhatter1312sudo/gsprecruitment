"""
Talent OS — small GDPR/AVG-shared helpers (WS-E.7).

Kept dependency-free (stdlib only) so gdpr.py, outreach.py and any admin
suppression-list endpoint can share one definition of "how do we hash an
e-mail for the suppression list" without importing each other.
"""
import hashlib
import re
from typing import Optional


def normalize_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def email_hash(email: Optional[str]) -> str:
    """sha256 of the lower-cased, trimmed e-mail address. This is what goes
    into suppression_list.email_hash and is compared against on every
    outreach approval — never the plaintext address."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def email_domain(email: Optional[str]) -> Optional[str]:
    e = normalize_email(email)
    return e.split("@", 1)[1] if "@" in e else None


_EMAIL_LIKE_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def redact_emails(text: Optional[str]) -> Optional[str]:
    """Replace any e-mail-looking substring in free text with a short hash
    marker, using the same email_hash() this module uses for
    suppression_list -- security-audit follow-up (WS-C.17 L2): an admin's
    free-text `evidence` note for talentpool-consent (routers/admin.py)
    can easily contain the candidate's own e-mail address; this keeps
    audit_log.changes (json.dumps'd, never a raw dict -- commit 72b4bcd)
    from ever storing that plaintext, while the hash still lets someone
    cross-reference the same address elsewhere (suppression_list,
    candidates.email via email_hash()) if they need to."""
    if not text:
        return text
    return _EMAIL_LIKE_RE.sub(lambda m: f"[redacted:{email_hash(m.group(0))[:16]}]", text)


# ── AI pseudonimisering (VERWERKINGSREGISTER.md §1.3, OpenRouter-rij) ─────
# services/matcher.py sends candidate text to OpenRouter (embeddings) for
# semantic matching. A cv_text field routinely carries name, e-mail,
# phone, address and a public profile URL, none of which help a
# similarity score. pseudonymize_cv_text() strips what it can recognise
# before that text ever leaves this process, chosen over dropping cv_text
# entirely (the simpler, safer option) because it keeps most of the
# semantic signal — skills/experience prose — that drives match quality;
# see tests/test_privacy_pseudonymize.py for the measured effect on a
# sample CV and the edge cases (NL/non-Western names, e-mail formats,
# phone numbers with/without country code, LinkedIn/GitHub URLs) this is
# tested against.
#
# This is a best-effort minimiser, not a guarantee of full anonymisation:
# it removes what it can reliably recognise (the candidate's own known
# full_name as a literal phrase/parts, e-mail addresses, LinkedIn/GitHub/
# http(s) URLs, and phone-number-shaped digit runs) and leaves the rest of
# the CV prose untouched. Free-text CVs can still contain other
# identifying detail (a very distinctive job title, a small employer,
# a rare combination of skills) that no regex catches — that residual risk
# is accepted here as proportionate, same as the SOP already does for
# public profile text used in sourcing (see §2.2).

_URL_RE = re.compile(
    r"(?:https?://\S+|www\.\S+|(?:linkedin|github)\.com/\S+)",
    re.IGNORECASE,
)

# Real Dutch/international phone numbers are dialled with an explicit
# prefix -- "+31...", "0031..." or a leading trunk "0" (06, 010, 0800...).
# Requiring that prefix is what keeps this from also eating year ranges
# like "2015-2020" (8 digits, no +/0 prefix) out of a CV's work history.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d[\d\s().-]{6,15}\d|0\d[\d\s().-]{6,15}\d)(?!\d)"
)


def _digit_count(s: str) -> int:
    return sum(ch.isdigit() for ch in s)


def _redact_urls(text: str) -> str:
    return _URL_RE.sub("[URL]", text)


def _redact_phones(text: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        token = m.group(0)
        # >=9 digits: a bare Dutch mobile/landline is 10 digits (incl.
        # leading 0) or 9 after a +31 country code -- this floor avoids
        # false-positiving shorter digit runs (postcodes, KVK-ish numbers)
        # that happen to start with 0.
        return "[TELEFOON]" if _digit_count(token) >= 9 else token

    return _PHONE_RE.sub(repl, text)


def _redact_known_name(text: str, full_name: Optional[str]) -> str:
    """Strip a *known* name (the candidate's own full_name column) out of
    free text, rather than trying to guess at names in general -- guessing
    is exactly where NL vs. non-Western name heuristics fall over. Matches
    the full phrase (natural order, reversed, and "Achternaam, Voornaam"),
    then each individual name part (3+ chars) as a standalone word, so a
    lone first-name mention elsewhere in the CV ("Groetjes, Aisha") is
    also caught."""
    if not full_name or not full_name.strip():
        return text

    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if not parts:
        return text

    escaped = [re.escape(p) for p in parts]
    phrase_patterns = [r"\s+".join(escaped)]
    if len(escaped) > 1:
        phrase_patterns.append(r"\s+".join(reversed(escaped)))
        phrase_patterns.append(
            escaped[-1] + r"\s*,\s*" + r"\s+".join(escaped[:-1])
        )
    for pattern in phrase_patterns:
        text = re.sub(pattern, "[NAAM]", text, flags=re.IGNORECASE)

    for part in parts:
        if len(part) >= 3:
            text = re.sub(
                r"(?<!\w)" + re.escape(part) + r"(?!\w)",
                "[NAAM]",
                text,
                flags=re.IGNORECASE,
            )
    return text


def pseudonymize_cv_text(cv_text: Optional[str], full_name: Optional[str] = None) -> str:
    """Best-effort strip of directly identifying data from CV free text
    before it is sent to OpenRouter for embedding (services/matcher.py).
    Order matters: redact on the *full* text first, then callers truncate
    the result -- truncating first can cut an e-mail/phone/URL in half and
    leave an identifying fragment (e.g. the local part of an address)
    past the cut. Always returns a string (never None)."""
    text = cv_text or ""
    if not text:
        return ""
    text = redact_emails(text)
    text = _redact_urls(text)
    text = _redact_phones(text)
    text = _redact_known_name(text, full_name)
    return text


# ── WS-C.17: shared talentpool lawful_basis "flip" rule ──────────────────
# One rule, used identically by the candidate portal, the public confirm
# flow, and the admin endpoint (security-audit follow-up H3a): a
# candidate's lawful_basis becomes 'opt_in_talentpool' only when it is
# currently NULL or already 'opt_in_talentpool' -- NEVER when it is
# 'portal_registratie' (that candidate's basis is their own portal
# registration, Art. 13, and stays that way regardless of a talentpool
# tick) or any other sourced basis. Ticking the talentpool box always
# records the four consent_talentpool_* columns; it only sometimes also
# changes lawful_basis, and never silently overwrites a different one.
def should_set_talentpool_lawful_basis(current_lawful_basis: Optional[str]) -> bool:
    return current_lawful_basis in (None, "opt_in_talentpool")
