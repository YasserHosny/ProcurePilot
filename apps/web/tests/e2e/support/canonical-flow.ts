/**
 * Shared UI helpers that drive the canonical quotation flow through the real running stack.
 *
 * The stub extraction provider (services/extraction-worker providers.py) is deterministic for
 * every upload regardless of file content: exactly two lines — 3 × £12.00 and 2 × £20.00 less
 * £1.00 discount, so the computed line total is always £75.00 — a stated_total of either
 * £88.00 or £77.00 (hash-chosen), which means the arithmetic-mismatch banner is present on
 * every single upload, and an issue_date confidence of 0.62 or 0.78, both below the 0.85
 * confirm threshold, which means the low-confidence gate is also always present.
 *
 * Reaching a confirmable state therefore always takes the same route: select a supplier,
 * correct Stated Total to 75.00 (reconciles arithmetic), resolve the low-confidence Issue
 * Date flag via its "confirm as extracted" control, save, then confirm through the review
 * dialog. These helpers encode that recipe once so every spec that needs a confirmed
 * quotation reuses it instead of re-deriving it.
 */

import { expect, type Page } from '@playwright/test';

import { createTestSupplier, fetchQuotationMatches, findProductByName, signInOwner } from './api';

/** The stub provider's fixed line arithmetic: 3×12 + (2×20 − 1) = 75.00, always. */
export const STUB_COMPUTED_TOTAL = '75.00';

/**
 * The stub provider ignores file content, but the upload API does not: it hashes the bytes and
 * refuses a re-upload of content that already exists in the workspace ("Possible Duplicate
 * Detected"). Embedding a per-call unique token keeps every upload on the primary path instead
 * of dead-ending on the duplicate dialog.
 */
function stubPdfBytes(fileName: string): Buffer {
  const token = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}-${fileName}`;
  return Buffer.from(
    `%PDF-1.4\n1 0 obj\n<< /Title (Quotation ${token}) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF`,
  );
}

export interface CreatedSupplier {
  id: string;
  name: string;
}

/** A real workspace supplier with a unique name, safe to select in the review dropdown. */
export async function createE2ESupplier(): Promise<CreatedSupplier> {
  return createTestSupplier(await signInOwner(), `E2E Flow Supplier ${Date.now()}`);
}

/**
 * Uploads an inline PDF through the real upload screen, waits for stub extraction to finish,
 * opens the review screen, and returns the new quotation's id from the URL.
 */
export async function uploadQuotationAndOpenReview(
  page: Page,
  fileName: string,
): Promise<string> {
  await page.goto('/quotations/upload');
  await page.setInputFiles('input.file-input', {
    name: fileName,
    mimeType: 'application/pdf',
    buffer: stubPdfBytes(fileName),
  });
  const startUpload = page.locator('.start-upload-btn');
  if (await startUpload.isVisible()) {
    await startUpload.click();
  }
  // 30s, not the framework default 10s: real extraction (a genuine RQ round trip) is slower
  // than a client-side state change, but must stay under the 60s per-test default so a real
  // failure here surfaces as this assertion rather than an opaque outer test timeout.
  await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 30000 });
  await page.click('a:has-text("Proceed to Review")');
  await page.waitForURL('**/quotations/**/review');
  return page.url().split('/quotations/')[1].split('/')[0];
}

export async function selectReviewSupplier(page: Page, supplierName: string): Promise<void> {
  // mat-select cannot be driven by selectOption(); open the overlay, then click the option.
  await page.locator('mat-select[required]').click();
  await page.locator('mat-option', { hasText: supplierName }).click();
}

/** Corrects Stated Total to the computed line total, reconciling the deterministic mismatch. */
export async function correctStatedTotal(page: Page): Promise<void> {
  const input = page
    .locator('.field-box', { hasText: 'Stated Total Amount' })
    .locator('input');
  await input.fill(STUB_COMPUTED_TOTAL);
}

/**
 * Resolves the low-confidence Issue Date flag via the field's "confirm as extracted" control.
 *
 * The Issue Date input is a matDatepicker: filling it programmatically never fires the
 * (dateChange) binding that stages a correction, so the low-confidence gate would survive and
 * confirm would be rejected with low_confidence_unresolved. The confirm-as-is button stages
 * the extracted value as a human-confirmed correction through the same mechanism as a manual
 * edit, which is exactly what this recipe needs.
 */
export async function resolveIssueDateFlag(page: Page): Promise<void> {
  const fieldBox = page.locator('.field-box', { hasText: 'Issue Date' });
  await fieldBox.locator('.confirm-as-is-btn').click();
  await expect(fieldBox.locator('.corrected-tag')).toBeVisible();
}

/** Saves pending corrections and asserts they were persisted with attribution and took effect. */
export async function saveCorrections(page: Page): Promise<void> {
  await page.locator('button.save-btn').click();
  await expect(page.locator('.corrected-tag').first()).toBeVisible();
  await expect(page.locator('.arithmetic-mismatch-banner')).toBeHidden();
  await expect(page.locator('button.confirm-btn')).toBeEnabled();
}

/** Confirms the quotation and asserts it reached the reviewed state. */
export async function confirmQuotation(page: Page): Promise<void> {
  await page.locator('button.confirm-btn').click();
  // FR-016: confirmation is a two-step human authorisation — the button opens an in-page
  // dialog whose Proceed button performs the actual POST /confirm.
  const dialog = page.locator('.confirm-dialog');
  await expect(dialog).toBeVisible();
  await dialog.locator('.confirm-dialog-actions .mat-mdc-unelevated-button').click();
  await expect(page.locator('.status-pill.status-reviewed')).toBeVisible();
  const continueLink = page.getByRole('link', { name: 'Continue to Product Matching' });
  await expect(continueLink).toBeVisible({ timeout: 30000 });
  await expect(continueLink).toHaveAttribute('href', /\/matching\?quotation_id=/);
}

/** The full upload → correct → confirm recipe, for specs that just need a confirmed quotation. */
export async function reconcileAndConfirmQuotation(
  page: Page,
  fileName: string,
): Promise<{ quotationId: string; supplier: CreatedSupplier }> {
  const supplier = await createE2ESupplier();
  const quotationId = await uploadQuotationAndOpenReview(page, fileName);
  await selectReviewSupplier(page, supplier.name);
  await correctStatedTotal(page);
  await resolveIssueDateFlag(page);
  await saveCorrections(page);
  await confirmQuotation(page);
  return { quotationId, supplier };
}

/**
 * Gets one line of a known quotation to a match decision with a landed cost, by resolving it
 * from the Match Resolution Queue as a new catalogue product.
 *
 * Groups are disambiguated by the quotation-id badge shown in the queue, because earlier tests in
 * the same run leave their own open tasks behind. Resolving a line teaches the workspace an
 * exact-text alias for the stub line wording (resolution_service learns it on every outcome), so
 * an identical line on any LATER quotation deterministically auto-matches — confidence 0.93 is
 * above the 0.92 auto-accept threshold — and never reaches this queue. That is the product
 * behaving correctly, so if the row does not appear we wait for the pipeline's automatic
 * decision instead of failing; callers get back which path happened plus the matched product id.
 *
 * When the resolution UI does run, the base unit is set explicitly (kilogram) so the created
 * product's pack_base_quantity is deterministic (1 × 10 kg for the stub's tomato line), which pins every
 * later Smart Compare number too.
 */
export interface ResolvedLineMatch {
  productId: string;
  via: 'ui_resolution' | 'alias_auto_accept';
}

export async function resolveLineAsNewProduct(
  page: Page,
  quotationId: string,
  lineTextPart: string,
  productName: string,
): Promise<ResolvedLineMatch> {
  await page.goto(`/matching?quotation_id=${quotationId}`);
  const group = page.locator('.quotation-group', { hasText: quotationId.slice(0, 8) });
  const line = group.locator('.match-line', { hasText: lineTextPart });

  try {
    await line.waitFor({ state: 'visible', timeout: 12000 });
  } catch {
    return {
      productId: await waitForAutoAcceptedProductId(quotationId, lineTextPart),
      via: 'alias_auto_accept',
    };
  }

  await expect(line).toHaveCount(1);
  await line.locator('.action-btn').click();
  await page.waitForURL('**/matching/**');

  // Select the outcome explicitly: with candidates present the component auto-selects rank 1
  // and same_product, so the default must not be relied on. The radio's value is a property
  // binding (no DOM attribute), so locate by the rendered English label instead.
  await page.locator('mat-radio-button', { hasText: 'No Match — Create New Product' }).click();
  await expect(page.locator('.new-product-section')).toBeVisible();

  await page.fill('input[formControlName="tenant_name"]', productName);
  await page.locator('mat-select[formControlName="base_unit"]').click();
  await page.locator('mat-option', { hasText: '(kilogram)' }).click();

  await page.locator('button.confirm-resolution-btn').click();
  await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 15000 });

  const ownerToken = await signInOwner();
  return { productId: (await findProductByName(ownerToken, productName)).id, via: 'ui_resolution' };
}

/** Polls the matches endpoint until the pipeline has auto-decided the line, then returns its product. */
async function waitForAutoAcceptedProductId(
  quotationId: string,
  lineTextPart: string,
): Promise<string> {
  const token = await signInOwner();
  const deadline = Date.now() + 30000;
  for (;;) {
    const matches = await fetchQuotationMatches(token, quotationId);
    const state = matches.lines.find((l) => l.line.original_text.includes(lineTextPart));
    if (state?.decision && state.landed_cost) {
      return state.decision.matched_product.id;
    }
    if (Date.now() > deadline) {
      throw new Error(
        `Line "${lineTextPart}" of quotation ${quotationId} has neither an open queue task nor an auto decision`,
      );
    }
    await sleep(1000);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
