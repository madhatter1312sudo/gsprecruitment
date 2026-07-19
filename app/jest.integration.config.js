/**
 * API integration suite — hits the REAL production API
 * (https://api.gsprecruitment.nl/api), no mocks, no RN rendering. Kept
 * fully separate from the offline unit suite (jest.config.js / `npm test`)
 * so `npm test` never needs network access. Run with `npm run test:integration`.
 *
 * Deliberately does NOT use the `jest-expo` preset — these are plain
 * TypeScript + fetch tests with no React Native/JSX involved, so a
 * minimal Node + Babel-TypeScript transform keeps this suite fast and
 * decoupled from the RN test environment.
 */
module.exports = {
  testEnvironment: 'node',
  testMatch: ['<rootDir>/__tests__/integration/**/*.test.ts'],
  testTimeout: 30000,
  transform: {
    '^.+\\.tsx?$': [
      'babel-jest',
      {
        presets: [['@babel/preset-env', { targets: { node: 'current' } }], '@babel/preset-typescript'],
      },
    ],
  },
};
