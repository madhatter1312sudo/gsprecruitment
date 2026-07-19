/**
 * Minimal manual mock for `expo-router`, used by unit/component tests
 * (see jest.config.js `moduleNameMapper`). Screens are rendered in
 * isolation here (not through the real file-based router), so navigation
 * calls are just spies and `Link` renders its children without wiring up
 * real navigation.
 */
import React from 'react';
import { Pressable } from 'react-native';

export const router = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  canGoBack: jest.fn(() => false),
  setParams: jest.fn(),
};

export function Link({
  href,
  children,
  ...props
}: {
  href: string;
  children: React.ReactNode;
  [key: string]: unknown;
}) {
  return (
    <Pressable accessibilityRole="link" onPress={() => router.push(href)} {...props}>
      {children}
    </Pressable>
  );
}

export function useLocalSearchParams() {
  return {};
}

export function Stack({ children }: { children?: React.ReactNode }) {
  return <>{children}</>;
}
(Stack as any).Screen = function StackScreen() {
  return null;
};

export function Tabs({ children }: { children?: React.ReactNode }) {
  return <>{children}</>;
}
(Tabs as any).Screen = function TabsScreen() {
  return null;
};
