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
