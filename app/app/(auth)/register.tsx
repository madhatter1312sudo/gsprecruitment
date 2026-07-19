import React, { useState } from 'react';
import { View, Text, ScrollView, KeyboardAvoidingView, Platform, Pressable } from 'react-native';
import { router, Link } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { ScreenContainer, TextField, Button } from '../../components/ui';
import { colors, spacing, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { register, ApiError } from '../../lib/api';
import { useAuthStore } from '../../lib/auth';
import { isValidEmail, isStrongPassword } from '../../lib/validation';

export default function RegisterScreen() {
  const { t } = useTranslation();
  const setSession = useAuthStore((s) => s.setSession);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => register(email.trim(), password, fullName.trim()),
    onSuccess: async (data) => {
      await setSession(data.access_token, data.user);
      if (router.canGoBack()) router.back();
      else router.replace('/(tabs)');
    },
  });

  const onSubmit = () => {
    setFieldError(null);
    if (!fullName.trim()) {
      setFieldError(t('auth.nameRequired'));
      return;
    }
    if (!isValidEmail(email)) {
      setFieldError(t('auth.invalidEmail'));
      return;
    }
    if (!isStrongPassword(password)) {
      setFieldError(t('auth.passwordTooWeak'));
      return;
    }
    mutation.mutate();
  };

  const serverError =
    mutation.isError && mutation.error instanceof ApiError && mutation.error.status === 409
      ? t('register.emailInUse')
      : mutation.isError
        ? t('common.errorGeneric')
        : null;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
      <ScreenContainer>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, flexGrow: 1, justifyContent: 'center' }}>
          <Text style={[typography.h1, { marginBottom: spacing.xs }]}>{t('register.title')}</Text>
          <Text style={[typography.bodyMuted, { marginBottom: spacing.xl }]}>{t('register.subtitle')}</Text>

          <TextField label={t('auth.fullName')} value={fullName} onChangeText={setFullName} autoComplete="name" />
          <TextField
            label={t('auth.email')}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
          />
          <TextField
            label={t('auth.password')}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="password-new"
          />
          <Text style={[typography.caption, { marginTop: -spacing.sm, marginBottom: spacing.md }]}>
            {t('auth.passwordRules')}
          </Text>

          {(fieldError || serverError) && (
            <Text style={{ color: colors.danger, marginBottom: spacing.md }}>{fieldError ?? serverError}</Text>
          )}

          <Button title={t('register.submit')} onPress={onSubmit} loading={mutation.isPending} />

          <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: spacing.xl }}>
            <Text style={typography.bodyMuted}>{t('register.haveAccount')} </Text>
            <Link href="/(auth)/login" replace>
              <Text style={{ color: colors.gold, fontWeight: '700' }}>{t('register.login')}</Text>
            </Link>
          </View>
        </ScrollView>
      </ScreenContainer>
    </KeyboardAvoidingView>
  );
}
