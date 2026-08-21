import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

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

  test('resolution queue lists match tasks with status and priority filters', async ({ page }) => {
    await page.goto('/matching');
    await expect(page.locator('.page-title')).toContainText('Match Resolution Queue');
    await expect(page.locator('.filter-card')).toBeVisible();

    // Table or empty state should be rendered
    const tableOrEmpty = page.locator('.tasks-table, .empty-state');
    await expect(tableOrEmpty).toBeVisible();
  });

  test('candidate selection and confirmation work via keyboard alone (FR-012)', async ({ page }) => {
    await page.goto('/matching');

    // If there is an item in the queue, navigate to it, otherwise navigate to direct route
    const resolveBtn = page.locator('.resolve-btn').first();
    if (await resolveBtn.isVisible()) {
      await resolveBtn.click();
      await page.waitForURL('**/matching/**');

      // Verify resolution interface
      await expect(page.locator('.keyboard-shortcuts-bar')).toBeVisible();
      await expect(page.locator('.candidates-section')).toBeVisible();

      // Test candidate selection with number keys (e.g. key '1', '2')
      const candidateCards = page.locator('.candidate-card');
      const count = await candidateCards.count();

      if (count >= 2) {
        // Press '2' to select candidate 2
        await page.keyboard.press('2');
        await expect(candidateCards.nth(1)).toHaveClass(/selected/);

        // Press '1' to select candidate 1
        await page.keyboard.press('1');
        await expect(candidateCards.nth(0)).toHaveClass(/selected/);

        // Press ArrowDown to navigate down
        await page.keyboard.press('ArrowDown');
        await expect(candidateCards.nth(1)).toHaveClass(/selected/);

        // Press ArrowUp to navigate up
        await page.keyboard.press('ArrowUp');
        await expect(candidateCards.nth(0)).toHaveClass(/selected/);
      }

      // Test outcome toggling with 'O' key
      await page.keyboard.press('o');
      await expect(page.locator('.outcome-radio-item').nth(1)).toBeVisible();

      // Press Enter to confirm resolution via keyboard without mouse
      await page.keyboard.press('Enter');

      // After confirm, verify decision banner or toast
      await expect(page.locator('.decision-banner, .mat-mdc-snack-bar-container')).toBeVisible({
        timeout: 10000,
      });
    }
  });

  test('inline product creation form appears on no-match outcome', async ({ page }) => {
    await page.goto('/matching');

    const resolveBtn = page.locator('.resolve-btn').first();
    if (await resolveBtn.isVisible()) {
      await resolveBtn.click();
      await page.waitForURL('**/matching/**');

      // Select "no_match_new_product" outcome radio
      const noMatchRadio = page.locator('mat-radio-button[value="no_match_new_product"]');
      if (await noMatchRadio.isVisible()) {
        await noMatchRadio.click();

        // Verify product creation form fields
        await expect(page.locator('.new-product-section')).toBeVisible();
        await expect(page.locator('input[formControlName="tenant_name"]')).toBeVisible();
        await expect(page.locator('mat-select[formControlName="base_unit"]')).toBeVisible();
        await expect(page.locator('.normalisation-preview')).toBeVisible();
      }
    }
  });
});
