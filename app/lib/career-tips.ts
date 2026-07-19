/** Static, honest career-coaching copy — written by the GSP team, no individual byline. */
export const CAREER_TIPS: { nl: string; en: string }[] = [
  {
    nl: 'Onderhandel op basis van data, niet op gevoel. Gebruik benchmarks zoals hierboven als startpunt voor een gesprek, niet als eindbod.',
    en: 'Negotiate from data, not gut feeling. Use benchmarks like the ones above as a conversation starter, not a final offer.',
  },
  {
    nl: 'Een stap opzij (andere stack, ander domein) kan op de lange termijn meer opleveren dan een kleine stap omhoog in je huidige rol.',
    en: 'A sideways move (different stack, different domain) can pay off more long-term than a small step up in your current role.',
  },
  {
    nl: 'Vraag in elk gesprek naar het groeipad: wat verwacht het bedrijf van je over een jaar, en hoe wordt dat beoordeeld?',
    en: "Ask about the growth path in every interview: what does the company expect from you in a year, and how is that assessed?"
  },
  {
    nl: 'Wissel niet alleen voor salaris. Team, autonomie en de kwaliteit van je manager bepalen op de lange termijn meer over hoeveel je leert.',
    en: "Don't switch for salary alone. Team, autonomy and manager quality determine far more of how much you'll learn long-term.",
  },
];

export const ROLE_OPTIONS = [
  'Software Engineer',
  'Embedded Software Engineer',
  'DevOps Engineer',
  'Data Engineer',
  'Machine Learning Engineer',
  'Test Engineer',
  'Product Manager',
  'Engineering Manager',
];

/**
 * Label -> query value. The backend's salary_benchmarks.seniority column
 * stores lowercase 'junior' | 'mid' | 'senior' | 'lead' (verified against
 * migrations/009_salary_benchmarks_seed.py) and the API does an exact
 * match, not fuzzy — so "Medior" must be sent as 'mid', not 'medior'.
 */
export const SENIORITY_OPTIONS: { label_nl: string; label_en: string; value: string }[] = [
  { label_nl: 'Junior', label_en: 'Junior', value: 'junior' },
  { label_nl: 'Medior', label_en: 'Medior', value: 'mid' },
  { label_nl: 'Senior', label_en: 'Senior', value: 'senior' },
  { label_nl: 'Lead', label_en: 'Lead', value: 'lead' },
];

export const LOCATION_OPTIONS = ['Eindhoven', 'Remote'];
