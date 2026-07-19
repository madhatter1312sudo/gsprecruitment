import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import QuizScreen from '../../app/(tabs)/quiz';
import * as api from '../../lib/api';
import { useAuthStore } from '../../lib/auth';
import { useLanguageStore } from '../../lib/i18n';
import type { QuizListResponse, QuizSubmitResponse } from '../../lib/api';

jest.mock('../../lib/api', () => {
  const actual = jest.requireActual('../../lib/api');
  return { ...actual, getQuiz: jest.fn(), submitQuiz: jest.fn(), submitLead: jest.fn() };
});

jest.setTimeout(20000);

const mockQuiz: QuizListResponse = {
  lang: 'nl',
  items: [
    { id: 1, domain: 'security', difficulty: 1, question: 'Vraag over security?', options: ['Fout antwoord', 'Goed antwoord'] },
    { id: 2, domain: 'cloud_devops', difficulty: 2, question: 'Vraag over devops?', options: ['Fout antwoord', 'Goed antwoord'] },
    { id: 3, domain: 'general_swe', difficulty: 3, question: 'Vraag over swe?', options: ['Goed antwoord', 'Fout antwoord'] },
  ],
};

const mockSubmitResult: QuizSubmitResponse = {
  score: 2,
  max_score: 3,
  tier: 'Medior-indicatie',
  domain_scores: {
    security: { correct: 1, total: 1 },
    cloud_devops: { correct: 0, total: 1 },
    general_swe: { correct: 1, total: 1 },
  },
  feedback: [
    { question_id: 1, correct: true, correct_index: 1, explanation: 'Uitleg vraag 1' },
    { question_id: 2, correct: false, correct_index: 1, explanation: 'Uitleg vraag 2' },
    { question_id: 3, correct: true, correct_index: 0, explanation: 'Uitleg vraag 3' },
  ],
};

function renderQuiz() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuizScreen />
    </QueryClientProvider>,
  );
}

describe('Quiz flow (server-graded, mocked API)', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    await useAuthStore.getState().logout();
    useLanguageStore.getState().setLang('nl');
    (api.getQuiz as jest.Mock).mockResolvedValue(mockQuiz);
    (api.submitQuiz as jest.Mock).mockResolvedValue(mockSubmitResult);
  });

  it('fetches questions, walks through all of them and renders the server result', async () => {
    await renderQuiz();

    // Intro screen: waits for the quiz to load before enabling "start".
    await waitFor(() => expect(api.getQuiz).toHaveBeenCalledWith('nl'));
    const startButton = await screen.findByText('Start de quiz');
    await fireEvent.press(startButton);

    // Answer all 3 mocked questions (always pick the second option = "Goed antwoord" for q1/q2, first for q3).
    await screen.findByText('Vraag over security?');
    await fireEvent.press(screen.getByText('Goed antwoord'));

    await screen.findByText('Vraag over devops?');
    await fireEvent.press(screen.getAllByText('Fout antwoord')[0]);

    await screen.findByText('Vraag over swe?');
    await fireEvent.press(screen.getAllByText('Goed antwoord')[0]);

    // Anonymous user -> optional email interstitial before submitting.
    await screen.findByText('Resultaat aan je e-mail koppelen?');
    await fireEvent.press(screen.getByText('Overslaan'));

    await waitFor(() =>
      expect(api.submitQuiz).toHaveBeenCalledWith(
        {
          answers: [
            { question_id: 1, answer_index: 1 },
            { question_id: 2, answer_index: 0 },
            { question_id: 3, answer_index: 0 },
          ],
          email: undefined,
        },
        'nl',
      ),
    );

    // Result screen renders the server's tier text verbatim, the score, and per-question feedback.
    expect(await screen.findByText('Medior-indicatie')).toBeTruthy();
    expect(screen.getByText('2 / 3')).toBeTruthy();
    expect(screen.getByText('Uitleg vraag 1')).toBeTruthy();
    expect(screen.getByText('Uitleg vraag 2')).toBeTruthy();
    expect(screen.getByText('Uitleg vraag 3')).toBeTruthy();
  });

  it('falls back to the offline quiz when the server fetch fails', async () => {
    (api.getQuiz as jest.Mock).mockRejectedValue(new Error('network down'));
    await renderQuiz();

    // useQuizQuery retries once before surfacing the error, so allow extra time.
    await screen.findByText('De quizvragen konden niet worden geladen.', {}, { timeout: 10000 });
    await fireEvent.press(screen.getByText('Ga verder met de offline versie'));

    // The offline bank's first question should now render.
    expect(await screen.findByText('Offline versie')).toBeTruthy();
  });

  it('submits the authenticated user\'s email automatically, skipping the email interstitial', async () => {
    await useAuthStore.getState().setSession('tok', {
      id: 1,
      email: 'candidate@example.com',
      full_name: 'Cand Idate',
      role: 'candidate',
      is_verified: true,
    });
    await renderQuiz();

    const startButton = await screen.findByText('Start de quiz');
    await fireEvent.press(startButton);

    await screen.findByText('Vraag over security?');
    await fireEvent.press(screen.getByText('Goed antwoord'));
    await screen.findByText('Vraag over devops?');
    await fireEvent.press(screen.getAllByText('Fout antwoord')[0]);
    await screen.findByText('Vraag over swe?');
    await fireEvent.press(screen.getAllByText('Goed antwoord')[0]);

    await waitFor(() =>
      expect(api.submitQuiz).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'candidate@example.com' }),
        'nl',
      ),
    );
    expect(await screen.findByText('Medior-indicatie')).toBeTruthy();
  });
});
