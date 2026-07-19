/**
 * GSP Recruitment design tokens.
 * Source of truth: website/styles.css (--navy / --gold custom properties).
 * The app is dark-mode only (navy background, gold accents) to match the
 * brand's live site theme; there is no light variant.
 */

export const colors = {
  navy: '#0E1B2E',
  navyLight: '#1C3252',
  navyMid: '#2A4A75',
  navyFaded: 'rgba(255,255,255,0.04)',

  gold: '#E8B400',
  goldDark: '#8A6B00',
  goldLight: 'rgba(232, 180, 0, 0.12)',
  goldGlow: 'rgba(232, 180, 0, 0.18)',

  white: '#FFFFFF',
  text: '#F3F6FA',
  textMuted: '#9FB0C3',
  textFaint: '#6B7C93',

  border: 'rgba(255,255,255,0.08)',
  borderStrong: 'rgba(255,255,255,0.16)',

  success: '#3DD68C',
  danger: '#E5484D',
  warning: '#F5A623',

  overlay: 'rgba(14,27,46,0.72)',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 18,
  xl: 24,
  pill: 999,
} as const;

export const typography = {
  h1: { fontSize: 28, fontWeight: '700' as const, color: colors.text },
  h2: { fontSize: 22, fontWeight: '700' as const, color: colors.text },
  h3: { fontSize: 18, fontWeight: '600' as const, color: colors.text },
  body: { fontSize: 15, fontWeight: '400' as const, color: colors.text },
  bodyMuted: { fontSize: 14, fontWeight: '400' as const, color: colors.textMuted },
  caption: { fontSize: 12, fontWeight: '500' as const, color: colors.textMuted },
  button: { fontSize: 15, fontWeight: '700' as const },
};

export const shadow = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 4,
  },
};
