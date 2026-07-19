import React, { useMemo, useState } from 'react';
import { ScrollView, View, Text, Pressable, StyleSheet, Linking, ActivityIndicator } from 'react-native';
import { router } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { ScreenContainer, Card, Button, TextField, Chip } from '../../components/ui';
import { colors, spacing, radius, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { useAuthStore } from '../../lib/auth';
import {
  QUIZ_QUESTIONS,
  scoreQuiz,
  GROWTH_TIPS,
  BLOG_URL,
  growthTipFor,
  type QuizAnswer,
  type QuizResult,
} from '../../lib/quiz-data';
import { submitLead, type QuizSubmitAnswer, type QuizSubmitResponse } from '../../lib/api';
import { useQuizQuery, useSubmitQuizMutation } from '../../lib/queries';
import { isValidEmail } from '../../lib/validation';
import type { Lang } from '../../lib/i18n';

type Stage = 'intro' | 'question' | 'email' | 'submitting' | 'result';

/** Question shape shared by the live (server) and offline (local) question banks, so one renderer covers both. */
interface DisplayQuestion {
  id: number;
  question: string;
  options: string[];
}

function offlineQuestionsFor(lang: Lang): DisplayQuestion[] {
  return QUIZ_QUESTIONS.map((q) => ({
    id: q.id,
    question: lang === 'nl' ? q.question_nl : q.question_en,
    options: q.options.map((o) => (lang === 'nl' ? o.text_nl : o.text_en)),
  }));
}

/** translate() falls back to returning the raw key when a dict entry is missing — use that to detect unknown domains. */
function domainLabel(domain: string, t: (key: string) => string): string {
  const key = `quiz.domain.${domain}`;
  const label = t(key);
  return label === key ? domain : label;
}

function tierColorFor(tier: string) {
  const lower = tier.toLowerCase();
  if (lower.startsWith('senior')) return colors.gold;
  if (lower.startsWith('medior')) return colors.success;
  return colors.textMuted;
}

export default function QuizScreen() {
  const { t, lang } = useTranslation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);

  const [stage, setStage] = useState<Stage>('intro');
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<QuizSubmitAnswer[]>([]);
  const [offline, setOffline] = useState(false);
  const [onlineResult, setOnlineResult] = useState<QuizSubmitResponse | null>(null);
  const [offlineResult, setOfflineResult] = useState<QuizResult | null>(null);
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);

  const quizQuery = useQuizQuery(lang);
  const submitMutation = useSubmitQuizMutation(lang);

  const questions: DisplayQuestion[] = useMemo(() => {
    if (offline) return offlineQuestionsFor(lang);
    if (quizQuery.data) return quizQuery.data.items.map((it) => ({ id: it.id, question: it.question, options: it.options }));
    return [];
  }, [offline, quizQuery.data, lang]);

  const restart = () => {
    setStage('intro');
    setIndex(0);
    setAnswers([]);
    setOffline(false);
    setOnlineResult(null);
    setOfflineResult(null);
    setEmail('');
    setEmailError(null);
    submitMutation.reset();
  };

  const startOnline = () => {
    setOffline(false);
    setIndex(0);
    setAnswers([]);
    setStage('question');
  };

  const startOffline = () => {
    setOffline(true);
    setIndex(0);
    setAnswers([]);
    setStage('question');
  };

  const submitOnline = (finalAnswers: QuizSubmitAnswer[], emailToSend?: string) => {
    submitMutation.mutate(
      { answers: finalAnswers, email: emailToSend },
      {
        onSuccess: (data) => {
          setOnlineResult(data);
          setStage('result');
        },
      },
    );
  };

  const selectOption = (optionIndex: number) => {
    const question = questions[index];
    const next = [
      ...answers.filter((a) => a.question_id !== question.id),
      { question_id: question.id, answer_index: optionIndex },
    ];
    setAnswers(next);

    if (index + 1 < questions.length) {
      setIndex(index + 1);
      return;
    }

    // Last question answered.
    if (offline) {
      const localAnswers: QuizAnswer[] = next.map((a) => ({ question_id: a.question_id, option_index: a.answer_index }));
      setOfflineResult(scoreQuiz(localAnswers));
      setStage('result');
      return;
    }

    if (isAuthenticated && user?.email) {
      setStage('submitting');
      submitOnline(next, user.email);
    } else {
      setStage('email');
    }
  };

  const onEmailContinue = (skip: boolean) => {
    setEmailError(null);
    const trimmed = email.trim();
    if (!skip && trimmed && !isValidEmail(trimmed)) {
      setEmailError(t('auth.invalidEmail'));
      return;
    }
    submitOnline(answers, skip ? undefined : trimmed || undefined);
  };

  // ── Intro ───────────────────────────────────────────────────────────
  if (stage === 'intro') {
    return (
      <ScreenContainer style={{ padding: spacing.lg, justifyContent: 'center', flex: 1 }}>
        <Text style={[typography.h1, { marginBottom: spacing.sm }]}>{t('quiz.introTitle')}</Text>
        <Text style={[typography.bodyMuted, { marginBottom: spacing.xl }]}>{t('quiz.introBody')}</Text>

        {quizQuery.isLoading && (
          <View style={{ alignItems: 'center', marginBottom: spacing.lg }}>
            <ActivityIndicator color={colors.gold} />
            <Text style={[typography.bodyMuted, { marginTop: spacing.sm }]}>{t('quiz.loading')}</Text>
          </View>
        )}

        {quizQuery.isError && (
          <Card style={{ marginBottom: spacing.lg }}>
            <Text style={[typography.body, { marginBottom: spacing.md }]}>{t('quiz.loadError')}</Text>
            <Button title={t('common.retry')} onPress={() => quizQuery.refetch()} variant="secondary" style={{ marginBottom: spacing.sm }} />
            <Button title={t('quiz.useOffline')} onPress={startOffline} variant="ghost" />
          </Card>
        )}

        {quizQuery.isSuccess && <Button title={t('quiz.start')} onPress={startOnline} />}
      </ScreenContainer>
    );
  }

  // ── Question ────────────────────────────────────────────────────────
  if (stage === 'question') {
    const question = questions[index];
    const progress = questions.length > 0 ? (index + 1) / questions.length : 0;
    if (!question) return null;
    return (
      <ScreenContainer style={{ padding: spacing.lg }}>
        {offline && (
          <View style={{ marginBottom: spacing.sm }}>
            <Chip label={t('quiz.offlineBadge')} tone="muted" />
          </View>
        )}
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
        </View>
        <Text style={[typography.caption, { marginTop: spacing.sm, marginBottom: spacing.lg }]}>
          {t('quiz.questionOf', { current: index + 1, total: questions.length })}
        </Text>
        <ScrollView>
          <Text style={[typography.h2, { marginBottom: spacing.lg }]}>{question.question}</Text>
          {question.options.map((opt, i) => (
            <Pressable
              key={i}
              onPress={() => selectOption(i)}
              accessibilityRole="button"
              testID={`quiz-option-${i}`}
              style={({ pressed }) => [styles.option, pressed && styles.optionPressed]}
            >
              <Text style={typography.body}>{opt}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </ScreenContainer>
    );
  }

  // ── Optional email before submit (anonymous users only) ────────────
  if (stage === 'email') {
    return (
      <ScreenContainer style={{ padding: spacing.lg, justifyContent: 'center', flex: 1 }}>
        <Text style={[typography.h1, { marginBottom: spacing.sm }]}>{t('quiz.emailStageTitle')}</Text>
        <Text style={[typography.bodyMuted, { marginBottom: spacing.lg }]}>{t('quiz.emailStageBody')}</Text>
        <TextField
          value={email}
          onChangeText={setEmail}
          placeholder={t('quiz.emailPlaceholder')}
          autoCapitalize="none"
          keyboardType="email-address"
        />
        {emailError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{emailError}</Text>}
        {submitMutation.isError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{t('quiz.submitError')}</Text>}
        <Button
          title={t('quiz.submit')}
          onPress={() => onEmailContinue(false)}
          loading={submitMutation.isPending}
          style={{ marginBottom: spacing.sm }}
        />
        <Button title={t('quiz.emailStageSkip')} onPress={() => onEmailContinue(true)} variant="ghost" disabled={submitMutation.isPending} />
      </ScreenContainer>
    );
  }

  // ── Submitting (authenticated users skip the email screen) ─────────
  if (stage === 'submitting') {
    return (
      <ScreenContainer style={{ padding: spacing.lg, justifyContent: 'center', alignItems: 'center', flex: 1 }}>
        {submitMutation.isError ? (
          <>
            <Text style={[typography.body, { marginBottom: spacing.md, textAlign: 'center' }]}>{t('quiz.submitError')}</Text>
            <Button title={t('common.retry')} onPress={() => submitOnline(answers, user?.email)} />
          </>
        ) : (
          <>
            <ActivityIndicator color={colors.gold} size="large" />
            <Text style={[typography.bodyMuted, { marginTop: spacing.md }]}>{t('quiz.submitting')}</Text>
          </>
        )}
      </ScreenContainer>
    );
  }

  // ── Result ──────────────────────────────────────────────────────────
  if (offline) {
    return <OfflineResultView result={offlineResult!} isAuthenticated={isAuthenticated} onRestart={restart} />;
  }
  return <OnlineResultView result={onlineResult!} questions={questions} isAuthenticated={isAuthenticated} onRestart={restart} />;
}

// ── Online (server-graded) result screen ─────────────────────────────────

function OnlineResultView({
  result,
  questions,
  isAuthenticated,
  onRestart,
}: {
  result: QuizSubmitResponse;
  questions: DisplayQuestion[];
  isAuthenticated: boolean;
  onRestart: () => void;
}) {
  const { t, lang } = useTranslation();
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);

  const leadMutation = useMutation({
    mutationFn: () =>
      submitLead({
        name: 'Quiz result',
        email: email.trim(),
        message: `Quiz score: ${result.score}/${result.max_score} (${result.tier}) — via mobile app`,
        interest_type: 'candidate',
      }),
  });

  const onSendEmail = () => {
    setEmailError(null);
    if (!isValidEmail(email)) {
      setEmailError(t('auth.invalidEmail'));
      return;
    }
    leadMutation.mutate();
  };

  const domainEntries = Object.entries(result.domain_scores).map(([domain, s]) => ({
    domain,
    pct: s.total > 0 ? Math.round((s.correct / s.total) * 100) : 0,
    correct: s.correct,
    total: s.total,
  }));
  const weakest = domainEntries.reduce((min, d) => (d.pct < min.pct ? d : min), domainEntries[0]);
  const questionById = new Map(questions.map((q) => [q.id, q]));
  const tierColor = tierColorFor(result.tier);

  return (
    <ScreenContainer>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        <Text style={[typography.h1, { marginBottom: spacing.lg }]}>{t('quiz.resultTitle')}</Text>

        <Card style={{ alignItems: 'center', paddingVertical: spacing.xl }}>
          <Text style={[styles.tierBadge, { color: tierColor, borderColor: tierColor }]}>{result.tier}</Text>
          <Text style={[typography.h2, { marginTop: spacing.md }]}>
            {result.score} / {result.max_score}
          </Text>
          <Text style={typography.bodyMuted}>{t('quiz.scoreLabel')}</Text>
        </Card>

        {domainEntries.length > 0 && (
          <>
            <Text style={[typography.h3, { marginTop: spacing.xl, marginBottom: spacing.md }]}>{t('quiz.domainScores')}</Text>
            {domainEntries.map((d) => (
              <View key={d.domain} style={{ marginBottom: spacing.sm }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={typography.bodyMuted}>{domainLabel(d.domain, t)}</Text>
                  <Text style={typography.bodyMuted}>
                    {d.correct}/{d.total}
                  </Text>
                </View>
                <View style={styles.barTrack}>
                  <View style={[styles.barFill, { width: `${d.pct}%` }]} />
                </View>
              </View>
            ))}

            <Card style={{ marginTop: spacing.xl, backgroundColor: colors.goldLight, borderColor: colors.gold }}>
              <Text style={[typography.h3, { color: colors.gold }]}>{t('quiz.growthTitle')}</Text>
              <Text style={[typography.body, { marginTop: spacing.sm }]}>{growthTipFor(weakest.domain, lang)}</Text>
              <Pressable onPress={() => Linking.openURL(BLOG_URL)} style={{ marginTop: spacing.sm }}>
                <Text style={{ color: colors.gold, fontWeight: '600' }}>gsprecruitment.nl/blog →</Text>
              </Pressable>
            </Card>
          </>
        )}

        <Text style={[typography.h3, { marginTop: spacing.xl, marginBottom: spacing.md }]}>{t('quiz.feedbackTitle')}</Text>
        {result.feedback.map((f) => {
          const question = questionById.get(f.question_id);
          return (
            <Card key={f.question_id} style={{ marginBottom: spacing.sm }}>
              {question && <Text style={typography.body}>{question.question}</Text>}
              <Text style={[typography.caption, { marginTop: spacing.xs, color: f.correct ? colors.success : colors.danger }]}>
                {f.correct ? '✓' : '✗'}
              </Text>
              {question && (
                <Text style={[typography.bodyMuted, { marginTop: spacing.xs }]}>{question.options[f.correct_index]}</Text>
              )}
              <Text style={[typography.bodyMuted, { marginTop: spacing.xs }]}>{f.explanation}</Text>
            </Card>
          );
        })}

        {!isAuthenticated && (
          <Card style={{ marginTop: spacing.lg }}>
            <Text style={typography.h3}>{t('quiz.ctaProfile')}</Text>
            <Text style={[typography.bodyMuted, { marginVertical: spacing.sm }]}>{t('quiz.ctaProfileBody')}</Text>
            <Button title={t('quiz.ctaProfile')} onPress={() => router.push('/(auth)/register')} />
          </Card>
        )}

        <Card style={{ marginTop: spacing.lg }}>
          <Text style={typography.h3}>{t('quiz.emailPrompt')}</Text>
          {leadMutation.isSuccess ? (
            <Text style={{ color: colors.success, marginTop: spacing.sm }}>{t('quiz.emailSent')}</Text>
          ) : (
            <>
              <TextField
                value={email}
                onChangeText={setEmail}
                placeholder={t('quiz.emailPlaceholder')}
                autoCapitalize="none"
                keyboardType="email-address"
                style={{ marginTop: spacing.sm }}
              />
              {emailError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{emailError}</Text>}
              {leadMutation.isError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{t('quiz.emailError')}</Text>}
              <Button title={t('quiz.sendResult')} onPress={onSendEmail} loading={leadMutation.isPending} variant="secondary" />
            </>
          )}
        </Card>

        <Button title={t('quiz.restart')} onPress={onRestart} variant="ghost" style={{ marginTop: spacing.lg }} />
      </ScrollView>
    </ScreenContainer>
  );
}

// ── Offline (local fallback) result screen ───────────────────────────────

function OfflineResultView({
  result,
  isAuthenticated,
  onRestart,
}: {
  result: QuizResult;
  isAuthenticated: boolean;
  onRestart: () => void;
}) {
  const { t, lang } = useTranslation();
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);

  const leadMutation = useMutation({
    mutationFn: () =>
      submitLead({
        name: 'Quiz result',
        email: email.trim(),
        message: `Quiz score (offline): ${result.pct}% (${result.tier}) — via mobile app`,
        interest_type: 'candidate',
      }),
  });

  const onSendEmail = () => {
    setEmailError(null);
    if (!isValidEmail(email)) {
      setEmailError(t('auth.invalidEmail'));
      return;
    }
    leadMutation.mutate();
  };

  const tierColor = result.tier === 'senior' ? colors.gold : result.tier === 'medior' ? colors.success : colors.textMuted;

  return (
    <ScreenContainer>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        <View style={{ marginBottom: spacing.md }}>
          <Chip label={t('quiz.offlineBadge')} tone="muted" />
        </View>
        <Text style={[typography.h1, { marginBottom: spacing.sm }]}>{t('quiz.resultTitle')}</Text>
        <Text style={[typography.bodyMuted, { marginBottom: spacing.lg }]}>{t('quiz.offlineNotice')}</Text>

        <Card style={{ alignItems: 'center', paddingVertical: spacing.xl }}>
          <Text style={[styles.tierBadge, { color: tierColor, borderColor: tierColor }]}>{t(`quiz.tier.${result.tier}`)}</Text>
          <Text style={[typography.h2, { marginTop: spacing.md }]}>{result.pct}%</Text>
          <Text style={typography.bodyMuted}>
            {result.score} / {result.maxScore} {t('quiz.scoreLabel')}
          </Text>
        </Card>

        <Text style={[typography.h3, { marginTop: spacing.xl, marginBottom: spacing.md }]}>{t('quiz.domainScores')}</Text>
        {result.domainScores.map((d) => (
          <View key={d.domain} style={{ marginBottom: spacing.sm }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={typography.bodyMuted}>{t(`quiz.domain.${d.domain}`)}</Text>
              <Text style={typography.bodyMuted}>{d.pct}%</Text>
            </View>
            <View style={styles.barTrack}>
              <View style={[styles.barFill, { width: `${d.pct}%` }]} />
            </View>
          </View>
        ))}

        <Card style={{ marginTop: spacing.xl, backgroundColor: colors.goldLight, borderColor: colors.gold }}>
          <Text style={[typography.h3, { color: colors.gold }]}>{t('quiz.growthTitle')}</Text>
          <Text style={[typography.body, { marginTop: spacing.sm }]}>{GROWTH_TIPS[result.weakestDomain][lang]}</Text>
          <Pressable onPress={() => Linking.openURL(BLOG_URL)} style={{ marginTop: spacing.sm }}>
            <Text style={{ color: colors.gold, fontWeight: '600' }}>gsprecruitment.nl/blog →</Text>
          </Pressable>
        </Card>

        <Text style={[typography.h3, { marginTop: spacing.xl, marginBottom: spacing.md }]}>{t('quiz.feedbackTitle')}</Text>
        {result.feedback.map((f) => (
          <Card key={f.question.id} style={{ marginBottom: spacing.sm }}>
            <Text style={typography.body}>{lang === 'nl' ? f.question.question_nl : f.question.question_en}</Text>
            <Text style={[typography.caption, { marginTop: spacing.xs }]}>
              {f.points}/{f.maxPoints} {t('quiz.scoreLabel')}
            </Text>
            <Text style={[typography.bodyMuted, { marginTop: spacing.xs }]}>
              {lang === 'nl' ? f.question.explanation_nl : f.question.explanation_en}
            </Text>
          </Card>
        ))}

        {!isAuthenticated && (
          <Card style={{ marginTop: spacing.lg }}>
            <Text style={typography.h3}>{t('quiz.ctaProfile')}</Text>
            <Text style={[typography.bodyMuted, { marginVertical: spacing.sm }]}>{t('quiz.ctaProfileBody')}</Text>
            <Button title={t('quiz.ctaProfile')} onPress={() => router.push('/(auth)/register')} />
          </Card>
        )}

        <Card style={{ marginTop: spacing.lg }}>
          <Text style={typography.h3}>{t('quiz.emailPrompt')}</Text>
          {leadMutation.isSuccess ? (
            <Text style={{ color: colors.success, marginTop: spacing.sm }}>{t('quiz.emailSent')}</Text>
          ) : (
            <>
              <TextField
                value={email}
                onChangeText={setEmail}
                placeholder={t('quiz.emailPlaceholder')}
                autoCapitalize="none"
                keyboardType="email-address"
                style={{ marginTop: spacing.sm }}
              />
              {emailError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{emailError}</Text>}
              {leadMutation.isError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{t('quiz.emailError')}</Text>}
              <Button title={t('quiz.sendResult')} onPress={onSendEmail} loading={leadMutation.isPending} variant="secondary" />
            </>
          )}
        </Card>

        <Button title={t('quiz.restart')} onPress={onRestart} variant="ghost" style={{ marginTop: spacing.lg }} />
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  progressTrack: { height: 6, backgroundColor: colors.navyLight, borderRadius: radius.pill, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: colors.gold },
  option: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.navyLight,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  optionPressed: { borderColor: colors.gold, backgroundColor: colors.goldLight },
  tierBadge: {
    fontSize: 16,
    fontWeight: '700',
    borderWidth: 1.5,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  barTrack: { height: 8, backgroundColor: colors.navyLight, borderRadius: radius.pill, overflow: 'hidden', marginTop: spacing.xs },
  barFill: { height: '100%', backgroundColor: colors.gold },
});
