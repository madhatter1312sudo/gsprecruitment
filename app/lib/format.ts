import type { Lang } from './i18n';

export function formatSalaryRange(
  min: number | null,
  max: number | null,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  if (!min && !max) return t('jobs.salaryUnknown');
  if (min && max) return `€${formatK(min)} – €${formatK(max)}`;
  if (min) return `€${formatK(min)}+`;
  return `tot €${formatK(max as number)}`;
}

function formatK(n: number): string {
  return n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);
}

export function locationTypeIcon(locationType: string | null): string {
  switch (locationType) {
    case 'remote':
      return '🌐';
    case 'hybrid':
      return '🏢🌐';
    case 'onsite':
      return '🏢';
    default:
      return '📍';
  }
}

const SENIORITY_LABELS: Record<string, { nl: string; en: string }> = {
  junior: { nl: 'Junior', en: 'Junior' },
  mid: { nl: 'Medior', en: 'Medior' },
  medior: { nl: 'Medior', en: 'Medior' },
  senior: { nl: 'Senior', en: 'Senior' },
  lead: { nl: 'Lead', en: 'Lead' },
  executive: { nl: 'Executive', en: 'Executive' },
};

export function seniorityLabel(seniority: string, lang: Lang): string {
  const entry = SENIORITY_LABELS[seniority.toLowerCase()];
  if (entry) return entry[lang];
  return seniority.charAt(0).toUpperCase() + seniority.slice(1);
}

export function formatDate(iso: string, lang: Lang): string {
  try {
    return new Date(iso).toLocaleDateString(lang === 'nl' ? 'nl-NL' : 'en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}
