import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

import {
  createMember,
  createTestSupplier,
  signInOwner,
  type CreatedMember,
} from './support/api';

/**
 * Accessibility and RTL Audit for Optimisation and Supplier IQ (T039, US4, FR-016).
 *
 * Requirements:
 * - WCAG 2.1 AA across the new R2.4 feature surface (zero violations).
 * - Bi-directional layout: full RTL validation in Arabic (`dir="rtl"`).
 * - Surfaces covered:
 *   1. Basket Split & Advanced Optimisation (/offers/basket-split)
 *   2. Supplier IQ Scorecard (/suppliers/:id/scorecard)
 *   3. Commercial Anomaly Alerts Inbox (/alerts)
 *   4. Smart Compare with Supplier IQ Risk Evidence (/offers/compare)
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: import('@playwright/test').Page) {
  return new AxeBuilder({ page })
    .withTags(WCAG_21_AA)
    .exclude('.nav-item.disabled')
    .analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

test.describe('Optimisation & Supplier IQ Accessibility & RTL @a11y (T039)', () => {
  let member: CreatedMember;
  let ownerToken: string;
  let testSupplier: { id: string; name: string };

  test.beforeEach(async () => {
    member = await createMember('buyer');
    ownerToken = await signInOwner();
    testSupplier = await createTestSupplier(ownerToken);
  });

  async function signIn(page: import('@playwright/test').Page) {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  }

  // 1. Advanced Basket Split
  test('Advanced Basket Split in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/offers/basket-split');
    await expect(page.locator('.page-title')).toContainText('Two-Supplier Basket Split');

    const toggleConstraintsBtn = page.locator('.toggle-constraints-btn');
    if (await toggleConstraintsBtn.isVisible()) {
      await toggleConstraintsBtn.click();
    }

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Advanced Basket Split in Arabic (RTL) has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/basket-split');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('تقسيم السلة');

    const toggleConstraintsBtn = page.locator('.toggle-constraints-btn');
    if (await toggleConstraintsBtn.isVisible()) {
      await toggleConstraintsBtn.click();
    }

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 2. Supplier IQ Scorecard
  test('Supplier IQ Scorecard in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto(`/suppliers/${testSupplier.id}/scorecard`);

    await expect(page.locator('#scorecard-heading')).toContainText('Supplier Scorecard');

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Supplier IQ Scorecard in Arabic (RTL) has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto(`/suppliers/${testSupplier.id}/scorecard`);

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('#scorecard-heading')).toContainText('بطاقة أداء المورّد');

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 3. Alerts Inbox
  test('Alerts Inbox with anomaly badges in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/alerts');
    await expect(page.locator('.page-title')).toContainText('Actionable Alerts Inbox');

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Alerts Inbox with anomaly badges in Arabic (RTL) has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/alerts');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('صندوق التنبيهات');

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 4. Smart Compare with Supplier IQ Risk Evidence
  test('Smart Compare screen in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/offers/compare');
    await expect(page.locator('.page-title')).toContainText('Smart Compare');

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Smart Compare screen in Arabic (RTL) has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/compare');

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('مقارنة العروض الذكية');

    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
