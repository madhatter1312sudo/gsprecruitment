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
# The third alternative has no +/0 prefix requirement at all -- security-audit
# follow-up (point 8): "6-12345678" and "612345678" (a mobile number typed
# without its leading trunk zero) were previously missed entirely. Digit-run
# length still guards this: the digit-count check in _redact_phones() below
# requires >=9 digits before anything is actually redacted, which is what
# keeps "2015-2020" (8 digits, no prefix) safe while still catching a bare
# 9- or 10-digit mobile number.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d[\d\s().-]{6,15}\d|0\d[\d\s().-]{5,14}\d|\d[\d\s().-]{6,14}\d)(?!\d)"
)


def _digit_count(s: str) -> int:
    return sum(ch.isdigit() for ch in s)


# ── security-audit follow-up (blocking finding 1): a Dutch CV's contact
# block (address, postcode, birthdate, BSN, IBAN) survived pseudonymisation
# entirely -- none of the patterns above are shaped to catch it, and a
# Dutch postcode+house-number combination on its own identifies one
# household. Two layers, per the audit:
#
#  1. _strip_contact_block(): cut the lines that *look like* a contact
#     block out of the CV's header (name/address/phone/e-mail block most
#     Dutch CVs open with), up to the first blank line -- this is the only
#     reliable way to remove a bare street name + house number, which no
#     regex below can recognise on its own. Line-scoped and marker-gated so
#     a CV that opens with profile prose (no blank-line-delimited header,
#     or a header line with none of these markers) is left untouched.
#  2. _redact_dutch_identifiers(): a global regex pass for the specific
#     shapes named in the audit (postcode, dd-mm-yyyy date, a bare 9-digit
#     BSN-shaped run, an IBAN-shaped run) -- run over the *whole* text, not
#     just the header, in case one of these appears in the CV body too.
# Note this is deliberately narrower than "any contact marker": an e-mail
# address or phone number *alone* on a header line (e.g. "jan@x.nl | +31 6
# ...  | Eindhoven") is left for the ordinary e-mail/phone/URL redaction
# steps below to clean up in place -- they turn it into "[EMAIL] |
# [TELEFOON] | Eindhoven" and the city name (real matching signal, not on
# its own identifying) survives. This regex instead flags the marker
# combinations that identify a *household or a specific individual* and
# that no single-token regex can safely clean in place -- chiefly a bare
# Dutch street name + house number, which has no fixed token shape to
# substitute -- so those lines are dropped outright.
_CONTACT_LINE_RE = re.compile(
    r"\b\d{4}\s?[A-Z]{2}\b"                             # NL postcode
    r"|\b\d{1,2}[-/]\d{1,2}[-/](?:19|20)\d{2}\b"        # dd-mm-yyyy
    r"|(?<!\d)\d{9,10}(?!\d)"                           # BSN/phone-shaped run
    r"|\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"                # IBAN-shaped
    r"|geboortedatum|geboren op|\bbsn\b|nationaliteit"
    r"|(?:straat|laan|plein|kade|dijk|hof|steeg|singel|weg)\s*\d{1,4}\b",
    re.IGNORECASE,
)


def _strip_contact_block(text: str) -> str:
    """Drop lines from the CV's leading header (up to the first blank
    line) that carry a household- or person-identifying combination --
    postcode, a Dutch street name + house number, a birthdate, a BSN- or
    IBAN-shaped digit run -- none of which a single-token regex can safely
    substitute in place (unlike an e-mail or phone number, there's no
    reusable "[ADRES]" shape for "Kerkstraat 12"). Line-scoped rather than
    dropping the whole header verbatim, so a title line ("Senior Embedded
    Software Engineer") sitting between the name and the address survives,
    and a header line with only an e-mail/phone/city on it (no address, no
    postcode) is left for the ordinary per-token redaction steps.

    Conservative: a CV with no blank line in it at all is left completely
    untouched here (nothing to safely call "the header") -- the global
    regex layer below is what still catches a postcode/date/BSN/IBAN in
    that case."""
    m = re.search(r"\n\s*\n", text)
    if not m:
        return text
    head, gap, rest = text[: m.start()], text[m.start() : m.end()], text[m.end() :]
    kept = [line for line in head.split("\n") if not _CONTACT_LINE_RE.search(line)]
    return "\n".join(kept) + gap + rest


_POSTCODE_RE = re.compile(r"\b\d{4}\s?[A-Z]{2}\b")
_DUTCH_DATE_RE = re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/](?:19|20)\d{2}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_BSN_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")


def _redact_dutch_identifiers(text: str) -> str:
    text = _POSTCODE_RE.sub("[POSTCODE]", text)
    text = _DUTCH_DATE_RE.sub("[DATUM]", text)
    text = _IBAN_RE.sub("[IBAN]", text)
    # BSN last: by this point real phone numbers are already [TELEFOON],
    # so a remaining bare 9-digit run is the shape the audit flagged.
    text = _BSN_RE.sub("[BSN]", text)
    return text


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


# security-audit follow-up (blocking finding 2): the loose-part pass below
# used to strip *any* 3+ char name part as a standalone word. For a name
# with a Dutch tussenvoegsel ("Jan van der Berg") that destroyed "van" and
# "der" wherever they occurred as ordinary Dutch words elsewhere in the CV
# ("... ontwikkeling van der Berg firmware ..." -> "... ontwikkeling [NAAM]
# [NAAM] firmware ..." — this list is what "van der Berg" itself gets
# matched by the phrase-pattern above already, this per-word guard is only
# about a bare "van"/"der" appearing on its own, unrelated to the name).
# These particles are never identifying on their own, so they are always
# skipped in the loose per-word pass -- the full-name phrase match above is
# untouched and still catches "Jan van der Berg" as one unit.
_NAME_PARTICLES = {
    "van", "de", "den", "der", "ter", "ten", "het", "aan", "in", "op",
    "bij", "vander", "vanden", "vande", "el", "al", "von", "zu", "'t",
}


def _redact_known_name(text: str, full_name: Optional[str]) -> str:
    """Strip a *known* name (the candidate's own full_name column) out of
    free text, rather than trying to guess at names in general -- guessing
    is exactly where NL vs. non-Western name heuristics fall over. Matches
    the full phrase (natural order, reversed, and "Achternaam, Voornaam"),
    then each individual name part (4+ chars, skipping Dutch tussenvoegsels
    and similar particles -- see _NAME_PARTICLES) as a standalone word, so a
    lone first-name mention elsewhere in the CV ("Groetjes, Aisha") is
    also caught.

    Known residual risk, accepted rather than "fixed" (VERWERKINGSREGISTER.md
    §1.3): a surname that also happens to be an employer/vendor name (e.g.
    full_name="Erik Bosch") still gets redacted wherever it stands alone --
    "Bosch-sensoren" becomes "[NAAM]-sensoren" -- because it genuinely *is*
    part of this candidate's own name and there is no reliable way to tell
    that occurrence apart from an actual self-reference; erring toward
    redaction is the safer failure mode for a privacy control."""
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
        if len(part) >= 4 and part.lower() not in _NAME_PARTICLES:
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
    past the cut. Always returns a string (never None).

    Contact-block stripping runs first so the address/postcode/birthdate/
    BSN/IBAN lines it removes never even reach the per-token regexes below
    (security-audit follow-up, blocking finding 1)."""
    text = cv_text or ""
    if not text:
        return ""
    text = _strip_contact_block(text)
    # A fixed [EMAIL] token, not redact_emails()'s sha256 hash -- that hash
    # is a stable identifier an LLM provider could use to correlate the
    # same person across separate matching runs, and it adds nothing to a
    # similarity score either way (security-audit follow-up, finding 7).
    text = _EMAIL_LIKE_RE.sub("[EMAIL]", text)
    text = _redact_urls(text)
    # IBAN/postcode/date/BSN before phone: an IBAN's trailing digit block
    # (e.g. "...ABNA0417164300") is itself phone-shaped once split off from
    # its letter prefix, so the widened bare-digit phone alternative (see
    # _PHONE_RE, finding 8) would otherwise eat half of it first and leave
    # the IBAN half-redacted.
    text = _redact_dutch_identifiers(text)
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
