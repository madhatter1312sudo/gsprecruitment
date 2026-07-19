import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { colors, spacing, radius, typography } from '../lib/theme';
import { Chip } from './ui';
import type { JobOrder } from '../lib/api';
import { useTranslation } from '../lib/i18n';
import { formatSalaryRange, locationTypeIcon, seniorityLabel } from '../lib/format';

export function JobCard({ job, onPress }: { job: JobOrder; onPress: () => void }) {
  const { t, lang } = useTranslation();
  return (
    <Pressable onPress={onPress} testID="job-card" style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <Text style={styles.title} numberOfLines={2}>{job.title}</Text>
      <View style={styles.chipRow}>
        {job.department ? <Chip label={job.department} tone="gold" /> : null}
        {job.seniority ? <Chip label={seniorityLabel(job.seniority, lang)} /> : null}
      </View>
      <View style={styles.metaRow}>
        <Text style={styles.metaIcon}>{locationTypeIcon(job.location_type)}</Text>
        <Text style={styles.metaText}>
          {job.location_type ? t(`common.${job.location_type}`) : '—'}
        </Text>
        <Text style={styles.metaDot}>·</Text>
        <Text style={styles.metaText}>{formatSalaryRange(job.salary_min, job.salary_max, t)}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.navyLight,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  pressed: { opacity: 0.8, borderColor: colors.gold },
  title: { ...typography.h3, marginBottom: spacing.sm },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm },
  metaRow: { flexDirection: 'row', alignItems: 'center' },
  metaIcon: { fontSize: 14, marginRight: spacing.xs },
  metaText: { ...typography.bodyMuted },
  metaDot: { color: colors.textFaint, marginHorizontal: spacing.xs },
});
