import { test, expect, type Page } from '@playwright/test';
import { credentials, setOwnerLocale } from './support/api';

async function signInUi(page: Page): Promise<void> {
  const creds = credentials();
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', creds.ownerEmail);
  await page.fill('input[formControlName="password"]', creds.ownerPassword);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

test.describe('Catalogue refresh review (R3.4)', () => {
  test('loads the tenant-scoped review queue and preserves preview fields', async ({ page }) => {
    // The shared owner account's locale is persisted server-side, so an Arabic-switching spec
    // that runs earlier in the suite leaks into this English-only assertion unless reset here.
    await setOwnerLocale('en');
    await signInUi(page);
    await page.goto('/matching?status=all');
    await expect(page.locator('.page-title')).toContainText('Match Resolution Queue');

    const reviewSection = page.locator('[data-testid="refresh-review-section"]');
    await expect(reviewSection).toBeVisible({ timeout: 15_000 });

    const reviewItems = page.locator('[data-testid="refresh-review-item"]');
    if ((await reviewItems.count()) === 0) {
      await expect(page.locator('.error-banner')).toHaveCount(0);
      await expect(reviewSection).toContainText('No catalogue refreshes are awaiting review.');
      return;
    }

    const firstReview = reviewItems.first();
    await expect(firstReview).toContainText('rows');
    await expect(firstReview).toContainText('errors');
    await expect(firstReview.locator('.refresh-preview-row').first()).toBeVisible();
    await expect(firstReview.locator('.refresh-review-actions')).toContainText('Approve refresh');
    await expect(firstReview.locator('.refresh-review-actions')).toContainText('Reject refresh');
  });
});
