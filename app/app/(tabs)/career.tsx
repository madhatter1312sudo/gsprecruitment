import React, { useState } from 'react';
import { ScrollView, View, Text, Pressable, StyleSheet } from 'react-native';
import { router } from 'expo-router';
import { ScreenContainer, Card, Button, LoadingState } from '../../components/ui';
import { colors, spacing, radius, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { useAuthStore } from '../../lib/auth';
import { useSalaryQuery, useApplicationsQuery } from '../../lib/queries';
import { ROLE_OPTIONS, SENIORITY_OPTIONS, LOCATION_OPTIONS, CAREER_TIPS } from '../../lib/career-tips';
import type { MatchItem } from '../../lib/api';

const PIPELINE_STAGES = ['applied', 'interviewing', 'offered', 'placed'] as const;

function SelectRow<T extends string>({ options, value, onChange, getLabel }: { options: T[]; value: T; onChange: (v: T) => void; getLabel: (v: T) => string }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs, paddingVertical: spacing.xs }}>
      {options.map((opt) => {
        const active = opt === value;
        return (
          <Pressable
            key={opt}
            onPress={() => onChange(opt)}
            style={[styles.selectChip, active && styles.selectChipActive]}
          >
            <Text style={[styles.selectChipText, active && styles.selectChipTextActive]}>{getLabel(opt)}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export default function CareerScreen() {
  const { t, lang } = useTranslation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [role, setRole] = useState(ROLE_OPTIONS[0]);
  const [seniority, setSeniority] = useState(SENIORITY_OPTIONS[2].value); // senior default
  const [location, setLocation] = useState(LOCATION_OPTIONS[0]);
  const [queryEnabled, setQueryEnabled] = useState(false);

  const salaryQuery = useSalaryQuery({ role_title: role, seniority, location }, queryEnabled);
  const applicationsQuery = useApplicationsQuery();

  const benchmark = salaryQuery.data?.[0];
  const maxBar = benchmark?.p90 ?? 1;

  return (
    <ScreenContainer>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        <Text style={[typography.h1, { marginBottom: spacing.lg }]}>{t('career.title')}</Text>

        <Text style={typography.h3}>{t('career.salaryTitle')}</Text>
        <Text style={[styles.label, { marginTop: spacing.md }]}>{t('career.role')}</Text>
        <SelectRow options={ROLE_OPTIONS} value={role} onChange={setRole} getLabel={(v) => v} />

        <Text style={styles.label}>{t('career.seniority')}</Text>
        <SelectRow
          options={SENIORITY_OPTIONS.map((s) => s.value)}
          value={seniority}
          onChange={setSeniority}
          getLabel={(v) => {
            const opt = SENIORITY_OPTIONS.find((s) => s.value === v)!;
            return lang === 'nl' ? opt.label_nl : opt.label_en;
          }}
        />

        <Text style={styles.label}>{t('career.location')}</Text>
        <SelectRow options={LOCATION_OPTIONS} value={location} onChange={setLocation} getLabel={(v) => v} />

        <Button
          title={t('career.calculate')}
          onPress={() => setQueryEnabled(true)}
          loading={salaryQuery.isFetching}
          style={{ marginTop: spacing.md }}
        />

        {queryEnabled && !salaryQuery.isFetching && (
          <Card style={{ marginTop: spacing.lg }}>
            {benchmark ? (
              <>
                <SalaryBar label="p25" value={benchmark.p25} max={maxBar} />
                <SalaryBar label="p50" value={benchmark.p50} max={maxBar} highlight />
                <SalaryBar label="p75" value={benchmark.p75} max={maxBar} />
                <SalaryBar label="p90" value={benchmark.p90} max={maxBar} />
                {benchmark.sample_size ? (
                  <Text style={[typography.caption, { marginTop: spacing.sm }]}>
                    {t('career.sampleSize', { n: benchmark.sample_size })}
                  </Text>
                ) : null}
              </>
            ) : (
              <Text style={typography.bodyMuted}>{t('career.noData')}</Text>
            )}
          </Card>
        )}

        <Text style={[typography.h3, { marginTop: spacing.xl }]}>{t('career.pipelineTitle')}</Text>
        {!isAuthenticated ? (
          <Card style={{ marginTop: spacing.md }}>
            <Text style={typography.bodyMuted}>{t('career.pipelineLoginRequired')}</Text>
            <Button title={t('profile.login')} onPress={() => router.push('/(auth)/login')} style={{ marginTop: spacing.md }} />
          </Card>
        ) : applicationsQuery.isLoading ? (
          <LoadingState />
        ) : !applicationsQuery.data?.items.length ? (
          <Card style={{ marginTop: spacing.md }}>
            <Text style={typography.bodyMuted}>{t('career.pipelineEmpty')}</Text>
          </Card>
        ) : (
          applicationsQuery.data.items.map((item) => <PipelineCard key={item.id} item={item} />)
        )}

        <Text style={[typography.h3, { marginTop: spacing.xl, marginBottom: spacing.md }]}>{t('career.coachingTitle')}</Text>
        {CAREER_TIPS.map((tip, i) => (
          <Card key={i} style={{ marginBottom: spacing.sm }}>
            <Text style={typography.body}>{lang === 'nl' ? tip.nl : tip.en}</Text>
          </Card>
        ))}
      </ScrollView>
    </ScreenContainer>
  );
}

function SalaryBar({ label, value, max, highlight }: { label: string; value: number; max: number; highlight?: boolean }) {
  const pct = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0;
  return (
    <View style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text style={typography.bodyMuted}>{label}</Text>
        <Text style={[typography.bodyMuted, highlight && { color: colors.gold, fontWeight: '700' }]}>€{Math.round(value / 1000)}k</Text>
      </View>
      <View style={styles.barTrack}>
        <View style={[styles.barFill, { width: `${pct}%` }, highlight && { backgroundColor: colors.gold }]} />
      </View>
    </View>
  );
}

function PipelineCard({ item }: { item: MatchItem }) {
  const { t } = useTranslation();
  const isRejected = item.status === 'rejected';
  const currentIdx = PIPELINE_STAGES.indexOf(item.status as (typeof PIPELINE_STAGES)[number]);

  return (
    <Card style={{ marginTop: spacing.md }}>
      <Text style={typography.h3} numberOfLines={1}>{item.job_title}</Text>
      <Text style={typography.bodyMuted} numberOfLines={1}>{item.company_name}</Text>
      {isRejected ? (
        <Text style={{ color: colors.danger, marginTop: spacing.sm, fontWeight: '600' }}>{t('matches.status.rejected')}</Text>
      ) : (
        <View style={styles.timelineRow}>
          {PIPELINE_STAGES.map((stage, i) => (
            <React.Fragment key={stage}>
              <View style={styles.timelineStep}>
                <View style={[styles.timelineDot, i <= currentIdx && styles.timelineDotActive]} />
                <Text style={[styles.timelineLabel, i <= currentIdx && { color: colors.gold }]}>{t(`matches.status.${stage}`)}</Text>
              </View>
              {i < PIPELINE_STAGES.length - 1 && (
                <View style={[styles.timelineLine, i < currentIdx && styles.timelineLineActive]} />
              )}
            </React.Fragment>
          ))}
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  label: { color: colors.textMuted, fontSize: 13, fontWeight: '600', marginTop: spacing.md, marginBottom: spacing.xs },
  selectChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.navyLight,
  },
  selectChipActive: { borderColor: colors.gold, backgroundColor: colors.goldLight },
  selectChipText: { color: colors.textMuted, fontSize: 13, fontWeight: '600' },
  selectChipTextActive: { color: colors.gold },
  barTrack: { height: 10, backgroundColor: colors.navyLight, borderRadius: radius.pill, overflow: 'hidden', marginTop: 4 },
  barFill: { height: '100%', backgroundColor: colors.navyMid },
  timelineRow: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.md },
  timelineStep: { alignItems: 'center', width: 64 },
  timelineDot: { width: 12, height: 12, borderRadius: 6, backgroundColor: colors.navyLight, borderWidth: 2, borderColor: colors.border },
  timelineDotActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  timelineLabel: { fontSize: 9, color: colors.textFaint, marginTop: 4, textAlign: 'center' },
  timelineLine: { flex: 1, height: 2, backgroundColor: colors.border, marginBottom: 14 },
  timelineLineActive: { backgroundColor: colors.gold },
});
