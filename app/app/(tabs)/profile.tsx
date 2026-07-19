import React, { useEffect, useState } from 'react';
import { ScrollView, View, Text, Switch, Alert, Share, StyleSheet } from 'react-native';
import { router } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { ScreenContainer, Card, Button, TextField, LoadingState } from '../../components/ui';
import { colors, spacing, typography } from '../../lib/theme';
import { useTranslation, type Lang } from '../../lib/i18n';
import { useAuthStore } from '../../lib/auth';
import {
  useProfileQuery,
  useUpdateProfileMutation,
  useUploadCvMutation,
  useGdprExportMutation,
  useDeleteAccountMutation,
} from '../../lib/queries';
import type { CandidateProfileUpdate } from '../../lib/api';

export default function ProfileScreen() {
  const { t } = useTranslation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  if (!isAuthenticated) {
    return (
      <ScreenContainer style={{ padding: spacing.lg, justifyContent: 'center', flex: 1 }}>
        <Text style={[typography.h1, { marginBottom: spacing.sm }]}>{t('profile.loginRequiredTitle')}</Text>
        <Text style={[typography.bodyMuted, { marginBottom: spacing.xl }]}>{t('profile.loginRequiredBody')}</Text>
        <Button title={t('profile.login')} onPress={() => router.push('/(auth)/login')} />
        <Button
          title={t('profile.createAccount')}
          onPress={() => router.push('/(auth)/register')}
          variant="secondary"
          style={{ marginTop: spacing.md }}
        />
      </ScreenContainer>
    );
  }

  const onLogout = () => {
    Alert.alert(t('profile.logoutConfirm'), undefined, [
      { text: t('common.cancel'), style: 'cancel' },
      { text: t('common.logout'), style: 'destructive', onPress: () => logout() },
    ]);
  };

  return (
    <ScreenContainer>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        <Text style={[typography.h1, { marginBottom: spacing.xs }]}>{t('profile.title')}</Text>
        {user ? <Text style={[typography.bodyMuted, { marginBottom: spacing.xl }]}>{user.email}</Text> : null}

        <ProfileForm />
        <CvSection />
        <SettingsSection />
        <PrivacySection />

        <Button title={t('common.logout')} onPress={onLogout} variant="danger" style={{ marginTop: spacing.xl }} />
      </ScrollView>
    </ScreenContainer>
  );
}

function ProfileForm() {
  const { t } = useTranslation();
  const profileQuery = useProfileQuery();
  const updateMutation = useUpdateProfileMutation();
  const [form, setForm] = useState<CandidateProfileUpdate>({});
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (profileQuery.data && !initialized) {
      const p = profileQuery.data;
      setForm({
        current_title: p.current_title ?? '',
        current_company: p.current_company ?? '',
        location: p.location ?? '',
        phone: p.phone ?? '',
        linkedin_url: p.linkedin_url ?? '',
        years_experience: p.years_experience ?? undefined,
        willing_to_relocate: p.willing_to_relocate,
      });
      setInitialized(true);
    }
  }, [profileQuery.data, initialized]);

  if (profileQuery.isLoading) return <LoadingState label={t('common.loading')} />;

  const set = <K extends keyof CandidateProfileUpdate>(key: K, value: CandidateProfileUpdate[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <Card style={{ marginBottom: spacing.lg }}>
      <Text style={[typography.h3, { marginBottom: spacing.md }]}>{t('profile.personalInfo')}</Text>
      <TextField label={t('profile.currentTitle')} value={form.current_title ?? ''} onChangeText={(v) => set('current_title', v)} />
      <TextField label={t('profile.currentCompany')} value={form.current_company ?? ''} onChangeText={(v) => set('current_company', v)} />
      <TextField label={t('profile.location')} value={form.location ?? ''} onChangeText={(v) => set('location', v)} />
      <TextField label={t('profile.phone')} value={form.phone ?? ''} onChangeText={(v) => set('phone', v)} keyboardType="phone-pad" />
      <TextField label={t('profile.linkedin')} value={form.linkedin_url ?? ''} onChangeText={(v) => set('linkedin_url', v)} autoCapitalize="none" />
      <TextField
        label={t('profile.yearsExperience')}
        value={form.years_experience !== undefined ? String(form.years_experience) : ''}
        onChangeText={(v) => set('years_experience', v ? Number(v) : undefined)}
        keyboardType="numeric"
      />
      <View style={styles.switchRow}>
        <Text style={typography.body}>{t('profile.willingToRelocate')}</Text>
        <Switch
          value={!!form.willing_to_relocate}
          onValueChange={(v) => set('willing_to_relocate', v)}
          trackColor={{ false: colors.navyLight, true: colors.gold }}
          thumbColor={colors.white}
        />
      </View>

      {updateMutation.isSuccess && <Text style={{ color: colors.success, marginBottom: spacing.sm }}>{t('profile.saveSuccess')}</Text>}
      {updateMutation.isError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{t('profile.saveError')}</Text>}
      <Button title={t('common.save')} onPress={() => updateMutation.mutate(form)} loading={updateMutation.isPending} />
    </Card>
  );
}

function CvSection() {
  const { t } = useTranslation();
  const profileQuery = useProfileQuery();
  const uploadMutation = useUploadCvMutation();
  const hasCv = !!profileQuery.data?.cv_file_path;

  const onPick = async () => {
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
    uploadMutation.mutate({ uri: asset.uri, name: asset.name, mimeType: asset.mimeType });
  };

  return (
    <Card style={{ marginBottom: spacing.lg }}>
      <Text style={[typography.h3, { marginBottom: spacing.sm }]}>{t('profile.cvTitle')}</Text>
      <Text style={[typography.bodyMuted, { marginBottom: spacing.md }]}>
        {hasCv ? `✓ ${t('profile.cvUploaded')}` : t('profile.cvMissing')}
      </Text>
      {uploadMutation.isSuccess && <Text style={{ color: colors.success, marginBottom: spacing.sm }}>{t('profile.cvUploadSuccess')}</Text>}
      {uploadMutation.isError && <Text style={{ color: colors.danger, marginBottom: spacing.sm }}>{t('profile.cvUploadError')}</Text>}
      <Button
        title={hasCv ? t('profile.cvReplace') : t('profile.cvUpload')}
        onPress={onPick}
        loading={uploadMutation.isPending}
        variant="secondary"
      />
    </Card>
  );
}

function SettingsSection() {
  const { t, lang, setLang } = useTranslation();
  return (
    <Card style={{ marginBottom: spacing.lg }}>
      <Text style={[typography.h3, { marginBottom: spacing.md }]}>{t('profile.settings')}</Text>
      <Text style={[typography.body, { marginBottom: spacing.sm }]}>{t('profile.language')}</Text>
      <View style={{ flexDirection: 'row', gap: spacing.sm }}>
        {(['nl', 'en'] as Lang[]).map((l) => (
          <Button
            key={l}
            title={l.toUpperCase()}
            onPress={() => setLang(l)}
            variant={lang === l ? 'primary' : 'secondary'}
            style={{ flex: 1 }}
          />
        ))}
      </View>
    </Card>
  );
}

function PrivacySection() {
  const { t } = useTranslation();
  const logout = useAuthStore((s) => s.logout);
  const exportMutation = useGdprExportMutation();
  const deleteMutation = useDeleteAccountMutation();

  const onExport = async () => {
    try {
      const data = await exportMutation.mutateAsync();
      await Share.share({
        title: 'GSP Recruitment — data export',
        message: JSON.stringify(data, null, 2),
      });
    } catch {
      Alert.alert(t('common.error'), t('profile.exportError'));
    }
  };

  const onDelete = () => {
    Alert.alert(t('profile.deleteAccount'), t('profile.deleteWarning1'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('profile.deleteAccount'),
        style: 'destructive',
        onPress: () => {
          Alert.alert(t('profile.deleteAccount'), t('profile.deleteWarning2'), [
            { text: t('common.cancel'), style: 'cancel' },
            {
              text: t('common.confirm'),
              style: 'destructive',
              onPress: async () => {
                try {
                  await deleteMutation.mutateAsync();
                  await logout();
                  router.replace('/(tabs)');
                } catch {
                  Alert.alert(t('common.error'), t('profile.deleteError'));
                }
              },
            },
          ]);
        },
      },
    ]);
  };

  return (
    <Card style={{ marginBottom: spacing.lg }}>
      <Text style={[typography.h3, { marginBottom: spacing.md }]}>{t('profile.privacyTitle')}</Text>
      <Button title={t('profile.exportData')} onPress={onExport} loading={exportMutation.isPending} variant="secondary" />
      <Button
        title={t('profile.deleteAccount')}
        onPress={onDelete}
        loading={deleteMutation.isPending}
        variant="danger"
        style={{ marginTop: spacing.sm }}
      />
    </Card>
  );
}

const styles = StyleSheet.create({
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
});
