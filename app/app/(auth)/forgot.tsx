import React, { useState } from 'react';
import { Text, ScrollView, KeyboardAvoidingView, Platform, Pressable } from 'react-native';
import { router } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { ScreenContainer, TextField, Button } from '../../components/ui';
import { colors, spacing, typography } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';
import { forgotPassword } from '../../lib/api';
import { isValidEmail } from '../../lib/validation';

export default function ForgotPasswordScreen() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);

  const mutation = useMutation({ mutationFn: () => forgotPassword(email.trim()) });

  const onSubmit = () => {
    setFieldError(null);
    if (!isValidEmail(email)) {
      setFieldError(t('auth.invalidEmail'));
      return;
    }
    mutation.mutate();
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
      <ScreenContainer>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, flexGrow: 1, justifyContent: 'center' }}>
          <Text style={[typography.h1, { marginBottom: spacing.xs }]}>{t('forgot.title')}</Text>
          <Text style={[typography.bodyMuted, { marginBottom: spacing.xl }]}>{t('forgot.subtitle')}</Text>

          {mutation.isSuccess ? (
            <Text style={{ color: colors.success, marginBottom: spacing.lg }}>{t('forgot.success')}</Text>
          ) : (
            <>
              <TextField
                label={t('auth.email')}
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                keyboardType="email-address"
              />
              {fieldError && <Text style={{ color: colors.danger, marginBottom: spacing.md }}>{fieldError}</Text>}
              <Button title={t('forgot.submit')} onPress={onSubmit} loading={mutation.isPending} />
            </>
          )}

          <Pressable onPress={() => router.back()} style={{ marginTop: spacing.xl, alignItems: 'center' }}>
            <Text style={{ color: colors.gold }}>{t('forgot.backToLogin')}</Text>
          </Pressable>
        </ScrollView>
      </ScreenContainer>
    </KeyboardAvoidingView>
  );
}
