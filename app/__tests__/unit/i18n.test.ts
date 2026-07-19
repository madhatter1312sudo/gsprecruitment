import { translate, dict, useLanguageStore } from '../../lib/i18n';

describe('translate', () => {
  it('looks up the Dutch and English strings for a known key', () => {
    expect(translate('common.save', 'nl')).toBe('Opslaan');
    expect(translate('common.save', 'en')).toBe('Save');
  });

  it('interpolates {placeholder} params', () => {
    expect(translate('quiz.questionOf', 'nl', { current: 3, total: 12 })).toBe('Vraag 3 van 12');
    expect(translate('quiz.questionOf', 'en', { current: 3, total: 12 })).toBe('Question 3 of 12');
  });

  it('falls back to returning the raw key when the entry is missing', () => {
    expect(translate('quiz.domain.totally_unknown_domain', 'nl')).toBe('quiz.domain.totally_unknown_domain');
  });

  it('every dict entry has both nl and en strings', () => {
    const missing: string[] = [];
    for (const [key, entry] of Object.entries(dict)) {
      if (!entry.nl || !entry.en) missing.push(key);
    }
    expect(missing).toEqual([]);
  });
});

describe('useLanguageStore', () => {
  it('defaults to nl and updates on setLang', () => {
    expect(useLanguageStore.getState().lang).toBe('nl');
    useLanguageStore.getState().setLang('en');
    expect(useLanguageStore.getState().lang).toBe('en');
    useLanguageStore.getState().setLang('nl');
  });
});
