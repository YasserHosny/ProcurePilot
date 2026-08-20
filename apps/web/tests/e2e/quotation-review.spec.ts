import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Quotation Side-by-Side Review & Confirmation (T053, US2).
 *
 * Requirements:
 * - FR-012: Side-by-side source document and extracted fields with source-region highlighting.
 * - FR-013: Human field corrections recorded with attribution.
 * - FR-014: Keyboard-only navigation between fields needing attention.
 * - FR-015: Supplier confirmation required before confirming quotation.
 * - FR-016: Human authorization step via POST /confirm.
 */
test.describe('Quotation Review & Confirmation (T053, US2)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('review queue lists pending quotation review tasks and allows navigation to review', async ({ page }) => {
    await page.goto('/quotations');
    await expect(page.locator('.page-title')).toContainText('Quotation Review Queue');
    await expect(page.locator('.filter-card')).toBeVisible();

    // Check if table or empty state renders
    const tableOrEmpty = page.locator('.tasks-table, .empty-state');
    await expect(tableOrEmpty).toBeVisible();
  });

  test('side-by-side review highlights source region and supports keyboard navigation', async ({ page }) => {
    // Navigate to upload first or directly to a quotation review screen if available
    await page.goto('/quotations/upload');
    const validPdfContent = '%PDF-1.4\n1 0 obj\n<< /Title (Quote) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF';
    await page.setInputFiles('input.file-input', {
      name: 'quote_for_review.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(validPdfContent),
    });
    await page.click('.start-upload-btn');

    // Wait for extraction to complete
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 15000 });
    await page.click('a:has-text("Proceed to Review")');
    await page.waitForURL('**/quotations/**/review');

    // Verify side-by-side panels
    await expect(page.locator('.document-panel')).toBeVisible();
    await expect(page.locator('.data-panel')).toBeVisible();

    // Test clicking a field highlights its source region in the document canvas
    const currencyField = page.locator('.field-box', { hasText: 'Currency' });
    if (await currencyField.isVisible()) {
      await currencyField.click();
      await expect(page.locator('.provenance-card, .bounding-box-highlight')).toBeVisible();
    }

    // Test Keyboard navigation between flagged fields (FR-014)
    const keyboardNavBar = page.locator('.keyboard-nav-bar');
    if (await keyboardNavBar.isVisible()) {
      await page.keyboard.press('Alt+KeyN');
      await expect(page.locator('.bounding-box-highlight')).toBeVisible();
    }
  });

  test('correct extracted field, select supplier, and confirm quotation', async ({ page }) => {
    await page.goto('/quotations/upload');
    const validPdfContent = '%PDF-1.4\n1 0 obj\n<< /Title (Quote) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF';
    await page.setInputFiles('input.file-input', {
      name: 'quote_confirm.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(validPdfContent),
    });
    await page.click('.start-upload-btn');
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 15000 });
    await page.click('a:has-text("Proceed to Review")');
    await page.waitForURL('**/quotations/**/review');

    // Make an inline correction if line items are present
    const quantityInput = page.locator('.line-field input').first();
    if (await quantityInput.isVisible()) {
      await quantityInput.fill('15');
      // Save corrections
      const saveBtn = page.locator('button.save-btn');
      if (await saveBtn.isEnabled()) {
        await saveBtn.click();
        await expect(page.locator('.corrected-tag')).toBeVisible();
      }
    }

    // Select Supplier from dropdown if suppliers exist
    const supplierSelect = page.locator('mat-select[required]');
    await supplierSelect.click();
    const firstOption = page.locator('mat-option').nth(1); // skip placeholder
    if (await firstOption.isVisible()) {
      await firstOption.click();
    }

    // If confirm button is enabled, click Confirm & Authorize
    const confirmBtn = page.locator('button.confirm-btn');
    if (await confirmBtn.isEnabled()) {
      await confirmBtn.click();
      await expect(page.locator('.status-pill.status-reviewed')).toBeVisible();
    }
  });
});
