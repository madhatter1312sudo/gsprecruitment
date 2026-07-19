import { Stack } from 'expo-router';
import { colors } from '../../lib/theme';

export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: true,
        headerStyle: { backgroundColor: colors.navy },
        headerTintColor: colors.gold,
        headerTitleStyle: { color: colors.text },
        headerShadowVisible: false,
        contentStyle: { backgroundColor: colors.navy },
      }}
    >
      <Stack.Screen name="login" options={{ title: '' }} />
      <Stack.Screen name="register" options={{ title: '' }} />
      <Stack.Screen name="forgot" options={{ title: '' }} />
    </Stack>
  );
}
