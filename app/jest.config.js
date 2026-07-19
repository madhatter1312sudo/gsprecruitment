/**
 * Unit test config — jest-expo preset (React Native environment + Babel
 * transform for TS/TSX), @testing-library/react-native for component
 * tests. Runs fully offline: no real network calls (see
 * jest.integration.config.js for the suite that hits the real API).
 */
module.exports = {
  preset: 'jest-expo',
  testTimeout: 15000,
  testMatch: ['<rootDir>/__tests__/unit/**/*.test.{ts,tsx}'],
  setupFiles: ['<rootDir>/__tests__/jest.setup.ts'],
  moduleNameMapper: {
    '^expo-router$': '<rootDir>/__tests__/__mocks__/expo-router.tsx',
    '^expo-secure-store$': '<rootDir>/__tests__/__mocks__/expo-secure-store.ts',
  },
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules-.*|sentry-expo|native-base|react-native-svg)',
  ],
  collectCoverageFrom: ['lib/**/*.{ts,tsx}', 'components/**/*.{ts,tsx}'],
};
