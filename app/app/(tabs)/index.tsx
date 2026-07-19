import React from 'react';
import { FlatList, RefreshControl, Text } from 'react-native';
import { router } from 'expo-router';
import { ScreenContainer, LoadingState, ErrorState, EmptyState } from '../../components/ui';
import { JobCard } from '../../components/JobCard';
import { spacing, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { useJobsQuery } from '../../lib/queries';
import { colors } from '../../lib/theme';

export default function JobsFeedScreen() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch, isRefetching } = useJobsQuery();

  if (isLoading) return <LoadingState label={t('common.loading')} />;
  if (isError) return <ErrorState message={t('jobs.loadError')} onRetry={refetch} retryLabel={t('common.retry')} />;

  return (
    <ScreenContainer>
      <FlatList
        data={data ?? []}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={{ padding: spacing.md, flexGrow: 1 }}
        ListHeaderComponent={<Text style={[typography.h1, { marginBottom: spacing.md }]}>{t('jobs.title')}</Text>}
        renderItem={({ item }) => <JobCard job={item} onPress={() => router.push(`/job/${item.id}`)} />}
        ListEmptyComponent={<EmptyState title={t('jobs.empty')} />}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.gold} colors={[colors.gold]} />
        }
      />
    </ScreenContainer>
  );
}
