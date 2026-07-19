import { useEffect, useState, useCallback } from 'react';
import { View } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as SplashScreen from 'expo-splash-screen';
import { useAuthStore } from '../lib/auth';
import { useLanguageStore } from '../lib/i18n';
import { colors } from '../lib/theme';

SplashScreen.preventAutoHideAsync().catch(() => {});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function RootLayout() {
  const hydrateAuth = useAuthStore((s) => s.hydrate);
  const hydrateLang = useLanguageStore((s) => s.hydrate);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    Promise.all([hydrateAuth(), hydrateLang()]).finally(() => setReady(true));
  }, [hydrateAuth, hydrateLang]);

  const onLayout = useCallback(async () => {
    if (ready) await SplashScreen.hideAsync().catch(() => {});
  }, [ready]);

  if (!ready) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <View style={{ flex: 1, backgroundColor: colors.navy }} onLayout={onLayout}>
            <StatusBar style="light" />
            <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.navy } }}>
              <Stack.Screen name="(tabs)" />
              <Stack.Screen name="(auth)" options={{ presentation: 'modal' }} />
              <Stack.Screen
                name="job/[id]"
                options={{
                  headerShown: true,
                  headerTitle: '',
                  headerStyle: { backgroundColor: colors.navy },
                  headerTintColor: colors.gold,
                  headerShadowVisible: false,
                }}
              />
            </Stack>
          </View>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
