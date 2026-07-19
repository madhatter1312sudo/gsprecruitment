import { test, expect } from './fixtures';

test.describe('Quiz (server-graded)', () => {
  test('start -> answer 12 questions -> results show a tier badge', async ({ page }) => {
    await page.goto('/quiz');
    await expect(page.getByText('Tech Match Quiz')).toBeVisible();

    const startButton = page.getByText('Start de quiz');
    await expect(startButton).toBeVisible({ timeout: 15_000 });
    await startButton.click();

    // The 12 questions are drawn from a larger randomized pool, so option
    // text isn't predictable — always pick the first option via its
    // testID (added specifically so e2e doesn't depend on question content).
    for (let i = 0; i < 12; i++) {
      await expect(page.getByText(`Vraag ${i + 1} van 12`)).toBeVisible({ timeout: 10_000 });
      await page.locator('[data-testid="quiz-option-0"]').first().click();
    }

    // Anonymous session -> optional "link this to your email" interstitial before the server grades it.
    await expect(page.getByText('Resultaat aan je e-mail koppelen?')).toBeVisible({ timeout: 10_000 });
    await page.getByText('Overslaan').click();

    // Server response renders a tier badge ("Junior/Medior/Senior-indicatie").
    await expect(page.getByText(/indicatie/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Per vakgebied')).toBeVisible();
    await expect(page.getByText('Per vraag')).toBeVisible();
  });
});
