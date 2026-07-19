/**
 * API integration suite — hits the REAL production API
 * (https://api.gsprecruitment.nl/api). Run with `npm run test:integration`.
 * NOT part of `npm test` (the offline unit suite) — see jest.integration.config.js.
 *
 * Registers a throwaway candidate account, exercises the public + authed
 * surface the app depends on, then soft-deletes the account via the GDPR
 * endpoint in `afterAll` so repeated runs don't pile up test users.
 */

const BASE_URL = 'https://api.gsprecruitment.nl/api';
const TEST_EMAIL = `app-tester+${Date.now()}@gsprecruitment.nl`;
const TEST_PASSWORD = 'Testpass1'; // meets both the client rule (upper+lower+digit, 8+) and the backend's min_length=8

let accessToken = '';

interface QuizItem {
  id: number;
  domain: string;
  difficulty: number;
  question: string;
  options: string[];
}

async function api(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

let quizItems: QuizItem[] = [];

describe('GSP Recruitment API integration (real network)', () => {
  beforeAll(async () => {
    const res = await api('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email: TEST_EMAIL,
        password: TEST_PASSWORD,
        full_name: 'App Integration Test',
        role: 'candidate',
      }),
    });
    if (!res.ok) {
      throw new Error(`Setup failed: register returned ${res.status}: ${await res.text()}`);
    }
    const data = await res.json();
    accessToken = data.access_token;
  });

  afterAll(async () => {
    if (!accessToken) return;
    try {
      await api('/v1/gdpr/account', { method: 'DELETE', headers: authHeader(accessToken) });
    } catch {
      // best-effort cleanup only
    }
  });

  test('register returned a bearer access token for the new candidate', () => {
    expect(accessToken).toEqual(expect.any(String));
    expect(accessToken.length).toBeGreaterThan(10);
  });

  test('login with the same credentials succeeds and returns the same user', async () => {
    const res = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
    });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.access_token).toEqual(expect.any(String));
    expect(data.user.email).toBe(TEST_EMAIL);
    accessToken = data.access_token; // use the freshest token for the rest of the suite
  });

  test('GET public/jobs returns at least 6 open jobs', async () => {
    const res = await api('/public/jobs');
    expect(res.status).toBe(200);
    const jobs = await res.json();
    expect(Array.isArray(jobs)).toBe(true);
    expect(jobs.length).toBeGreaterThanOrEqual(6);
    expect(jobs[0]).toEqual(expect.objectContaining({ id: expect.any(Number), title: expect.any(String) }));
  });

  test('GET public/quiz returns 12 balanced items with no answer key leaked', async () => {
    const res = await api('/v1/public/quiz?lang=nl');
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.lang).toBe('nl');
    expect(data.items).toHaveLength(12);
    quizItems = data.items;

    for (const item of data.items as QuizItem[]) {
      expect(typeof item.id).toBe('number');
      expect(typeof item.domain).toBe('string');
      expect(typeof item.difficulty).toBe('number');
      expect(typeof item.question).toBe('string');
      expect(Array.isArray(item.options)).toBe(true);
      expect(item.options.length).toBeGreaterThan(1);
      // The whole point of server-side grading: no answer/correct-index leak to the client.
      expect(item).not.toHaveProperty('correct_index');
      expect(item).not.toHaveProperty('answer');
      expect(item).not.toHaveProperty('answer_index');
      expect(item).not.toHaveProperty('correct');
      expect(item).not.toHaveProperty('explanation');
    }
  });

  test('POST public/quiz/submit grades the answers and returns score/tier/feedback', async () => {
    expect(quizItems.length).toBe(12);
    const answers = quizItems.map((q) => ({ question_id: q.id, answer_index: 0 }));
    const res = await api('/v1/public/quiz/submit?lang=nl', {
      method: 'POST',
      body: JSON.stringify({ answers }),
    });
    expect(res.status).toBe(200);
    const data = await res.json();

    expect(typeof data.score).toBe('number');
    expect(typeof data.max_score).toBe('number');
    expect(data.max_score).toBe(12);
    expect(typeof data.tier).toBe('string');
    expect(data.tier).toMatch(/indicatie/i); // "Junior-indicatie" | "Medior-indicatie" | "Senior-indicatie"

    expect(data.feedback).toHaveLength(12);
    for (const f of data.feedback) {
      expect(f).toEqual(
        expect.objectContaining({
          question_id: expect.any(Number),
          correct: expect.any(Boolean),
          correct_index: expect.any(Number),
          explanation: expect.any(String),
        }),
      );
    }
    expect(Object.keys(data.domain_scores).length).toBeGreaterThan(0);
  });

  test('GET candidate/matches (authenticated) returns 200', async () => {
    const res = await api('/v1/candidate/matches', { headers: authHeader(accessToken) });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data.items)).toBe(true);
  });

  test('GET gdpr/export (authenticated) returns 200 with this user\'s own record', async () => {
    const res = await api('/v1/gdpr/export', { headers: authHeader(accessToken) });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.user.email).toBe(TEST_EMAIL);
  });

  test('DELETE gdpr/account soft-deletes the throwaway test account', async () => {
    const res = await api('/v1/gdpr/account', { method: 'DELETE', headers: authHeader(accessToken) });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.message).toEqual(expect.any(String));
    accessToken = ''; // tell afterAll cleanup is already done
  });
});
