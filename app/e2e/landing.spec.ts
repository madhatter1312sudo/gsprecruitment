import { test, expect } from './fixtures';

test.describe('Landing / jobs feed', () => {
  test('renders the jobs feed with 6 jobs', async ({ page }) => {
    await page.goto('/');
    const cards = page.locator('[data-testid="job-card"]');
    await expect(cards.first()).toBeVisible({ timeout: 15_000 });
    await expect(cards).toHaveCount(6);
  });

  test('opens a job detail screen from the feed', async ({ page }) => {
    await page.goto('/');
    const cards = page.locator('[data-testid="job-card"]');
    await expect(cards.first()).toBeVisible({ timeout: 15_000 });

    await cards.first().click();

    await expect(page).toHaveURL(/\/job\/\d+/);
    // The job detail screen renders its own section headers not present on the feed.
    await expect(page.getByText('Over de functie')).toBeVisible();
    await expect(page.getByText('Wat we vragen')).toBeVisible();
  });
});
