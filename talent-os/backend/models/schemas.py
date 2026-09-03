"""Talent OS — Pydantic schemas for request/response models."""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Any, Literal
from datetime import datetime, date
from decimal import Decimal


# ── Auth / Users ─────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field("candidate", pattern=r"^(candidate|client)$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class SetPasswordRequest(BaseModel):
    """WS-E.3 team-invite flow: consumes the same one-time token mechanism
    as e-mail verification (verification_token_hash), sets the invitee's
    chosen password, and marks the e-mail verified in the same step."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


# ── WS-C.17 talentpool consent (migrations/030_talentpool_consent.py) ────

TALENTPOOL_CONSENT_SCOPES = ("matching_only", "matching_and_contact")


class TalentpoolConsentUpdate(BaseModel):
    """Candidate portal: POST /api/v1/candidate/talentpool-consent.
    consent=True sets consent_talentpool_at/_until/_scope (source='portal');
    consent=False clears all three (withdrawal) -- see SOP §1.5."""
    consent: bool
    scope: Optional[str] = None

    @field_validator("scope")
    @classmethod
    def _scope_in_set(cls, v):
        if v is not None and v not in TALENTPOOL_CONSENT_SCOPES:
            raise ValueError(f"scope must be one of {TALENTPOOL_CONSENT_SCOPES}")
        return v


class TalentpoolOptinRequest(BaseModel):
    """Public: POST /api/public/talentpool-optin -- e-mail + consent tick
    from website/kandidaten.html or website/blog/post.html's CTA. Does not
    itself set anything on `candidates`; only issues a confirmation e-mail
    (routers/public.py talentpool_public_router). Consent only becomes
    effective once the token is confirmed via talentpool-confirm."""
    email: EmailStr
    consent: bool
    scope: str
    source: str

    @field_validator("scope")
    @classmethod
    def _scope_in_set(cls, v):
        if v not in TALENTPOOL_CONSENT_SCOPES:
            raise ValueError(f"scope must be one of {TALENTPOOL_CONSENT_SCOPES}")
        return v

    @field_validator("source")
    @classmethod
    def _source_in_set(cls, v):
        if v not in ("kandidaten_page", "blog_cta"):
            raise ValueError("source must be one of ('kandidaten_page', 'blog_cta')")
        return v


class TalentpoolConfirmRequest(BaseModel):
    """Public: POST /api/public/talentpool-confirm. token is the raw,
    single-use value e-mailed to the candidate (only its sha256 hash is
    ever stored -- core.security.hash_token, same as WS-E.2's verify-email
    flow)."""
    token: str


class AdminTalentpoolConsentUpdate(BaseModel):
    """Admin: PATCH /api/v1/admin/candidates/{id}/talentpool-consent.
    `evidence` is mandatory -- a short note on what evidence of consent
    the admin has on file (e.g. a signed form, an e-mail) since this
    endpoint records consent on the candidate's behalf rather than
    capturing a live tick of the box."""
    consent: bool
    scope: Optional[str] = None
    evidence: str = Field(..., min_length=1, max_length=2000)

    @field_validator("scope")
    @classmethod
    def _scope_in_set(cls, v):
        if v is not None and v not in TALENTPOOL_CONSENT_SCOPES:
            raise ValueError(f"scope must be one of {TALENTPOOL_CONSENT_SCOPES}")
        return v


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


# ── MFA (WS-E.12, admin TOTP) ────────────────────────────────────────────

class MfaRequiredResponse(BaseModel):
    """Returned by POST /api/auth/login in place of TokenResponse when the
    account has MFA enabled -- see routers/auth.py login() and
    core/mfa.py issue_mfa_pending_token."""
    mfa_required: bool = True
    mfa_token: str


class MfaSetupResponse(BaseModel):
    otpauth_uri: str
    qr_svg: str
    secret: str


class MfaEnableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class MfaEnableResponse(BaseModel):
    message: str
    recovery_codes: List[str]


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(..., min_length=6, max_length=8)


class MfaRecoveryRequest(BaseModel):
    mfa_token: str
    recovery_code: str = Field(..., min_length=6, max_length=16)


class MfaDisableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class MfaStatusResponse(BaseModel):
    mfa_enabled: bool


# ── Candidate ───────────────────────────────────────────────────────────

def _normalize_http_url(v: Optional[str]) -> Optional[str]:
    # These values are rendered as links in the admin panel; refuse
    # javascript:/data:/etc. schemes at the source (defense in depth —
    # the admin UI also whitelists schemes before emitting an href).
    if v is None or v.strip() == "":
        return v
    s = v.strip()
    lowered = s.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return s
    if "://" in lowered or lowered.startswith(("javascript:", "data:", "vbscript:")):
        raise ValueError("URL must start with http:// or https://")
    # Bare domain like "linkedin.com/in/x" — normalize to https.
    return "https://" + s


class CandidateCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    location: Optional[str] = None
    willing_to_relocate: bool = False
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None
    notice_period_days: Optional[int] = None
    years_experience: Optional[float] = None
    skills: List[str] = []
    languages: List[str] = []
    education: Optional[str] = None
    cv_text: Optional[str] = None
    source: str = "apollo"
    # WS-E.7 provenance/lawful_basis (SOP §2, VERWERKINGSREGISTER §1.1).
    # Optional here (and therefore on CandidateResponse, which subclasses
    # this) because the existing Apollo pool has neither a real http(s)
    # source_url (it stores 'apollo:<id>' — see harvest.py) nor a
    # lawful_basis, and every read of that pool goes through this same
    # model. The mandatory version used at the sourcing insert path is
    # CandidateSourceCreate below — do not add an http-only validator or a
    # Field(...) default here, it would break every existing GET/list call.
    source_url: Optional[str] = None
    lawful_basis: Optional[str] = Field(
        None, pattern=r"^(gerechtvaardigd_belang|opt_in_talentpool|toestemming_referral|portal_registratie)$"
    )
    date_found: Optional[date] = None
    sourced_by_agent: Optional[str] = None
    strength_score: Optional[float] = Field(None, ge=1.0, le=10.0)
    switch_readiness: Optional[str] = Field(None, pattern=r"^(LOW|MEDIUM|HIGH|ACTIVE)$")
    tags: List[str] = []

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def _url_scheme_http_only(cls, v):
        return _normalize_http_url(v)

    # DB rows (esp. the Apollo-bulk pool) store NULL for these array columns;
    # coerce NULL -> [] so ResponseValidationError isn't raised on read.
    @field_validator("skills", "languages", "tags", mode="before")
    @classmethod
    def _none_to_empty_list(cls, v):
        return v if v is not None else []


class CandidateResponse(CandidateCreate):
    # Read path: harvest.py writes these columns via raw SQL (no model), so
    # a bad scheme in one row must not 500 the whole list — coerce, don't raise.
    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def _url_scheme_http_only(cls, v):
        try:
            return _normalize_http_url(v)
        except ValueError:
            return None

    id: int
    status: str = "sourced"
    is_passive: bool = True
    screening_score: Optional[int] = None
    screening_notes: Optional[str] = None
    quality_score: Optional[float] = None
    cv_file_path: Optional[str] = None
    created_at: datetime
    # NOT required: no INSERT into candidates (create_candidate, the
    # webhook, portal registration, harvest.py, scheduler.py) ever sets
    # this column explicitly, so any row inserted before the column
    # picked up a DEFAULT NOW() (see migrations/027_candidates_updated_at_default.py)
    # reads back NULL here -- a required datetime raised
    # ResponseValidationError on GET /api/candidates and GET
    # /api/candidates/{id} for every such row.
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CandidateSourceCreate(CandidateCreate):
    """POST /api/candidates (X-API-Key sourcing path) only — WS-E.7,
    SOP §2 "geen bron-URL = geen contact". Unlike CandidateCreate,
    source_url and lawful_basis are mandatory here: this endpoint is for
    manually-sourced people (LinkedIn/GitHub/meetup/referral per the SOP),
    not for portal self-registration (routers/candidate.py sets
    lawful_basis='portal_registratie' + the portal URL itself, without
    going through this model) or opt-in talentpool (WS-C.17, same
    exemption, SOP §1.5). date_found defaults to today if not supplied —
    it is the anchor for the "3 months after date_found" retention clock
    (SOP §6)."""
    source_url: str = Field(..., min_length=1)
    lawful_basis: str = Field(
        ..., pattern=r"^(gerechtvaardigd_belang|opt_in_talentpool|toestemming_referral|portal_registratie)$"
    )
    date_found: date = Field(default_factory=date.today)

    @field_validator("source_url")
    @classmethod
    def _source_url_must_be_http(cls, v):
        s = (v or "").strip()
        if not (s.lower().startswith("http://") or s.lower().startswith("https://")):
            raise ValueError("source_url must be a public http:// or https:// URL (SOP §2)")
        return s


class CandidateAdminUpdate(BaseModel):
    """PATCH /api/candidates/{id} (X-API-Key, internal/agent use) -- the
    same allow-listed fields the router used to accept as a raw dict."""
    status: Optional[str] = None
    screening_score: Optional[int] = None
    screening_notes: Optional[str] = None
    quality_score: Optional[float] = None
    screened_by_agent: Optional[str] = None
    strength_score: Optional[float] = Field(None, ge=1.0, le=10.0)
    switch_readiness: Optional[str] = Field(None, pattern=r"^(LOW|MEDIUM|HIGH|ACTIVE)$")
    tags: Optional[List[str]] = None


class CandidatePortalProfile(BaseModel):
    """Full candidate profile combining users + candidate_profiles."""
    id: int
    user_id: int
    email: str
    full_name: str
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    location: Optional[str] = None
    willing_to_relocate: bool = False
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None
    notice_period_days: Optional[int] = None
    years_experience: Optional[float] = None
    skills: List[str] = []
    languages: List[str] = []
    education: Optional[str] = None
    cv_text: Optional[str] = None
    cv_file_path: Optional[str] = None
    # WS-C.17: read from the linked `candidates` row (C.16 FK /
    # get_or_create_candidate_id), not candidate_profiles -- these four
    # live on candidates alongside lawful_basis. None/None/None/None when
    # no candidates row exists yet or no talentpool consent has ever been
    # recorded.
    consent_talentpool_at: Optional[datetime] = None
    consent_talentpool_until: Optional[datetime] = None
    consent_scope: Optional[str] = None
    consent_source: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class CandidateProfileUpdate(BaseModel):
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def _url_scheme_http_only(cls, v):
        return _normalize_http_url(v)
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    location: Optional[str] = None
    willing_to_relocate: Optional[bool] = None
    salary_expectation_min: Optional[int] = None
    salary_expectation_max: Optional[int] = None
    notice_period_days: Optional[int] = None
    years_experience: Optional[float] = None
    skills: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    education: Optional[str] = None
    cv_text: Optional[str] = None


# ── Job Order ───────────────────────────────────────────────────────────

class JobOrderCreate(BaseModel):
    client_id: int
    title: str = Field(..., min_length=1)
    department: Optional[str] = None
    seniority: Optional[str] = None
    location_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "EUR"
    description: Optional[str] = None
    requirements: Optional[str] = None
    nice_to_have: Optional[str] = None
    urgency: str = "normal"
    city: Optional[str] = None
    company_display: Optional[str] = None
    employment_type: Optional[Literal["vast", "detachering", "interim"]] = None
    sponsorship_possible: bool = False


class JobOrderResponse(JobOrderCreate):
    id: int
    status: str = "open"
    fee_percentage: float = 20.0
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOrderUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    department: Optional[str] = None
    seniority: Optional[str] = None
    location_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    nice_to_have: Optional[str] = None
    status: Optional[str] = None
    urgency: Optional[str] = None
    city: Optional[str] = None
    company_display: Optional[str] = None
    employment_type: Optional[Literal["vast", "detachering", "interim"]] = None
    sponsorship_possible: Optional[bool] = None


# ── Match ───────────────────────────────────────────────────────────────

class MatchCreate(BaseModel):
    """Create/upsert a match — used by external agents (e.g. a Claude cloud
    agent doing matching) instead of the in-backend OpenRouter matcher."""
    candidate_id: int
    job_id: int
    match_score: float = Field(..., ge=0, le=100)
    status: str = "suggested"
    rationale: Optional[str] = None  # no rationale column yet — accepted but not persisted


class MatchResponse(BaseModel):
    # match_breakdown intentionally omitted: no code path ever writes it
    # (grepped routers/matches.py, services/matcher.py) so it would only
    # ever serialize as null. The `matches.match_breakdown` DB column is
    # left in place (no migration needed to drop an always-null column).
    id: int
    job_id: int
    candidate_id: int
    match_score: Optional[float] = None
    status: str = "pending"
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Webhook ─────────────────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    action: str = Field(..., pattern=r"^(candidate_found|candidate_updated|signal_detected|placement_update)$")
    agent: Optional[str] = None
    data: dict = {}


# ── Health ──────────────────────────────────────────────────────────────

class PublicHealthResponse(BaseModel):
    """GET /health -- public, unauthenticated. Deliberately minimal: no row
    counts, no vendor/integration status (see WS-C.3a; those moved to the
    admin-only GET /api/v1/admin/health)."""
    status: str
    version: str = "1.0.0"
    database: str = "unknown"


class HealthResponse(BaseModel):
    """GET /api/v1/admin/health -- admin-JWT only."""
    status: str
    version: str = "1.0.0"
    database: str = "unknown"
    openrouter: str = "unknown"
    apollo: str = "unknown"
    candidates_count: Optional[int] = None
    open_jobs: Optional[int] = None


# ── Candidate Portal Schemas ────────────────────────────────────────────

class CandidateMatchItem(BaseModel):
    id: int
    job_id: int
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    match_score: Optional[float] = None
    status: str = "pending"
    created_at: datetime


class ApplicationCreate(BaseModel):
    job_id: int


class SavedJobCreate(BaseModel):
    job_id: int


class CandidateDashboard(BaseModel):
    match_count: int = 0
    profile_views: int = 0
    unread_messages: int = 0
    saved_jobs_count: int = 0
    applications_count: int = 0


class SalaryBenchmarkResponse(BaseModel):
    role_title: str
    seniority: Optional[str] = None
    location: Optional[str] = None
    currency: str = "EUR"
    p25: int
    p50: int
    p75: int
    p90: int
    sample_size: Optional[int] = None


# ── Client Portal Schemas ───────────────────────────────────────────────

class ClientDashboard(BaseModel):
    active_jobs: int = 0
    total_candidates_matched: int = 0
    candidates_in_pipeline: int = 0
    interviews_scheduled: int = 0
    offers_made: int = 0
    placements: int = 0
    unread_messages: int = 0


class ClientJobCreate(BaseModel):
    title: str = Field(..., min_length=1)
    department: Optional[str] = None
    seniority: Optional[str] = None
    location_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "EUR"
    description: Optional[str] = None
    requirements: Optional[str] = None
    nice_to_have: Optional[str] = None
    urgency: str = "normal"


class ClientJobUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    department: Optional[str] = None
    seniority: Optional[str] = None
    location_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    nice_to_have: Optional[str] = None
    status: Optional[str] = None
    urgency: Optional[str] = None


class CandidateSearchParams(BaseModel):
    specialisation: Optional[str] = None
    level: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    availability: Optional[str] = None
    years_experience_min: Optional[float] = None
    years_experience_max: Optional[float] = None
    skills: Optional[List[str]] = None
    limit: int = 20
    offset: int = 0


class PipelineAdd(BaseModel):
    candidate_id: int
    job_id: int
    stage: str = "sourced"
    notes: Optional[str] = None


class ClientAnalytics(BaseModel):
    time_to_hire_avg_days: Optional[float] = None
    pipeline_funnel: dict = {}
    source_breakdown: dict = {}
    offer_rate: Optional[float] = None
    cost_per_hire_avg: Optional[float] = None


class TeamInvite(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    # Privilege-escalation fix (WS-C.2): a client-invited teammate can only
    # ever be role=client. Server also hardcodes 'client' in the INSERT
    # regardless of this value, so this is defense in depth, not the only gate.
    role: Literal["client"] = "client"


# ── Admin Portal Schemas ────────────────────────────────────────────────

class AdminDashboard(BaseModel):
    total_users: int = 0
    active_jobs: int = 0
    registered_candidates: int = 0
    active_clients: int = 0
    placements_this_week: int = 0


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, pattern=r"^(candidate|client|admin)$")
    is_verified: Optional[bool] = None


class AdminJobUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    seniority: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    fee_percentage: Optional[float] = None
    urgency: Optional[str] = None
    # WS-C.15 / WS-A.5 (migrations/016_job_orders_columns.py). employment_type
    # is validated here (suspenders) on top of the DB CHECK constraint
    # (belt) -- same pattern as quiz_questions.domain in migrations/012.
    city: Optional[str] = None
    company_display: Optional[str] = None
    employment_type: Optional[Literal["vast", "detachering", "interim"]] = None
    sponsorship_possible: Optional[bool] = None


class AdminJobCreate(BaseModel):
    """WS-B.2: an admin records a job on a client's behalf -- e.g. a
    telephone assignment where the client has no portal login yet. Mirrors
    JobOrderCreate/ClientJobCreate plus the WS-C.15 public-facing columns,
    with an explicit client_id (a client posting their own job never
    supplies one -- it's derived from their session) and a settable
    status, defaulting to 'draft' so nothing an admin phones in reaches the
    public board unpublished-but-live by accident."""
    client_id: int
    title: str = Field(..., min_length=1)
    department: Optional[str] = None
    seniority: Optional[str] = None
    location_type: Optional[str] = None
    city: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    employment_type: Optional[Literal["vast", "detachering", "interim"]] = None
    sponsorship_possible: bool = False
    # security-auditor LOW finding: was a bare `str`, letting the caller
    # set job_orders.status to any string at all (typos included) with no
    # validation -- constrained to the same three values update_any_job's
    # AdminJobUpdate.status effectively supports downstream.
    status: Literal["draft", "open", "closed"] = "draft"


class AdminAnalytics(BaseModel):
    user_growth: dict = {}
    job_fill_rate: Optional[float] = None
    client_retention_rate: Optional[float] = None
    candidate_satisfaction: Optional[float] = None


class AuditLogEntry(BaseModel):
    id: int
    action: str
    actor_id: Optional[int] = None
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    changes: Optional[dict] = None
    created_at: datetime


class ContentItem(BaseModel):
    id: int
    section: str
    key: str
    value: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class ContentUpdate(BaseModel):
    value: str


class SystemSettings(BaseModel):
    key: str
    value: str


class SystemSettingsUpdate(BaseModel):
    settings: dict


# ── Public API Schemas ──────────────────────────────────────────────────

class SiteContentResponse(BaseModel):
    section: str
    items: List[dict]


LEAD_INTEREST_TYPES = ("werving_selectie", "detachering_internationaal", "kandidaat", "overig")

# WS-C.10 code-review follow-ups: website/contact.html's <select> sent
# these six values before this PR's fix -- candidate/client/partner, plus
# uitzenden/detacheren/zzp_bemiddeling (WS-A.3, the staffing/secondment/
# freelance-placement options) -- and quiz submissions (website/script.js)
# hardcoded 'candidate'. Any in-flight/cached page, or a request replayed
# from history, can still arrive with one of these for a while after the
# site itself is fixed. Same remap as migrations/026_leads_interest_type.py's
# UPDATEs, kept in sync deliberately: candidate -> kandidaat, client ->
# werving_selectie, partner -> overig, and uitzenden/detacheren/
# zzp_bemiddeling -> detachering_internationaal (all three are staffing/
# secondment/freelance variants, the same bucket the canonical select's
# second option now covers).
_LEGACY_INTEREST_TYPE_MAP = {
    "candidate": "kandidaat",
    "client": "werving_selectie",
    "partner": "overig",
    "uitzenden": "detachering_internationaal",
    "detacheren": "detachering_internationaal",
    "zzp_bemiddeling": "detachering_internationaal",
}


class LeadSubmit(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    company: Optional[str] = None
    phone: Optional[str] = None
    message: str = Field(..., min_length=1)
    # validate_default=True: the normalising validator below must run even
    # when the caller omits interest_type entirely (default None), not
    # only when an explicit bad value is sent -- pydantic v2 skips
    # validators on unsupplied defaults otherwise.
    interest_type: Optional[str] = Field(None, validate_default=True)

    @field_validator("interest_type")
    @classmethod
    def _interest_type_or_overig(cls, v):
        """WS-C.10: contact_submissions.interest_type is CHECK'd to
        LEAD_INTEREST_TYPES (migrations/026_leads_interest_type.py) -- the
        migration maps existing NULL/unknown rows to 'overig' at the DB
        level (plus the three legacy values below), and this validator
        does the same at the API boundary so a caller sending an empty
        string, a legacy value, or an unrecognised value never reaches
        the INSERT with something the CHECK would reject."""
        if v in _LEGACY_INTEREST_TYPE_MAP:
            return _LEGACY_INTEREST_TYPE_MAP[v]
        if v is None or v.strip() == "" or v not in LEAD_INTEREST_TYPES:
            return "overig"
        return v


# ── Generic Pagination ─────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    # Fields match the actual `outreach_messages` table (migrations/000_baseline.py)
    # -- there is no separate `messages` table, and no sender_id/recipient_id
    # columns exist. is_read is derived (opened_at IS NOT NULL), not stored;
    # routers must set it explicitly per row, it is never a raw DB column.
    id: int
    candidate_id: Optional[int] = None
    campaign_id: Optional[int] = None
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    channel: Optional[str] = None
    status: Optional[str] = None
    is_read: bool = False
    sent_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    unread_count: int = 0


# ── Mobile: Push Tokens ─────────────────────────────────────────────────

class PushTokenCreate(BaseModel):
    token: str = Field(..., min_length=1, max_length=400)
    platform: Optional[str] = Field(None, max_length=20)


class PushTokenDelete(BaseModel):
    token: str = Field(..., min_length=1, max_length=400)


# ── Public: Skill Quiz ───────────────────────────────────────────────────

class QuizAnswerItem(BaseModel):
    question_id: int
    answer_index: int = Field(..., ge=0, le=3)


class QuizSubmitRequest(BaseModel):
    email: Optional[EmailStr] = None
    answers: List[QuizAnswerItem] = Field(..., min_length=1)


# ── WS-C.4: Client Contacts ──────────────────────────────────────────────

class ClientContactCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    role: Optional[str] = Field(None, pattern=r"^(hiring_manager|finance|tekenbevoegd|overig)$")
    is_primary: bool = False
    # Same GDPR lawful-basis set as client_prospects (WS-E.7,
    # migrations/018_gdpr_provenance_optout.py) -- a client_contacts row is
    # a business contact, not a consumer, so it isn't mandatory the way
    # candidates.lawful_basis is, but it's validated when supplied.
    lawful_basis: Optional[str] = Field(None, pattern=r"^(zakelijk_functioneel_adres|opt_in|bestaande_relatie)$")


class ClientContactUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    role: Optional[str] = Field(None, pattern=r"^(hiring_manager|finance|tekenbevoegd|overig)$")
    is_primary: Optional[bool] = None
    lawful_basis: Optional[str] = Field(None, pattern=r"^(zakelijk_functioneel_adres|opt_in|bestaande_relatie)$")


class ClientContactResponse(BaseModel):
    id: int
    client_id: int
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_primary: bool = False
    lawful_basis: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── WS-B.5: Admin clients list/detail (migrations/031) ───────────────────

class ClientPrimaryContact(BaseModel):
    full_name: str
    email: Optional[str] = None
    role: Optional[str] = None


class ClientListItem(BaseModel):
    id: int
    company_name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    erkend_referent: str = "onbekend"
    open_job_count: int = 0
    primary_contact: Optional[ClientPrimaryContact] = None
    created_at: datetime


class ClientDetail(BaseModel):
    id: int
    company_name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    erkend_referent: str = "onbekend"
    notes: Optional[str] = None
    open_job_count: int = 0
    contacts: List[ClientContactResponse] = []
    created_at: datetime
    updated_at: Optional[datetime] = None


class ClientAdminUpdate(BaseModel):
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=255)
    erkend_referent: Optional[str] = Field(None, pattern=r"^(ja|nee|onbekend)$")
    notes: Optional[str] = None


# ── WS-C.5: Pipeline Stage History ───────────────────────────────────────

class PipelineStageUpdate(BaseModel):
    stage: str = Field(..., min_length=1, max_length=50)


class PipelineStageHistoryItem(BaseModel):
    id: int
    pipeline_entry_id: int
    from_stage: Optional[str] = None
    to_stage: str
    changed_by: Optional[int] = None
    changed_at: datetime

    model_config = {"from_attributes": True}


# ── WS-C.7: Placements (minimal) + immigratiestatus. PROVISIONAL. ────────
# Pricing/margin factors here are owner decisions not yet finalised, and
# nothing built on top of these models is published to the public site or
# the client portal (routers/placements.py is admin-only). See
# migrations/029_placements.py and core/margin.py for the full rationale.
#
# security-auditor follow-up (M2 WS-C.7 FIX FIRST, MEDIUM #2/#3): every
# money/rate field is Decimal, not float -- floats can silently carry NaN/
# inf and lose precision on read-modify-write; Decimal with
# allow_inf_nan=False rejects both at the API boundary (422), matching
# each column's own NUMERIC(precision,scale) bound from
# migrations/029_placements.py so a value pydantic accepts can never
# overflow the column at insert time.

_PLACEMENT_TYPES = r"^(werving_selectie|detachering)$"
_BILLING_BASES = r"^(vast_maandbedrag|per_uur)$"
_FEE_TYPES = r"^(percentage|vast)$"
_PLACEMENT_STATUSES = r"^(concept|actief|beeindigd|geannuleerd)$"


def _money_field() -> Any:
    """NUMERIC(10,2) columns (hourly_bill_rate, monthly_purchase_price,
    fee_amount): non-negative, 2 decimal places, capped at the column's
    max (8 integer digits + 2 decimal = 99999999.99), no NaN/Infinity."""
    return Field(
        None, ge=0, le=Decimal("99999999.99"), decimal_places=2, allow_inf_nan=False,
    )


def _eor_cost_factor_field() -> Any:
    """NUMERIC(6,4): non-negative, 4 decimal places, capped at 99.9999."""
    return Field(
        None, ge=0, le=Decimal("99.9999"), decimal_places=4, allow_inf_nan=False,
    )


def _fee_percentage_field() -> Any:
    """NUMERIC(5,2): a percentage, so also capped at 100 (not just the
    column's raw 999.99 headroom)."""
    return Field(
        None, ge=0, le=Decimal("100"), decimal_places=2, allow_inf_nan=False,
    )


def _expected_billable_hours_field() -> Any:
    """NUMERIC(6,2): non-negative, 2 decimal places, capped at 9999.99."""
    return Field(
        None, ge=0, le=Decimal("9999.99"), decimal_places=2, allow_inf_nan=False,
    )


class OneOffCost(BaseModel):
    """One ad-hoc one-off cost line item inside placements.one_off_costs
    (jsonb). extra='forbid' so an arbitrary/unexpected key never silently
    rides along into the stored jsonb array."""
    model_config = {"extra": "forbid"}

    label: str = Field(..., min_length=1, max_length=120)
    amount: Decimal = Field(..., ge=0, decimal_places=2, allow_inf_nan=False)


class PlacementCreate(BaseModel):
    candidate_id: int
    job_id: int
    client_id: int
    placement_type: str = Field(..., pattern=_PLACEMENT_TYPES)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hourly_bill_rate: Optional[Decimal] = _money_field()
    monthly_purchase_price: Optional[Decimal] = _money_field()
    eor_partner: Optional[str] = None
    eor_cost_factor: Optional[Decimal] = _eor_cost_factor_field()
    billing_basis: Optional[str] = Field(None, pattern=_BILLING_BASES)
    expected_billable_hours: Optional[Decimal] = _expected_billable_hours_field()
    fee_type: Optional[str] = Field(None, pattern=_FEE_TYPES)
    fee_percentage: Optional[Decimal] = _fee_percentage_field()
    fee_amount: Optional[Decimal] = _money_field()
    one_off_costs: List[OneOffCost] = []
    status: str = Field("concept", pattern=_PLACEMENT_STATUSES)
    notes: Optional[str] = None


class PlacementUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hourly_bill_rate: Optional[Decimal] = _money_field()
    monthly_purchase_price: Optional[Decimal] = _money_field()
    eor_partner: Optional[str] = None
    eor_cost_factor: Optional[Decimal] = _eor_cost_factor_field()
    billing_basis: Optional[str] = Field(None, pattern=_BILLING_BASES)
    expected_billable_hours: Optional[Decimal] = _expected_billable_hours_field()
    fee_type: Optional[str] = Field(None, pattern=_FEE_TYPES)
    fee_percentage: Optional[Decimal] = _fee_percentage_field()
    fee_amount: Optional[Decimal] = _money_field()
    one_off_costs: Optional[List[OneOffCost]] = None
    notes: Optional[str] = None


class PlacementStatusUpdate(BaseModel):
    status: str = Field(..., pattern=_PLACEMENT_STATUSES)


class PlacementResponse(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    client_id: int
    placement_type: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hourly_bill_rate: Optional[Decimal] = None
    monthly_purchase_price: Optional[Decimal] = None
    eor_partner: Optional[str] = None
    eor_cost_factor: Optional[Decimal] = None
    billing_basis: Optional[str] = None
    expected_billable_hours: Optional[Decimal] = None
    fee_type: Optional[str] = None
    fee_percentage: Optional[Decimal] = None
    fee_amount: Optional[Decimal] = None
    one_off_costs: List[OneOffCost] = []
    status: str
    notes: Optional[str] = None
# ── WS-C.6: Activities (unified activity/task log) ───────────────────────

ACTIVITY_SUBJECT_TYPES = ("candidate", "client", "job", "prospect", "placement", "lead")
ACTIVITY_TYPES = ("note", "call", "email", "meeting", "task", "status_change")


class ActivityCreate(BaseModel):
    subject_type: str = Field(..., pattern=r"^(candidate|client|job|prospect|placement|lead)$")
    subject_id: int
    type: str = Field(..., pattern=r"^(note|call|email|meeting|task|status_change)$")
    body: Optional[str] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # Code-review follow-up: an admin-created row defaults to internal
    # (recruiter-only) and may opt in to client-visible with
    # internal=false. Client-portal rows never go through this model --
    # see ClientActivityCreate, which has no internal field at all and
    # is always forced to internal=false server-side.
    internal: bool = True


class ActivityUpdate(BaseModel):
    """Only the fields the admin/client can revise after the fact --
    subject_type/subject_id/type are the row's identity and are not
    editable (create a new activity instead of re-pointing one)."""
    body: Optional[str] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    internal: Optional[bool] = None


class ActivityResponse(BaseModel):
    id: int
    subject_type: str
    subject_id: int
    type: str
    body: Optional[str] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    internal: bool = True
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# Client-portal create: subject_type is restricted server-side (job | candidate,
# scoped to the caller's own client via user_clients -- routers/activities.py),
# never trusted from the body the way the admin create is. Deliberately has
# no `internal` field -- a client-portal-authored activity is always
# internal=false, forced by the router, never a client-supplied value.
class ClientActivityCreate(BaseModel):
    subject_type: str = Field(..., pattern=r"^(job|candidate)$")
    subject_id: int
    type: str = Field(..., pattern=r"^(note|call|email|meeting|task|status_change)$")
    body: Optional[str] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ── WS-C.10: Leads (unified contact_submissions + quiz_submissions) ──────

class LeadReadUpdate(BaseModel):
    is_read: bool