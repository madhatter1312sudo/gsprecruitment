/**
 * React Query hooks wrapping lib/api.ts. Centralised here so screens stay
 * thin and query keys stay consistent (important for cache sharing, e.g.
 * the job detail screen reads out of the same `['jobs']` cache entry the
 * feed populated instead of hitting a nonexistent detail endpoint).
 */
import { useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from './api';
import { useAuthStore } from './auth';
import type { Lang } from './i18n';

export const queryKeys = {
  jobs: ['jobs'] as const,
  salary: (params: { role_title?: string; seniority?: string; location?: string }) => ['salary', params] as const,
  profile: ['candidate-profile'] as const,
  matches: ['candidate-matches'] as const,
  applications: ['candidate-applications'] as const,
  quiz: (lang: Lang) => ['quiz', lang] as const,
};

// ── Jobs ────────────────────────────────────────────────────────────────

export function useJobsQuery() {
  return useQuery({
    queryKey: queryKeys.jobs,
    queryFn: api.getPublicJobs,
    staleTime: 60_000,
  });
}

/**
 * There is no `GET /public/jobs/{id}` on the backend (only the list route
 * exists — see routers/jobs.py). We resolve job detail from the same
 * cached list the feed screen uses, refetching the list if the entry
 * isn't there yet (e.g. a cold deep link).
 */
export function useJob(id: number | undefined) {
  const query = useJobsQuery();
  const job = useMemo(() => query.data?.find((j) => j.id === id), [query.data, id]);
  return {
    data: job,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    isRefetching: query.isRefetching,
  };
}

// ── Salary ──────────────────────────────────────────────────────────────

export function useSalaryQuery(params: { role_title?: string; seniority?: string; location?: string }, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.salary(params),
    queryFn: () => api.getSalaryData(params),
    enabled,
  });
}

// ── Candidate profile ────────────────────────────────────────────────────

export function useProfileQuery() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useQuery({
    queryKey: queryKeys.profile,
    queryFn: api.getCandidateProfile,
    enabled: isAuthenticated,
  });
}

export function useUpdateProfileMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (updates: api.CandidateProfileUpdate) => api.updateCandidateProfile(updates),
    onSuccess: (data) => qc.setQueryData(queryKeys.profile, data),
  });
}

export function useUploadCvMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: { uri: string; name: string; mimeType?: string }) => api.uploadCv(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.profile }),
  });
}

// ── Matches / applications ────────────────────────────────────────────────

export function useMatchesQuery() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useQuery({
    queryKey: queryKeys.matches,
    queryFn: () => api.getCandidateMatches(),
    enabled: isAuthenticated,
  });
}

export function useApplicationsQuery() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useQuery({
    queryKey: queryKeys.applications,
    queryFn: () => api.getCandidateApplications(),
    enabled: isAuthenticated,
  });
}

export function useApplyMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => api.applyToJob(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.applications });
      qc.invalidateQueries({ queryKey: queryKeys.matches });
    },
  });
}

// ── Quiz ────────────────────────────────────────────────────────────────

export function useQuizQuery(lang: Lang, enabled = true) {
  return useQuery({
    queryKey: queryKeys.quiz(lang),
    queryFn: () => api.getQuiz(lang),
    enabled,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

export function useSubmitQuizMutation(lang: Lang) {
  return useMutation({
    mutationFn: (payload: { answers: api.QuizSubmitAnswer[]; email?: string }) => api.submitQuiz(payload, lang),
  });
}

// ── GDPR ──────────────────────────────────────────────────────────────

export function useGdprExportMutation() {
  return useMutation({ mutationFn: api.gdprExport });
}

export function useDeleteAccountMutation() {
  return useMutation({ mutationFn: api.gdprDeleteAccount });
}
