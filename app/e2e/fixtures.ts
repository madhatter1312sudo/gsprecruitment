import { test as base, expect } from '@playwright/test';

const API_ORIGIN = 'https://api.gsprecruitment.nl/**';
const PUBLIC_JOBS_URL = 'https://api.gsprecruitment.nl/api/public/jobs';

/**
 * The exported web app is served from http://localhost:4173 in this suite,
 * but the production API's CORS allow-list only covers the real site
 * origins — not localhost. Rather than mock the app's data (defeating the
 * point of an e2e run against the live backend), every test intercepts API
 * requests at the network layer and re-fulfills them with the real
 * response plus an `access-control-allow-origin` header, and answers CORS
 * preflight OPTIONS requests directly. This is a test-harness shim only; it
 * changes nothing about how the app talks to the API.
 *
 * The one deliberate exception is `GET /api/public/jobs`: since WS-C.15 the
 * public board excludes the 6 `is_demo` seed rows from migrations/012
 * (`routers/jobs.py` `list_public_jobs`), and production currently has no
 * real open job order, so the live endpoint returns `[]`. A feed test that
 * hit the real endpoint would therefore be asserting on the sales pipeline
 * (is there an open opdracht today?) rather than on the app. `MOCK_JOBS`
 * below is fixed, fictional data shaped exactly like a real row
 * (`PUBLIC_JOB_COLUMNS` / `_public_job_row` in `routers/jobs.py`) so the
 * jobs-feed tests stay deterministic. Every other endpoint (quiz, login,
 * salary, ...) is left live via the general shim, which is the actual value
 * of this suite.
 */

/** Shaped exactly like a row `_public_job_row()` returns: every
 * `PUBLIC_JOB_COLUMNS` field, with `company_display` already normalized to
 * "confidential" the way GSP's faceless-agency rows always render, and
 * `employment_type` drawn from the values the CHECK constraint in
 * `migrations/016_job_orders_columns.py` actually allows ('vast' |
 * 'detachering' | 'interim'), so a screen that starts rendering this field
 * is exercised against a value production can really return. */
export const MOCK_JOBS = [
  {
    id: 900001,
    title: 'Embedded Software Engineer (C++)',
    department: 'Embedded software',
    seniority: 'senior',
    location_type: 'hybrid',
    city: 'Eindhoven',
    salary_min: 5200,
    salary_max: 6800,
    salary_currency: 'EUR',
    description: 'Testfixture-vacature voor de e2e-suite: ontwikkeling van embedded C++ software voor een industrieel platform.',
    requirements: 'Testfixture-vacature: ervaring met C++17, RTOS en hardware-nabije software.',
    nice_to_have: 'Testfixture-vacature: ervaring met Yocto of Buildroot.',
    status: 'open',
    urgency: 'normal',
    created_at: '2026-08-01T09:00:00Z',
    company_display: 'confidential',
    employment_type: 'vast',
    sponsorship_possible: false,
  },
  {
    id: 900002,
    title: 'Mechatronica Engineer',
    department: 'Mechatronica en besturingssoftware',
    seniority: 'mid',
    location_type: 'onsite',
    city: 'Eindhoven',
    salary_min: 4200,
    salary_max: 5400,
    salary_currency: 'EUR',
    description: 'Testfixture-vacature voor de e2e-suite: ontwerp en besturingssoftware voor mechatronische systemen.',
    requirements: 'Testfixture-vacature: ervaring met bewegingsbesturing en PLC/motion control.',
    nice_to_have: 'Testfixture-vacature: kennis van MATLAB/Simulink.',
    status: 'open',
    urgency: 'high',
    created_at: '2026-08-05T09:00:00Z',
    company_display: 'confidential',
    employment_type: 'detachering',
    sponsorship_possible: true,
  },
  {
    id: 900003,
    title: 'OT-Cybersecurity Engineer',
    department: 'OT-cybersecurity',
    seniority: 'lead',
    location_type: 'remote',
    city: null,
    salary_min: 6000,
    salary_max: 7800,
    salary_currency: 'EUR',
    description: 'Testfixture-vacature voor de e2e-suite: beveiliging van operationele technologie-omgevingen.',
    requirements: 'Testfixture-vacature: ervaring met IEC 62443 en industriële netwerken.',
    nice_to_have: null,
    status: 'open',
    urgency: 'normal',
    created_at: '2026-08-10T09:00:00Z',
    company_display: 'confidential',
    employment_type: 'interim',
    sponsorship_possible: false,
  },
];

async function fulfillFromRealApi(route: import('@playwright/test').Route) {
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
}

async function fulfillJson(route: import('@playwright/test').Route, data: unknown) {
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
  await route.fulfill({
    status: 200,
    headers: { 'access-control-allow-origin': '*', 'content-type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route(API_ORIGIN, fulfillFromRealApi);
    await use(page);
  },
});

/**
 * Same CORS shim as `test`, but `GET /api/public/jobs` is answered with the
 * fixed `MOCK_JOBS` list instead of the live endpoint. Every other request
 * (quiz, login, salary, ...) still goes to the real production API. Use
 * this for jobs-feed tests that need a deterministic, non-empty board.
 */
export const testWithMockJobs = base.extend({
  page: async ({ page }, use) => {
    await page.route(API_ORIGIN, fulfillFromRealApi);
    await page.route(PUBLIC_JOBS_URL, (route) => fulfillJson(route, MOCK_JOBS));
    await use(page);
  },
});

/**
 * Same CORS shim as `test`, but `GET /api/public/jobs` is answered with an
 * empty list, for exercising the feed's empty state deterministically.
 */
export const testWithEmptyJobs = base.extend({
  page: async ({ page }, use) => {
    await page.route(API_ORIGIN, fulfillFromRealApi);
    await page.route(PUBLIC_JOBS_URL, (route) => fulfillJson(route, []));
    await use(page);
  },
});

export { expect };
