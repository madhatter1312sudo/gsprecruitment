import { QUIZ_QUESTIONS, scoreQuiz, growthTipFor, SERVER_GROWTH_TIPS_DEFAULT, type QuizAnswer } from '../../lib/quiz-data';

describe('scoreQuiz (offline fallback grading)', () => {
  it('awards 0 when no questions are answered', () => {
    const result = scoreQuiz([]);
    expect(result.score).toBe(0);
    expect(result.pct).toBe(0);
    expect(result.tier).toBe('junior');
    expect(result.feedback).toHaveLength(QUIZ_QUESTIONS.length);
  });

  it('awards full marks when every question picks the max-points option', () => {
    const answers: QuizAnswer[] = QUIZ_QUESTIONS.map((q) => {
      const bestIndex = q.options.reduce((best, o, i) => (o.points > q.options[best].points ? i : best), 0);
      return { question_id: q.id, option_index: bestIndex };
    });
    const result = scoreQuiz(answers);
    expect(result.score).toBe(result.maxScore);
    expect(result.pct).toBe(100);
    expect(result.tier).toBe('senior');
  });

  it('computes per-domain scores that sum back to the overall score', () => {
    const answers: QuizAnswer[] = QUIZ_QUESTIONS.map((q) => ({ question_id: q.id, option_index: 0 }));
    const result = scoreQuiz(answers);
    const domainTotal = result.domainScores.reduce((sum, d) => sum + d.score, 0);
    expect(domainTotal).toBe(result.score);
  });

  it('identifies the weakest domain as the one with the lowest percentage', () => {
    // Answer everything with the worst option except give 'security' full marks.
    const answers: QuizAnswer[] = QUIZ_QUESTIONS.map((q) => {
      if (q.domain === 'security') {
        const bestIndex = q.options.reduce((best, o, i) => (o.points > q.options[best].points ? i : best), 0);
        return { question_id: q.id, option_index: bestIndex };
      }
      const worstIndex = q.options.reduce((worst, o, i) => (o.points < q.options[worst].points ? i : worst), 0);
      return { question_id: q.id, option_index: worstIndex };
    });
    const result = scoreQuiz(answers);
    const security = result.domainScores.find((d) => d.domain === 'security')!;
    expect(security.pct).toBe(100);
    expect(result.weakestDomain).not.toBe('security');
  });
});

describe('growthTipFor (server-domain growth tips)', () => {
  it('returns a tip for each known server domain', () => {
    expect(growthTipFor('general_swe', 'nl')).toBeTruthy();
    expect(growthTipFor('security', 'en')).toBeTruthy();
    expect(growthTipFor('cloud_devops', 'nl')).toBeTruthy();
    expect(growthTipFor('embedded_cpp', 'en')).toBeTruthy();
  });

  it('falls back to a generic tip for an unrecognized domain so a new backend domain never crashes the UI', () => {
    expect(growthTipFor('some_future_domain', 'nl')).toBe(SERVER_GROWTH_TIPS_DEFAULT.nl);
    expect(growthTipFor('some_future_domain', 'en')).toBe(SERVER_GROWTH_TIPS_DEFAULT.en);
  });
});
