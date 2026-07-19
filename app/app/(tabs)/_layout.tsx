import React from 'react';
import { Text, type ColorValue } from 'react-native';
import { Tabs } from 'expo-router';
import { colors } from '../../lib/theme';
import { useTranslation } from '../../lib/i18n';

function TabIcon({ glyph, color }: { glyph: string; color: ColorValue }) {
  return <Text style={{ fontSize: 20, color }}>{glyph}</Text>;
}

export default function TabsLayout() {
  const { t } = useTranslation();

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.navy },
        headerTintColor: colors.text,
        headerShadowVisible: false,
        headerTitleStyle: { fontWeight: '700' },
        tabBarStyle: { backgroundColor: colors.navyLight, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.gold,
        tabBarInactiveTintColor: colors.textFaint,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t('tabs.jobs'),
          tabBarIcon: ({ color }) => <TabIcon glyph="💼" color={color} />,
        }}
      />
      <Tabs.Screen
        name="matches"
        options={{
          title: t('tabs.matches'),
          tabBarIcon: ({ color }) => <TabIcon glyph="🎯" color={color} />,
        }}
      />
      <Tabs.Screen
        name="quiz"
        options={{
          title: t('tabs.quiz'),
          tabBarIcon: ({ color }) => <TabIcon glyph="🧩" color={color} />,
        }}
      />
      <Tabs.Screen
        name="career"
        options={{
          title: t('tabs.career'),
          tabBarIcon: ({ color }) => <TabIcon glyph="📈" color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t('tabs.profile'),
          tabBarIcon: ({ color }) => <TabIcon glyph="👤" color={color} />,
        }}
      />
    </Tabs>
  );
}
