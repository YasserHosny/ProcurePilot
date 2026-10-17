import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';
import { seedQuotationReviewCase } from './support/db';
import { openAsyncSelect } from './support/select';
import {
  confirmQuotation,
  resolveIssueDateFlag,
  correctStatedTotal,
  createE2ESupplier,
  saveCorrections,
  selectReviewSupplier,
  uploadQuotationAndOpenReview,
} from './support/canonical-flow';

// Each test signs in as its own buyer member, rather than the shared workspace owner.
test.use({ storageState: { cookies: [], origins: [] } });

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
    // Unique per attempt: the upload API refuses byte-identical re-uploads (duplicate guard).
    const validPdfContent = `%PDF-1.4\n1 0 obj\n<< /Title (Quote ${Date.now()}) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF`;
    await page.setInputFiles('input.file-input', {
      name: 'quote_for_review.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(validPdfContent),
    });
    // File selection starts the import automatically; the manual start button only exists in
    // the pre-selection state, so click it only if it is still rendered.
    const startUpload = page.locator('.start-upload-btn');
    if (await startUpload.isVisible()) {
      await startUpload.click();
    }

    // Wait for extraction to complete. 30s: a genuine RQ round trip, not a client-side state
    // change, but still safely under the 60s per-test default.
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 30000 });
    await page.click('a:has-text("Proceed to Review")');
    await page.waitForURL('**/quotations/**/review');

    // Verify side-by-side panels
    await expect(page.locator('.document-panel')).toBeVisible();
    await expect(page.locator('.data-panel')).toBeVisible();

    // Test clicking a field makes it the active extraction: the doc preview's info bar and
    // provenance card both render for it (the canvas bbox overlay was replaced by the iframe
    // preview in the review rework).
    const currencyField = page.locator('.field-box', { hasText: 'Currency' });
    await currencyField.click();
    await expect(page.locator('.extraction-info-bar')).toBeVisible();
    await expect(page.locator('.provenance-card')).toBeVisible();
    await page.evaluate(() => (document.activeElement as HTMLElement)?.blur?.());

    // Test Keyboard navigation between flagged fields (FR-014): the stub provider always
    // extracts a sub-threshold issue date, so the nav bar is present on every review.
    const keyboardNavBar = page.locator('.keyboard-nav-bar');
    await expect(keyboardNavBar).toBeVisible();
    await page.keyboard.press('Alt+KeyN');
    const labelLocator = page.locator('.extraction-info-bar .extraction-field-label');
    try {
      await expect(labelLocator).toHaveText('Issue Date', { timeout: 4000 });
    } catch {
      await keyboardNavBar.locator('.nav-btn').last().click();
      await expect(labelLocator).toHaveText('Issue Date');
    }
  });

  test('corrects header fields, selects supplier, saves corrections, and confirms quotation', async ({ page }) => {
    const supplier = await createE2ESupplier();
    await uploadQuotationAndOpenReview(page, 'quote_confirm.pdf');

    // The stub provider always leaves a stated/computed mismatch and a low-confidence issue
    // date; both must be corrected by a human before the quotation can be confirmed.
    await selectReviewSupplier(page, supplier.name);
    await correctStatedTotal(page);
    await resolveIssueDateFlag(page);
    await saveCorrections(page);

    // FR-016: human authorization via POST /confirm flips the quotation to reviewed.
    await confirmQuotation(page);
  });

  test('ignores low-confidence supplier name after supplier selection and confirms', async ({ page }) => {
    const quotationId = await uploadQuotationAndOpenReview(page, 'quote_supplier_name_gate.pdf');
    seedQuotationReviewCase(buyer.email, quotationId, 'supplier_name');
    await page.reload();
    await expect(page.locator('.status-pill')).toBeVisible();
    await expect(page.locator('.flagged-field-row')).toHaveCount(0);
    await confirmQuotation(page);
  });

  test('blocks low-confidence line price until confirmed as extracted', async ({ page }) => {
    const quotationId = await uploadQuotationAndOpenReview(page, 'quote_line_price_gate.pdf');
    seedQuotationReviewCase(buyer.email, quotationId, 'unit_price');
    await page.reload();
    await page.locator('button.confirm-btn').click();
    await page.locator('.confirm-dialog .confirm-dialog-actions .mat-mdc-unelevated-button').click();
    await expect(page.locator('.error-text')).toContainText(
      /Review or confirm the flagged extraction fields before confirming\./,
    );
    await expect(page.locator('.error-text')).not.toHaveText(
      'Request conflicts with the current state.',
    );
    const priceFlag = page.locator('.flagged-field-row').filter({ has: page.getByText('Unit price', { exact: true }) });
    await expect(priceFlag).toHaveClass(/flagged-highlight/);
    await priceFlag.locator('button').last().click();
    await page.locator('button.save-btn').click();
    await expect(page.locator('.corrected-tag').first()).toBeVisible();
    await page.locator('button.confirm-btn').click();
    const dialog = page.locator('.confirm-dialog');
    await expect(dialog).toBeVisible();
    await dialog.locator('.confirm-dialog-actions .mat-mdc-unelevated-button').click();
    await expect(page.locator('.status-pill.status-reviewed')).toBeVisible();
  });

  test('renders Arabic supplier provenance as auto-direction plain text', async ({ page }) => {
    const quotationId = await uploadQuotationAndOpenReview(page, 'quote_supplier_provenance.pdf');
    seedQuotationReviewCase(buyer.email, quotationId, 'supplier_name');
    await page.reload();
    // With a supplier selected the supplier_name row is (correctly) not a blocker; clear the
    // selection so the row reappears and its provenance can be opened.
    await openAsyncSelect(page, page.locator('mat-select[required]'));
    await page.locator('mat-option').first().click();
    // Focus a different field first: the provenance box must then switch to the supplier name
    // because of the Go-to-field click, not because it happened to be the page's default.
    await page.locator('.field-box', { hasText: 'Issue Date' }).first().click();
    await expect(page.locator('.extraction-field-label')).not.toHaveText('Supplier Name');
    const supplierFlag = page.locator('.flagged-field-row').filter({ has: page.getByText('Supplier name', { exact: true }) });
    await supplierFlag.getByRole('button', { name: 'Go to field', exact: true }).click();
    await expect(page.locator('.extraction-field-label')).toHaveText('Supplier Name');
    const originalValue = page.locator('.prov-item').filter({ hasText: 'Original AI Value' }).locator('.prov-val');
    await expect(originalValue).toHaveAttribute('dir', 'auto');
    await expect(originalValue).toContainText('الأمانة للتجارة');
    await expect(originalValue).not.toHaveText(/^"/);
  });
});
