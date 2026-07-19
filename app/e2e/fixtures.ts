import { test as base, expect } from '@playwright/test';

const API_ORIGIN = 'https://api.gsprecruitment.nl/**';

/**
 * The exported web app is served from http://localhost:4173 in this suite,
 * but the production API's CORS allow-list only covers the real site
 * origins — not localhost. Rather than mock the app's data (defeating the
 * point of an e2e run against the live backend), every test intercepts API
 * requests at the network layer and re-fulfills them with the real
 * response plus an `access-control-allow-origin` header, and answers CORS
 * preflight OPTIONS requests directly. This is a test-harness shim only; it
 * changes nothing about how the app talks to the API.
 */
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route(API_ORIGIN, async (route) => {
      const request = route.request();
      if (request.method() === 'OPTIONS') {
        await route.fulfill({
          status: 204,
          headers: {
            'access-control-allow-origin': '*',
            'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
            'access-control-allow-headers': 'content-type,authorization',
          },
          body: '',
        });
        return;
      }
      const response = await route.fetch();
      const body = await response.body();
      await route.fulfill({
        status: response.status(),
        headers: { ...response.headers(), 'access-control-allow-origin': '*' },
        body,
      });
    });
    await use(page);
  },
});

export { expect };
