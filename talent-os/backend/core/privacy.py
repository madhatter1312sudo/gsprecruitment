"""
Talent OS — small GDPR/AVG-shared helpers (WS-E.7).

Kept dependency-free (stdlib only) so gdpr.py, outreach.py and any admin
suppression-list endpoint can share one definition of "how do we hash an
e-mail for the suppression list" without importing each other.
"""
import hashlib
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
