import { test, expect } from './fixtures';

test.describe('Login screen validation', () => {
  test('rejects an invalid email without calling the API', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByText('Welkom terug')).toBeVisible();

    await page.locator('[data-testid="login-email-input"]').fill('not-an-email');
    await page.getByText('Inloggen').click();

    await expect(page.getByText('Vul een geldig e-mailadres in.')).toBeVisible();
  });

  test('requires a password once the email is valid', async ({ page }) => {
    await page.goto('/login');
    await page.locator('[data-testid="login-email-input"]').fill('someone@example.com');
    await page.getByText('Inloggen').click();

    await expect(page.getByText('Minimaal 8 tekens, met een hoofdletter, kleine letter en cijfer.')).toBeVisible();
  });

  test('shows the incorrect-credentials error for a wrong password against the real API', async ({ page }) => {
    await page.goto('/login');
    await page.locator('[data-testid="login-email-input"]').fill('nonexistent-user@gsprecruitment.nl');
    await page.locator('[data-testid="login-password-input"]').fill('DefinitelyWrong1');
    await page.getByText('Inloggen').click();

    await expect(page.getByText('Onjuist e-mailadres of wachtwoord.')).toBeVisible({ timeout: 10_000 });
  });
});
