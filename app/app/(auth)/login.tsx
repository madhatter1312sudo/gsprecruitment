import React, { useState } from 'react';
import { View, Text, ScrollView, KeyboardAvoidingView, Platform, Pressable } from 'react-native';
import { router, Link } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { ScreenContainer, TextField, Button } from '../../components/ui';
import { colors, spacing, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { login, ApiError } from '../../lib/api';
import { useAuthStore } from '../../lib/auth';
import { isValidEmail } from '../../lib/validation';

export default function LoginScreen() {
  const { t } = useTranslation();
  const setSession = useAuthStore((s) => s.setSession);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => login(email.trim(), password),
    onSuccess: async (data) => {
      await setSession(data.access_token, data.user);
      if (router.canGoBack()) router.back();
      else router.replace('/(tabs)');
    },
  });

  const onSubmit = () => {
    setFieldError(null);
    if (!isValidEmail(email)) {
      setFieldError(t('auth.invalidEmail'));
      return;
    }
    if (!password) {
      setFieldError(t('auth.passwordRules'));
      return;
    }
    mutation.mutate();
  };

  const serverError =
    mutation.isError && mutation.error instanceof ApiError && mutation.error.status === 401
      ? t('login.failed')
      : mutation.isError
        ? t('common.errorGeneric')
        : null;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
      <ScreenContainer>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, flexGrow: 1, justifyContent: 'center' }}>
          <Text style={[typography.h1, { marginBottom: spacing.xs }]}>{t('login.title')}</Text>
          <Text style={[typography.bodyMuted, { marginBottom: spacing.xl }]}>{t('login.subtitle')}</Text>

          <TextField
            testID="login-email-input"
            label={t('auth.email')}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
          />
          <TextField
            testID="login-password-input"
            label={t('auth.password')}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="password"
          />
          {(fieldError || serverError) && (
            <Text style={{ color: colors.danger, marginBottom: spacing.md }}>{fieldError ?? serverError}</Text>
          )}

          <Button title={t('login.submit')} onPress={onSubmit} loading={mutation.isPending} />

          <Pressable onPress={() => router.push('/(auth)/forgot')} style={{ marginTop: spacing.lg, alignItems: 'center' }}>
            <Text style={{ color: colors.gold }}>{t('login.forgot')}</Text>
          </Pressable>

          <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: spacing.xl }}>
            <Text style={typography.bodyMuted}>{t('login.noAccount')} </Text>
            <Link href="/(auth)/register" replace>
              <Text style={{ color: colors.gold, fontWeight: '700' }}>{t('login.register')}</Text>
            </Link>
          </View>
        </ScrollView>
      </ScreenContainer>
    </KeyboardAvoidingView>
  );
}
