import React from 'react';
import { FlatList, View, Text, Pressable, RefreshControl } from 'react-native';
import { router } from 'expo-router';
import { ScreenContainer, LoadingState, ErrorState, EmptyState, Card, Button, Chip } from '../../components/ui';
import { MatchRing } from '../../components/MatchRing';
import { colors, spacing, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { useMatchesQuery } from '../../lib/queries';
import { useAuthStore } from '../../lib/auth';
import type { MatchItem } from '../../lib/api';

export default function MatchesScreen() {
  const { t } = useTranslation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data, isLoading, isError, refetch, isRefetching } = useMatchesQuery();

  if (!isAuthenticated) {
    return (
      <ScreenContainer style={{ padding: spacing.lg }}>
        <Text style={[typography.h1, { marginBottom: spacing.lg }]}>{t('matches.title')}</Text>
        <Card>
          <Text style={typography.bodyMuted}>{t('matches.loginRequired')}</Text>
          <Button title={t('profile.login')} onPress={() => router.push('/(auth)/login')} style={{ marginTop: spacing.md }} />
        </Card>
      </ScreenContainer>
    );
  }

  if (isLoading) return <LoadingState label={t('common.loading')} />;
  if (isError) return <ErrorState message={t('common.errorGeneric')} onRetry={refetch} retryLabel={t('common.retry')} />;

  const items = data?.items ?? [];

  return (
    <ScreenContainer>
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={{ padding: spacing.md, flexGrow: 1 }}
        ListHeaderComponent={<Text style={[typography.h1, { marginBottom: spacing.md }]}>{t('matches.title')}</Text>}
        renderItem={({ item }) => <MatchRow item={item} />}
        ListEmptyComponent={
          <View style={{ marginTop: spacing.xl }}>
            <EmptyState title={t('matches.empty')} body={t('matches.emptyBody')} />
            <Button
              title={t('matches.completeProfile')}
              onPress={() => router.push('/(tabs)/profile')}
              variant="secondary"
              style={{ marginTop: spacing.md }}
            />
          </View>
        }
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.gold} colors={[colors.gold]} />
        }
      />
    </ScreenContainer>
  );
}

function MatchRow({ item }: { item: MatchItem }) {
  const { t } = useTranslation();
  const statusKey = `matches.status.${item.status}`;
  return (
    <Pressable onPress={() => router.push(`/job/${item.job_id}`)}>
      <Card style={{ flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md }}>
        <MatchRing score={item.match_score ?? 0} />
        <View style={{ marginLeft: spacing.md, flex: 1 }}>
          <Text style={typography.h3} numberOfLines={1}>{item.job_title}</Text>
          <Text style={typography.bodyMuted} numberOfLines={1}>{item.company_name}</Text>
          <View style={{ marginTop: spacing.xs, alignSelf: 'flex-start' }}>
            <Chip label={t(statusKey)} tone="gold" />
          </View>
        </View>
      </Card>
    </Pressable>
  );
}
