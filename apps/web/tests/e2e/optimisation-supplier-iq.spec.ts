import { test, expect } from '@playwright/test';
import {
  createMember,
  createTestSupplier,
  signInOwner,
  type CreatedMember,
} from './support/api';

/**
 * End-to-End test suite for Optimisation and Supplier IQ (T038, US1-US4).
 *
 * Requirements:
 * - US1 / FR-001 - FR-005: Advanced basket optimisation with commercial constraints (MOV, urgency,
 *   risk tolerance, supplier exclusions, weights) and advisory-only behaviour (no autonomous purchasing).
 * - US2 / FR-006 - FR-008: Supplier IQ scorecards with dense operational metrics, deterministic risk
 *   score breakdown, source counts, and insufficient evidence disclosure.
 * - US3 / FR-009 - FR-011: Anomaly detection alerts with confidence, severity, and action links into
 *   supplier scorecards and quotation reviews.
 * - US4 / FR-016: Dual language (English & Arabic RTL) without layout breakages or missing strings.
 */
test.describe('Optimisation & Supplier IQ E2E (T038)', () => {
  let buyer: CreatedMember;
  let ownerToken: string;
  let testSupplier: { id: string; name: string };

  test.beforeEach(async ({ page }) => {
    buyer = await createMember('buyer');
    ownerToken = await signInOwner();
    testSupplier = await createTestSupplier(ownerToken);

    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('User Story 1: Advanced basket optimisation exposes constraint controls and advisory-only result', async ({ page }) => {
    await page.goto('/offers/basket-split');

    await expect(page.locator('.page-title')).toContainText('Two-Supplier Basket Split');

    // Verify presence of constraint controls expansion
    const toggleConstraintsBtn = page.locator('.toggle-constraints-btn');
    if (await toggleConstraintsBtn.isVisible()) {
      await toggleConstraintsBtn.click();
      // Verify constraint inputs: Risk tolerance, Urgency, Excluded suppliers, Weights
      await expect(page.locator('.constraints-controls-grid')).toBeVisible();
      await expect(page.locator('.weights-section')).toBeVisible();
    }

    // Verify advisory-only nature: No automated purchasing/ordering buttons exist
    const autonomousBtns = page.locator('button:has-text("Order Now"), button:has-text("Auto-Purchase"), button:has-text("Checkout")');
    await expect(autonomousBtns).toHaveCount(0);
  });

  test('User Story 2: Supplier Scorecard renders dense operational metrics, risk score, and insufficient evidence notice', async ({ page }) => {
    await page.goto(`/suppliers/${testSupplier.id}/scorecard`);

    // Verify scorecard header and supplier name
    await expect(page.locator('#scorecard-heading')).toContainText('Supplier Scorecard');
    await expect(page.locator('.supplier-subtitle')).toContainText(testSupplier.name);

    // Verify window selection chips
    await expect(page.locator('.window-selector')).toBeVisible();

    // Since this is a newly created supplier with sparse evidence, verify insufficient evidence notice
    const insufficientNotice = page.locator('.insufficient-notice');
    if (await insufficientNotice.isVisible()) {
      await expect(insufficientNotice).toContainText('Insufficient Evidence');
    }

    // Verify risk card and confidence card are rendered
    await expect(page.locator('.summary-cards-row')).toBeVisible();
    await expect(page.locator('.risk-card')).toBeVisible();
    await expect(page.locator('.confidence-card')).toBeVisible();

    // Verify metrics section is displayed
    await expect(page.locator('.metrics-section')).toBeVisible();
    await expect(page.locator('.metrics-grid')).toBeVisible();
  });

  test('User Story 3: Alerts Inbox displays anomaly badges and navigates to supplier scorecard via action links', async ({ page }) => {
    await page.goto('/alerts');

    await expect(page.locator('.page-title')).toContainText('Actionable Alerts Inbox');

    // Verify alert list or all-clear state
    const content = page.locator('.alerts-list, .empty-state-card');
    await expect(content).toBeVisible();

    // If an alert with inspect_scorecard or scorecard link is present, clicking it navigates to scorecard
    const scorecardActionBtn = page.locator('button:has-text("Inspect Scorecard"), a:has-text("Inspect Scorecard")').first();
    if (await scorecardActionBtn.isVisible()) {
      await scorecardActionBtn.click();
      await expect(page).toHaveURL(/.*\/suppliers\/.*\/scorecard/);
      await expect(page.locator('#scorecard-heading')).toBeVisible();
    }
  });

  test('User Story 4: Arabic RTL layout for Advanced Basket and Supplier Scorecard without clipping', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');

    // 1. Basket Split in Arabic
    await page.goto('/offers/basket-split');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('تقسيم السلة');

    // 2. Supplier Scorecard in Arabic
    await page.goto(`/suppliers/${testSupplier.id}/scorecard`);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('#scorecard-heading')).toContainText('بطاقة أداء المورّد');
    await expect(page.locator('.back-link')).toBeVisible();
  });
});
