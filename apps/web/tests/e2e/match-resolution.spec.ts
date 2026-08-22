import { test, expect } from '@playwright/test';
import {
  createMember,
  createTestProduct,
  signInOwner,
  type CreatedMember,
} from './support/api';
import {
  reconcileAndConfirmQuotation,
} from './support/canonical-flow';

/**
 * End-to-End test suite for Match Resolution & Keyboard-First Navigation (T032, US2).
 *
 * Requirements:
 * - FR-008: Reviewers can resolve a line with same product, different pack, different variant,
 *   compatible alternative, or no match.
 * - FR-009: When no match is chosen, reviewer can create a new catalogue product inline.
 * - FR-011: Standalone match-resolution queue independent of a single quotation page.
 * - FR-012: Reviewers MUST be able to select a candidate and confirm a resolution using the
 *   keyboard alone, without the mouse.
 *
 * A confirmed quotation is the precondition for everything here: confirming is the one place
 * that calls GET /quotations/{id}/matches, which runs the matching pipeline and populates this
 * queue. Each test builds that state itself through the shared canonical-flow helpers.
 */
test.describe('Match Resolution & Keyboard-Only Navigation (T032, US2)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('resolution queue lists the confirmed quotation lines as open tasks with status and priority filters', async ({ page }) => {
    const { quotationId } = await reconcileAndConfirmQuotation(page, 'queue_seed.pdf');

    // The pipeline routes both stub lines to review (candidate confidence never reaches the
    // auto-accept threshold), so both must appear here as open tasks for this quotation.
    await page.goto('/matching');
    const ourRows = page.locator('tr.mat-mdc-row', { hasText: quotationId.slice(0, 8) });
    await expect(ourRows).toHaveCount(2, { timeout: 30000 });
    await expect(ourRows.filter({ hasText: 'Tomatoes case 10 kg' })).toHaveCount(1);
    await expect(ourRows.filter({ hasText: 'Olive oil tin 5 litre' })).toHaveCount(1);
    await expect(page.locator('.filter-card')).toBeVisible();
    await expect(ourRows.first().locator('.status-badge.status-open')).toBeVisible();
    await expect(ourRows.first().locator('.priority-badge')).toBeVisible();
  });

  test('candidate selection and confirmation work via keyboard alone (FR-012)', async ({ page }) => {
    // Seed the catalogue with two near-exact matches for the olive-oil line so the matching
    // pipeline deterministically presents exactly two candidates for it.
    const ownerToken = await signInOwner();
    await createTestProduct(ownerToken, { tenant_name: 'Olive oil tin 5 litre x 2 @ 20.00 less 1.00', base_unit: 'litre' });
    await createTestProduct(ownerToken, { tenant_name: 'Olive oil tin 5 litre', base_unit: 'litre' });

    const { quotationId } = await reconcileAndConfirmQuotation(page, 'keyboard_seed.pdf');

    await page.goto('/matching');
    // Resolve the olive-oil line, not the tomato one: completing a resolution teaches the
    // workspace an exact-text alias for that line's wording, and later specs in the same run
    // need an un-aliased tomato line for their own canonical-path resolution.
    const oliveRow = page
      .locator('tr.mat-mdc-row', { hasText: quotationId.slice(0, 8) })
      .filter({ hasText: 'Olive oil tin 5 litre' });
    await expect(oliveRow).toHaveCount(1, { timeout: 30000 });

    const candidateCards = page.locator('.candidate-card');
    await oliveRow.locator('.resolve-btn').click();
    await page.waitForURL('**/matching/**');

    await expect(page.locator('.keyboard-shortcuts-bar')).toBeVisible();
    await expect(page.locator('.candidates-section')).toBeVisible();
    await expect(candidateCards).toHaveCount(2);

    // Select candidate 2, then candidate 1, then navigate — all via the keyboard.
    await page.keyboard.press('2');
    await expect(candidateCards.nth(1)).toHaveClass(/selected/);

    await page.keyboard.press('1');
    await expect(candidateCards.nth(0)).toHaveClass(/selected/);

    await page.keyboard.press('ArrowDown');
    await expect(candidateCards.nth(1)).toHaveClass(/selected/);

    await page.keyboard.press('ArrowUp');
    await expect(candidateCards.nth(0)).toHaveClass(/selected/);

    // Toggle the outcome with 'O' (same_product → different_pack). The radio's value is a
    // property binding (no DOM attribute), so assert via the checked host class on the
    // label-located button.
    await page.keyboard.press('o');
    await expect(
      page.locator('mat-radio-button', { hasText: 'Different Pack Size' }),
    ).toHaveClass(/mat-mdc-radio-checked/);

    // Confirm the resolution via Enter alone and assert the decision was recorded.
    await page.keyboard.press('Enter');
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.landed-cost-card')).toBeVisible();
  });

  test('inline product creation form appears on no-match outcome', async ({ page }) => {
    const { quotationId } = await reconcileAndConfirmQuotation(page, 'no_match_seed.pdf');

    await page.goto('/matching');
    // Use the tomato line: the keyboard test before this one resolved the olive-oil line,
    // which taught the workspace an exact-text alias for it, so any later olive line
    // auto-matches and never reaches this queue. The tomato line still always does.
    const tomatoRow = page
      .locator('tr.mat-mdc-row', { hasText: quotationId.slice(0, 8) })
      .filter({ hasText: 'Tomatoes case 10 kg' });
    await expect(tomatoRow).toHaveCount(1, { timeout: 30000 });

    await tomatoRow.locator('.resolve-btn').click();
    await page.waitForURL('**/matching/**');

    // Select "no_match_new_product" outcome radio (value is a property binding, not an
    // attribute, so locate by the rendered label)
    const noMatchRadio = page
      .locator('mat-radio-button', { hasText: 'No Match — Create New Product' });
    await noMatchRadio.click();

    // Verify product creation form fields, including the pre-fill from the line's own wording
    await expect(page.locator('.new-product-section')).toBeVisible();
    const tenantName = page.locator('input[formControlName="tenant_name"]');
    await expect(tenantName).toBeVisible();
    await expect(tenantName).not.toHaveValue('');
    await expect(page.locator('mat-select[formControlName="base_unit"]')).toBeVisible();
    await expect(page.locator('.normalisation-preview')).toBeVisible();
  });
});
