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
 * correct Stated Total to 75.00 (reconciles arithmetic), correct Issue Date to a different
 * value (clears low_confidence_unresolved), save, confirm. These helpers encode that recipe
 * once so every spec that needs a confirmed quotation reuses it instead of re-deriving it.
 */

import { expect, type Page } from '@playwright/test';

import { createTestSupplier, fetchQuotationMatches, findProductByName, signInOwner } from './api';

/** The stub provider's fixed line arithmetic: 3×12 + (2×20 − 1) = 75.00, always. */
export const STUB_COMPUTED_TOTAL = '75.00';

const STUB_PDF =
  '%PDF-1.4\n1 0 obj\n<< /Title (Quotation) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF';

/** The stub provider always extracts this issue date; a correction must differ to fire change. */
const ISSUE_DATE_REPLACEMENT = '2026-08-19';

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
    buffer: Buffer.from(STUB_PDF),
  });
  await page.click('.start-upload-btn');
  await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 20000 });
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
 * Corrects Issue Date to a value different from the extracted one — Angular's (change) only
 * fires on a real value change, and the extracted value is deterministically 2026-08-21.
 */
export async function correctIssueDate(page: Page): Promise<void> {
  const input = page.locator('.field-box', { hasText: 'Issue Date' }).locator('input');
  await input.fill(ISSUE_DATE_REPLACEMENT);
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
  await expect(page.locator('.status-pill.status-reviewed')).toBeVisible();
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
  await correctIssueDate(page);
  await saveCorrections(page);
  await confirmQuotation(page);
  return { quotationId, supplier };
}

/**
 * Gets one line of a known quotation to a match decision with a landed cost, by resolving it
 * from the Match Resolution Queue as a new catalogue product.
 *
 * Rows are disambiguated by the quotation-id badge shown in the queue, because earlier tests in
 * the same run leave their own open tasks behind. Resolving a line teaches the workspace an
 * exact-text alias for the stub line wording (resolution_service learns it on every outcome), so
 * an identical line on any LATER quotation deterministically auto-matches — confidence 0.93 is
 * above the 0.92 auto-accept threshold — and never reaches this queue. That is the product
 * behaving correctly, so if the row does not appear we wait for the pipeline's automatic
 * decision instead of failing; callers get back which path happened plus the matched product id.
 *
 * When the resolution UI does run, the base unit is set explicitly (kg) so the created product's
 * pack_base_quantity is deterministic (1 × 10 kg for the stub's tomato line), which pins every
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
  await page.goto('/matching');
  const row = page
    .locator('tr.mat-mdc-row', { hasText: quotationId.slice(0, 8) })
    .filter({ hasText: lineTextPart });

  try {
    await row.waitFor({ state: 'visible', timeout: 12000 });
  } catch {
    return {
      productId: await waitForAutoAcceptedProductId(quotationId, lineTextPart),
      via: 'alias_auto_accept',
    };
  }

  await expect(row).toHaveCount(1);
  await row.locator('.resolve-btn').click();
  await page.waitForURL('**/matching/**');

  // Select the outcome explicitly: with candidates present the component auto-selects rank 1
  // and same_product, so the default must not be relied on. The radio's value is a property
  // binding (no DOM attribute), so locate by the rendered English label instead.
  await page.locator('mat-radio-button', { hasText: 'No Match — Create New Product' }).click();
  await expect(page.locator('.new-product-section')).toBeVisible();

  await page.fill('input[formControlName="tenant_name"]', productName);
  await page.locator('mat-select[formControlName="base_unit"]').click();
  await page.locator('mat-option', { hasText: '(kg)' }).click();

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
