"""Talent OS — Pydantic schemas for request/response models."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime


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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


# ── Candidate ───────────────────────────────────────────────────────────

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
    sourced_by_agent: Optional[str] = None
    strength_score: Optional[float] = Field(None, ge=1.0, le=10.0)
    switch_readiness: Optional[str] = Field(None, pattern=r"^(LOW|MEDIUM|HIGH|ACTIVE)$")
    tags: List[str] = []


class CandidateResponse(CandidateCreate):
    id: int
    status: str = "sourced"
    is_passive: bool = True
    screening_score: Optional[int] = None
    screening_notes: Optional[str] = None
    quality_score: Optional[float] = None
    cv_file_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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


# ── Match ───────────────────────────────────────────────────────────────

class MatchResponse(BaseModel):
    id: int
    job_id: int
    candidate_id: int
    match_score: Optional[float] = None
    match_breakdown: Optional[dict] = None
    status: str = "pending"
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Webhook ─────────────────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    action: str = Field(..., pattern=r"^(candidate_found|candidate_updated|signal_detected|placement_update)$")
    agent: Optional[str] = None
    data: dict = {}


# ── Health ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
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
    role: str = "client"


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
    id: int
    sender_id: Optional[int] = None
    recipient_id: Optional[int] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_read: bool = False
    created_at: datetime


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    unread_count: int = 0