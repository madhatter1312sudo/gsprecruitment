import React, { useMemo, useState } from 'react';
import { ScrollView, View, Text, Pressable, StyleSheet, Linking } from 'react-native';
import { router } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { ScreenContainer, Card, Button, TextField } from '../../components/ui';
import { colors, spacing, radius, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { useAuthStore } from '../../lib/auth';
import { QUIZ_QUESTIONS, scoreQuiz, GROWTH_TIPS, BLOG_URL, type QuizAnswer, type QuizResult } from '../../lib/quiz-data';
import { submitLead } from '../../lib/api';
import { isValidEmail } from '../../lib/validation';

type Stage = 'intro' | 'question' | 'result';

export default function QuizScreen() {
  const { t, lang } = useTranslation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [stage, setStage] = useState<Stage>('intro');
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<QuizAnswer[]>([]);

  const result: QuizResult | null = useMemo(() => (stage === 'result' ? scoreQuiz(answers) : null), [stage, answers]);

  const restart = () => {
    setStage('intro');
    setIndex(0);
    setAnswers([]);
  };

  const selectOption = (optionIndex: number) => {
    const question = QUIZ_QUESTIONS[index];
    const next = [...answers.filter((a) => a.question_id !== question.id), { question_id: question.id, option_index: optionIndex }];
    setAnswers(next);
    if (index + 1 < QUIZ_QUESTIONS.length) {
      setIndex(index + 1);
    } else {
      setStage('result');
    }
  };

  if (stage === 'intro') {
    return (
      <ScreenContainer style={{ padding: spacing.lg, justifyContent: 'center', flex: 1 }}>
        <Text style={[typography.h1, { marginBottom: spacing.sm }]}>{t('quiz.introTitle')}</Text>
        <Text style={[typography.bodyMuted, { marginBottom: spacing.xl }]}>{t('quiz.introBody')}</Text>
        <Button title={t('quiz.start')} onPress={() => setStage('question')} />
      </ScreenContainer>
    );
  }

  if (stage === 'question') {
    const question = QUIZ_QUESTIONS[index];
    const progress = (index + 1) / QUIZ_QUESTIONS.length;
    return (
      <ScreenContainer style={{ padding: spacing.lg }}>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
        </View>
        <Text style={[typography.caption, { marginTop: spacing.sm, marginBottom: spacing.lg }]}>
          {t('quiz.questionOf', { current: index + 1, total: QUIZ_QUESTIONS.length })}
        </Text>
        <ScrollView>
          <Text style={[typography.h2, { marginBottom: spacing.lg }]}>
            {lang === 'nl' ? question.question_nl : question.question_en}
          </Text>
          {question.options.map((opt, i) => (
            <Pressable key={i} onPress={() => selectOption(i)} style={({ pressed }) => [styles.option, pressed && styles.optionPressed]}>
              <Text style={typography.body}>{lang === 'nl' ? opt.text_nl : opt.text_en}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </ScreenContainer>
    );
  }

  // stage === 'result'
  return <QuizResultView result={result!} isAuthenticated={isAuthenticated} onRestart={restart} />;
}

function QuizResultView({
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
        message: `Quiz score: ${result.pct}% (${result.tier}) — via mobile app`,
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
        <Text style={[typography.h1, { marginBottom: spacing.lg }]}>{t('quiz.resultTitle')}</Text>

        <Card style={{ alignItems: 'center', paddingVertical: spacing.xl }}>
          <Text style={[styles.tierBadge, { color: tierColor, borderColor: tierColor }]}>{t(`quiz.tier.${result.tier}`)}</Text>
          <Text style={[typography.h2, { marginTop: spacing.md }]}>{result.pct}%</Text>
          <Text style={typography.bodyMuted}>{result.score} / {result.maxScore} {t('quiz.scoreLabel')}</Text>
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
          <Text style={[typography.body, { marginTop: spacing.sm }]}>
            {GROWTH_TIPS[result.weakestDomain][lang]}
          </Text>
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
