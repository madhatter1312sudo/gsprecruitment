import { defineConfig, devices } from '@playwright/test';

/**
 * E2E suite against the static web export (`npx expo export --platform web`
 * -> dist/), served locally and driven by real Chromium. The exported app
 * still talks to the REAL production API (api.gsprecruitment.nl) — there is
 * no mocking of app data, only a CORS shim (see e2e/fixtures.ts) because the
 * backend's CORS allow-list is scoped to the real site origins, not
 * localhost. Run with `npm run test:e2e`.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npx serve -l 4173 -s dist',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
