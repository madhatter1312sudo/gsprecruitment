import React, { useMemo, useState } from 'react';
import { ScrollView, View, Text, StyleSheet } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { ScreenContainer, LoadingState, ErrorState, Chip, Button, Card } from '../../components/ui';
import { colors, spacing, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { useJob, useApplicationsQuery, useApplyMutation, useProfileQuery, useUploadCvMutation } from '../../lib/queries';
import { useAuthStore } from '../../lib/auth';
import { formatSalaryRange, locationTypeIcon, seniorityLabel } from '../../lib/format';
import { ApiError } from '../../lib/api';

export default function JobDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(id);
  const { t, lang } = useTranslation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const jobQuery = useJob(jobId);
  const applicationsQuery = useApplicationsQuery();
  const profileQuery = useProfileQuery();
  const applyMutation = useApplyMutation();
  const uploadCvMutation = useUploadCvMutation();

  const [pickerBusy, setPickerBusy] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  const alreadyApplied = useMemo(
    () => applicationsQuery.data?.items.some((a) => a.job_id === jobId) ?? false,
    [applicationsQuery.data, jobId],
  );

  if (jobQuery.isLoading) return <LoadingState label={t('common.loading')} />;
  const job = jobQuery.data;
  if (!job) return <ErrorState message={t('job.notFound')} onRetry={() => jobQuery.refetch()} retryLabel={t('common.retry')} />;

  const hasCv = !!profileQuery.data?.cv_file_path;

  const doApply = () => {
    setApplyError(null);
    applyMutation.mutate(jobId, {
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) return; // already applied — treated as success below
        setApplyError(t('job.applyError'));
      },
    });
  };

  const onUploadThenApply = async () => {
    setApplyError(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: [
          'application/pdf',
          'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'text/plain',
        ],
        copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      setPickerBusy(true);
      await uploadCvMutation.mutateAsync({ uri: asset.uri, name: asset.name, mimeType: asset.mimeType });
      doApply();
    } catch {
      setApplyError(t('profile.cvUploadError'));
    } finally {
      setPickerBusy(false);
    }
  };

  const applied = alreadyApplied || applyMutation.isSuccess || (applyMutation.isError && applyMutation.error instanceof ApiError && applyMutation.error.status === 409);

  return (
    <ScreenContainer>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        <Text style={typography.h1}>{job.title}</Text>
        <View style={styles.chipRow}>
          {job.department ? <Chip label={job.department} tone="gold" /> : null}
          {job.seniority ? <Chip label={seniorityLabel(job.seniority, lang)} /> : null}
        </View>
        <View style={styles.metaRow}>
          <Text style={styles.metaText}>
            {locationTypeIcon(job.location_type)} {job.location_type ? t(`common.${job.location_type}`) : '—'}
          </Text>
          <Text style={styles.metaText}>💶 {formatSalaryRange(job.salary_min, job.salary_max, t)}</Text>
        </View>

        {job.description ? (
          <Card style={{ marginTop: spacing.lg }}>
            <Text style={typography.h3}>{t('job.description')}</Text>
            <Text style={[typography.body, { marginTop: spacing.sm }]}>{job.description}</Text>
          </Card>
        ) : null}

        {job.requirements ? (
          <Card style={{ marginTop: spacing.md }}>
            <Text style={typography.h3}>{t('job.requirements')}</Text>
            <Text style={[typography.body, { marginTop: spacing.sm }]}>{job.requirements}</Text>
          </Card>
        ) : null}

        <View style={{ marginTop: spacing.xl }}>
          {!isAuthenticated ? (
            <Card>
              <Text style={typography.h3}>{t('job.loginRequiredTitle')}</Text>
              <Text style={[typography.bodyMuted, { marginVertical: spacing.sm }]}>{t('job.loginRequiredBody')}</Text>
              <Button title={t('profile.login')} onPress={() => router.push('/(auth)/login')} />
            </Card>
          ) : applied ? (
            <Card>
              <Text style={[typography.h3, { color: colors.success }]}>✓ {t('job.applied')}</Text>
              <Text style={[typography.bodyMuted, { marginTop: spacing.sm }]}>{t('job.applySuccessBody')}</Text>
            </Card>
          ) : !hasCv ? (
            <Card>
              <Text style={typography.h3}>{t('job.cvRequiredTitle')}</Text>
              <Text style={[typography.bodyMuted, { marginVertical: spacing.sm }]}>{t('job.cvRequiredBody')}</Text>
              <Button
                title={t('job.uploadCv')}
                onPress={onUploadThenApply}
                loading={pickerBusy || uploadCvMutation.isPending || applyMutation.isPending}
              />
            </Card>
          ) : (
            <Button title={t('job.apply')} onPress={doApply} loading={applyMutation.isPending} />
          )}
          {applyError ? <Text style={{ color: colors.danger, marginTop: spacing.sm }}>{applyError}</Text> : null}
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  chipRow: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.sm },
  metaRow: { flexDirection: 'row', gap: spacing.lg, marginTop: spacing.md },
  metaText: { ...typography.bodyMuted },
});
