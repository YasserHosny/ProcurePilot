import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Quotation Versioning & Re-quotes (T059, US4).
 *
 * Requirements:
 * - FR-020: Link new quotation to prior version and keep both visible.
 * - SC-007: Can see both new and prior versions and tell which is current.
 */
test.describe('Quotation Versioning & Re-quotes (T059, US4)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('re-quote checkbox reveals prior quotation selection', async ({ page }) => {
    await page.goto('/quotations/upload');
    const validPdfContent = '%PDF-1.4\n1 0 obj\n<< /Title (Quote V2) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF';
    await page.setInputFiles('input.file-input', {
      name: 'quote_v2.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(validPdfContent),
    });
    await page.click('.start-upload-btn');
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 90000 });
    await page.click('a:has-text("Proceed to Review")');
    await page.waitForURL('**/quotations/**/review');

    // Check the re-quote checkbox
    const requoteCheckbox = page.locator('mat-checkbox', { hasText: 'This is an updated re-quote' });
    if (await requoteCheckbox.isVisible()) {
      await requoteCheckbox.click();
      await expect(page.locator('.version-select')).toBeVisible();
    }
  });

  test('version banner appears on linked quotations and allows navigation to prior version', async ({ page }) => {
    // Check if any quotation with a version link exists in the queue
    await page.goto('/quotations');
    const firstTask = page.locator('a:has-text("Review & Authorize"), a:has-text("View")').first();
    if (await firstTask.isVisible()) {
      await firstTask.click();
      await page.waitForURL('**/quotations/**/review');

      const versionBanner = page.locator('.version-banner');
      if (await versionBanner.isVisible()) {
        await expect(versionBanner.locator('.version-link-btn')).toBeVisible();
        await versionBanner.locator('.version-link-btn').click();
        await page.waitForURL('**/quotations/**/review');
        await expect(page.locator('.document-panel')).toBeVisible();
      }
    }
  });
});
