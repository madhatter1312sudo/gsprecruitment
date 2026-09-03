"""Talent OS — Pydantic schemas for request/response models."""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Any, Literal
from datetime import datetime, date


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
    # picked up a DEFAULT NOW() (see migrations/023_candidates_updated_at_default.py)
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


class LeadSubmit(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    company: Optional[str] = None
    phone: Optional[str] = None
    message: str = Field(..., min_length=1)
    interest_type: Optional[str] = None


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