import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * End-to-End test suite for Quotation Upload and Extraction (T037, US1, FR-001, FR-004, FR-018, SC-001).
 *
 * Requirements:
 * - FR-001: Direct upload of PDF, image, CSV, Excel.
 * - FR-004: Refuse unsupported file format immediately client-side.
 * - FR-018: Asynchronous job polling for extraction.
 */
test.describe('Quotation Upload & Extraction (T037, US1)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('upload unsupported file format, assert immediate client-side rejection', async ({ page }) => {
    await page.goto('/quotations/upload');
    await expect(page.locator('.page-title')).toContainText('Upload Supplier Quotation');

    const invalidContent = 'This is an unsupported text file.';
    await page.setInputFiles('input.file-input', {
      name: 'unsupported_document.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from(invalidContent),
    });

    // Assert error message shown immediately
    await expect(page.locator('.error-banner')).toBeVisible();
    await expect(page.locator('.error-text')).toContainText('Unsupported file format');

    // Assert upload button is not visible
    await expect(page.locator('.start-upload-btn')).not.toBeVisible();
  });

  test('upload valid quotation file, trigger extraction, and transition to extracted state', async ({ page }) => {
    await page.goto('/quotations/upload');
    await expect(page.locator('.page-title')).toContainText('Upload Supplier Quotation');

    // Create a mock PDF buffer
    const validPdfContent = '%PDF-1.4\n1 0 obj\n<< /Title (Quotation) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF';

    await page.setInputFiles('input.file-input', {
      name: 'supplier_quotation.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(validPdfContent),
    });

    // Verify selected file card
    await expect(page.locator('.selected-file-card')).toBeVisible();
    await expect(page.locator('.file-name')).toContainText('supplier_quotation.pdf');

    // Click upload and extract
    await page.click('.start-upload-btn');

    // Expect progress container or result container
    await expect(
      page.locator('.progress-container, .result-container.success')
    ).toBeVisible();

    // Eventually transition to extracted state. Generous: under full-suite CI load, a single
    // real RQ worker can have a backlog from every earlier upload in the run.
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 90000 });
    await expect(page.locator('.result-title')).toContainText('Extraction completed successfully');

    // Proceed to review link
    const reviewLink = page.locator('a:has-text("Proceed to Review")');
    await expect(reviewLink).toBeVisible();
    await reviewLink.click();
    await page.waitForURL('**/quotations/**/review');
  });
});
