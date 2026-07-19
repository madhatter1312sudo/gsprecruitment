/**
 * Fetch wrapper + typed endpoint functions for the GSP Recruitment API.
 *
 * Base URL: https://api.gsprecruitment.nl/api (see app.json `extra.apiBaseUrl`).
 *
 * IMPORTANT — endpoint corrections made against the live backend
 * (talent-os/backend/routers/*.py), see README-APP.md "API adjustments"
 * for the full list. In short:
 *   - Candidate matches/applications live under `/v1/candidate/...`,
 *     not `/v1/mobile/me/...`.
 *   - There is no job-detail endpoint (`GET /public/jobs/{id}`) — the
 *     public router only exposes the list. Job detail is resolved
 *     client-side from the cached jobs list (see lib/queries.ts `useJob`).
 *   - There is no `/v1/public/quiz` backend at all yet — the quiz is
 *     entirely client-side (lib/quiz-data.ts), same approach the public
 *     website itself uses for its own match quiz. Quiz email capture
 *     reuses the real `POST /v1/public/lead` endpoint instead of a
 *     nonexistent `/v1/public/quiz/submit`.
 *   - There is no `/v1/mobile/push-token` endpoint on the backend today,
 *     and expo-notifications isn't part of this app's dependency list,
 *     so push registration is not wired up. `registerPushToken()` below
 *     is left in place, pointed at the path from the spec, for when both
 *     exist — it is never called.
 */
import Constants from 'expo-constants';
import { getAuthState, useAuthStore, type AuthUser } from './auth';

export const API_BASE_URL: string =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  'https://api.gsprecruitment.nl/api';

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  auth?: boolean; // attach bearer token
  query?: Record<string, string | number | undefined | null>;
  /** internal: set while retrying after a refresh, to avoid infinite loops */
  _isRetry?: boolean;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function extractErrorMessage(res: Response): Promise<{ message: string; detail: unknown }> {
  try {
    const data = await res.json();
    const detail = data?.detail;
    if (typeof detail === 'string') return { message: detail, detail };
    if (Array.isArray(detail)) {
      // FastAPI validation error array
      const message = detail.map((d: any) => d?.msg).filter(Boolean).join(', ') || res.statusText;
      return { message, detail };
    }
    return { message: res.statusText || 'Request failed', detail };
  } catch {
    return { message: res.statusText || 'Request failed', detail: undefined };
  }
}

// Single-flight refresh: concurrent 401s share one refresh attempt.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const current = getAuthState().accessToken;
      if (!current) return null;
      try {
        const res = await fetch(buildUrl('/auth/refresh'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: current }),
        });
        if (!res.ok) return null;
        const data = await res.json();
        const user: AuthUser = data.user;
        await useAuthStore.getState().setSession(data.access_token, user);
        return data.access_token as string;
      } catch {
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = false, query, _isRetry = false } = options;

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth) {
    const token = getAuthState().accessToken;
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && auth && !_isRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return apiRequest<T>(path, { ...options, _isRetry: true });
    }
    await useAuthStore.getState().logout();
    const { message, detail } = await extractErrorMessage(res);
    throw new ApiError(401, message, detail);
  }

  if (!res.ok) {
    const { message, detail } = await extractErrorMessage(res);
    throw new ApiError(res.status, message, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Multipart upload helper (used for CV upload — fetch's FormData + RN file URI). */
async function apiUpload<T>(path: string, form: FormData, opts: { auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (opts.auth) {
    const token = getAuthState().accessToken;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  // NOTE: do NOT set Content-Type manually — fetch needs to set the
  // multipart boundary itself.
  const res = await fetch(buildUrl(path), { method: 'POST', headers, body: form as any });
  if (res.status === 401 && opts.auth) {
    const newToken = await refreshAccessToken();
    if (newToken) return apiUpload<T>(path, form, opts);
    await useAuthStore.getState().logout();
  }
  if (!res.ok) {
    const { message, detail } = await extractErrorMessage(res);
    throw new ApiError(res.status, message, detail);
  }
  return (await res.json()) as T;
}

// ── Types ─────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface JobOrder {
  id: number;
  title: string;
  department: string | null;
  seniority: string | null; // 'junior' | 'mid' | 'senior' | 'lead' | 'executive'
  location_type: string | null; // 'remote' | 'hybrid' | 'onsite'
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  description: string | null;
  requirements: string | null;
  nice_to_have: string | null;
  status: string;
  created_at: string;
}

export interface SalaryBenchmark {
  role_title: string;
  seniority: string | null;
  location: string | null;
  currency: string;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  sample_size: number | null;
}

export interface CandidateProfile {
  id: number;
  user_id: number;
  email: string;
  full_name: string;
  phone: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  current_company: string | null;
  current_title: string | null;
  location: string | null;
  willing_to_relocate: boolean;
  salary_expectation_min: number | null;
  salary_expectation_max: number | null;
  notice_period_days: number | null;
  years_experience: number | null;
  skills: string[];
  languages: string[];
  education: string | null;
  cv_text: string | null;
  cv_file_path: string | null;
  created_at: string;
  updated_at: string | null;
}

export type CandidateProfileUpdate = Partial<
  Pick<
    CandidateProfile,
    | 'phone'
    | 'linkedin_url'
    | 'github_url'
    | 'portfolio_url'
    | 'current_company'
    | 'current_title'
    | 'location'
    | 'willing_to_relocate'
    | 'salary_expectation_min'
    | 'salary_expectation_max'
    | 'notice_period_days'
    | 'years_experience'
    | 'skills'
    | 'languages'
    | 'education'
  >
>;

export interface MatchItem {
  id: number;
  job_id: number;
  candidate_id: number;
  match_score: number | null;
  match_breakdown: Record<string, unknown> | null;
  status: string; // pending | applied | interviewing | offered | placed | rejected
  created_at: string;
  job_title: string;
  company_name: string;
}

export interface PaginatedList<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface GdprExport {
  user: Record<string, unknown> | null;
  candidate_profile: Record<string, unknown> | null;
  candidate_record: Record<string, unknown> | null;
  applications: Record<string, unknown>[];
  saved_jobs: Record<string, unknown>[];
}

// ── Auth ──────────────────────────────────────────────────────────────

export function login(email: string, password: string) {
  return apiRequest<TokenResponse>('/auth/login', { method: 'POST', body: { email, password } });
}

export function register(email: string, password: string, full_name: string) {
  return apiRequest<TokenResponse>('/auth/register', {
    method: 'POST',
    body: { email, password, full_name, role: 'candidate' },
  });
}

export function forgotPassword(email: string) {
  return apiRequest<{ message?: string }>('/auth/forgot-password', { method: 'POST', body: { email } });
}

// ── Public ────────────────────────────────────────────────────────────

export function getPublicJobs() {
  return apiRequest<JobOrder[]>('/public/jobs');
}

export function getSalaryData(params: { role_title?: string; seniority?: string; location?: string }) {
  return apiRequest<SalaryBenchmark[]>('/v1/public/salary-data', { query: params });
}

export function submitLead(input: { name: string; email: string; message: string; interest_type?: string }) {
  return apiRequest<{ message: string; id: number }>('/v1/public/lead', { method: 'POST', body: input });
}

// ── Candidate (authed) ──────────────────────────────────────────────────

export function getCandidateProfile() {
  return apiRequest<CandidateProfile>('/v1/candidate/profile', { auth: true });
}

export function updateCandidateProfile(updates: CandidateProfileUpdate) {
  return apiRequest<CandidateProfile>('/v1/candidate/profile', { method: 'PUT', auth: true, body: updates });
}

export async function uploadCv(file: { uri: string; name: string; mimeType?: string }) {
  const form = new FormData();
  form.append('file', {
    uri: file.uri,
    name: file.name,
    type: file.mimeType ?? 'application/octet-stream',
  } as any);
  return apiUpload<{ message: string; file_path: string; size: number }>('/v1/candidate/cv', form, { auth: true });
}

export function getCandidateMatches(limit = 20, offset = 0) {
  return apiRequest<PaginatedList<MatchItem>>('/v1/candidate/matches', { auth: true, query: { limit, offset } });
}

export function getCandidateApplications(limit = 20, offset = 0) {
  return apiRequest<PaginatedList<MatchItem>>('/v1/candidate/applications', { auth: true, query: { limit, offset } });
}

export function applyToJob(job_id: number) {
  return apiRequest<MatchItem>('/v1/candidate/applications', { method: 'POST', auth: true, body: { job_id } });
}

// ── GDPR (authed) ─────────────────────────────────────────────────────

export function gdprExport() {
  return apiRequest<GdprExport>('/v1/gdpr/export', { auth: true });
}

export function gdprDeleteAccount() {
  return apiRequest<{ message: string }>('/v1/gdpr/account', { method: 'DELETE', auth: true });
}

// ── Push (not wired — see file header) ─────────────────────────────────

export function registerPushToken(token: string, platform: 'ios' | 'android') {
  return apiRequest<{ message?: string }>('/v1/mobile/push-token', { method: 'POST', auth: true, body: { token, platform } });
}
