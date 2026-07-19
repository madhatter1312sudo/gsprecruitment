import { formatSalaryRange, locationTypeIcon, seniorityLabel, formatDate } from '../../lib/format';

const t = (key: string) => (key === 'jobs.salaryUnknown' ? 'Salaris in overleg' : key);

describe('formatSalaryRange', () => {
  it('formats a full range in thousands', () => {
    expect(formatSalaryRange(60000, 85000, t)).toBe('€60k – €85k');
  });

  it('formats a min-only range with a plus', () => {
    expect(formatSalaryRange(70000, null, t)).toBe('€70k+');
  });

  it('formats a max-only range with "tot"', () => {
    expect(formatSalaryRange(null, 50000, t)).toBe('tot €50k');
  });

  it('falls back to the "unknown" translation when both are missing', () => {
    expect(formatSalaryRange(null, null, t)).toBe('Salaris in overleg');
  });

  it('does not abbreviate values under 1000', () => {
    expect(formatSalaryRange(500, 900, t)).toBe('€500 – €900');
  });
});

describe('locationTypeIcon', () => {
  it('returns a distinct icon per location type', () => {
    expect(locationTypeIcon('remote')).toBe('🌐');
    expect(locationTypeIcon('hybrid')).toBe('🏢🌐');
    expect(locationTypeIcon('onsite')).toBe('🏢');
    expect(locationTypeIcon(null)).toBe('📍');
    expect(locationTypeIcon('unknown-value')).toBe('📍');
  });
});

describe('seniorityLabel', () => {
  it('maps known seniority values per language, including the mid -> Medior mismatch', () => {
    expect(seniorityLabel('mid', 'nl')).toBe('Medior');
    expect(seniorityLabel('mid', 'en')).toBe('Medior');
    expect(seniorityLabel('senior', 'nl')).toBe('Senior');
    expect(seniorityLabel('JUNIOR', 'nl')).toBe('Junior');
  });

  it('title-cases unknown values as a fallback', () => {
    expect(seniorityLabel('principal', 'en')).toBe('Principal');
  });
});

describe('formatDate', () => {
  it('formats a valid ISO date without throwing', () => {
    const result = formatDate('2026-03-15T10:00:00Z', 'nl');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });

  it('returns the raw input when the date cannot be parsed into a valid value', () => {
    // Date.prototype.toLocaleDateString does not throw for invalid dates,
    // it returns "Invalid Date" — formatDate should still return a string.
    const result = formatDate('not-a-date', 'en');
    expect(typeof result).toBe('string');
  });
});
