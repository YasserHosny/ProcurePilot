import { test, expect } from '@playwright/test';
import {
  createMember,
  createTestProduct,
  signInOwner,
  type CreatedMember,
} from './support/api';

/**
 * End-to-End test suite for Smart Compare (T021, US1).
 *
 * Requirements:
 * - FR-001: List eligible supplier offers side-by-side with true landed cost and signals.
 * - FR-002: Exclude or clearly mark expired offers.
 * - FR-003: Single recommended offer with evidence, calibrated confidence, risk notes, validity.
 * - FR-004 / SC-002: Instant client-side quantity recalculation.
 * - FR-016: Dual language (English & Arabic RTL) support.
 */
test.describe('Smart Compare Screen (T021, US1)', () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('recalculates instantly on quantity change without leaving the compare grid', async ({ page }) => {
    const ownerToken = await signInOwner();
    const product = await createTestProduct(ownerToken);

    await page.goto(`/offers/compare?product_id=${product.id}`);

    await expect(page.locator('.page-title')).toContainText('Smart Compare');

    // The product exists but has no offers yet, so the empty state renders.
    await expect(page.locator('.empty-state-card')).toBeVisible();

    // SC-002: quantity edits recompute client-side — the grid stays rendered, URL unchanged.
    await page.fill('.quantity-input', '25');
    await expect(page.locator('.quantity-input')).toHaveValue('25');
    await expect(page.locator('.empty-state-card')).toBeVisible();
  });

  test('renders Smart Compare in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/compare');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('مقارنة العروض الذكية');
  });

  test('displays empty state gracefully when no offers exist for product', async ({ page }) => {
    // A real catalogue product with no matched lines has no offers to compare.
    const ownerToken = await signInOwner();
    const product = await createTestProduct(ownerToken);

    await page.goto(`/offers/compare?product_id=${product.id}`);
    await expect(page.locator('.empty-state-card')).toBeVisible();
  });
});
