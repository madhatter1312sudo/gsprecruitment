import { testWithMockJobs, testWithEmptyJobs, expect } from './fixtures';

testWithMockJobs.describe('Landing / jobs feed', () => {
  testWithMockJobs('renders the jobs feed with the stubbed jobs', async ({ page }) => {
    await page.goto('/');
    const cards = page.locator('[data-testid="job-card"]');
    await expect(cards.first()).toBeVisible({ timeout: 15_000 });
    await expect(cards).toHaveCount(3);
  });

  testWithMockJobs('opens a job detail screen from the feed', async ({ page }) => {
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

testWithEmptyJobs.describe('Landing / jobs feed (empty)', () => {
  testWithEmptyJobs('shows the empty state when there are no open jobs, without crashing', async ({ page }) => {
    await page.goto('/');
    const cards = page.locator('[data-testid="job-card"]');
    await expect(page.getByText('Op dit moment geen open vacatures. Kom snel terug.')).toBeVisible({ timeout: 15_000 });
    await expect(cards).toHaveCount(0);
  });
});
