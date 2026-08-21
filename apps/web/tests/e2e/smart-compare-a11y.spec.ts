import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

import { createMember, type CreatedMember } from './support/api';

/**
 * Accessibility for Smart Compare & Intelligence (T071, SC-001, FR-016).
 *
 * WCAG 2.1 AA on all 4 new screens in both English and Arabic (RTL), asserted with zero violations.
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: import('@playwright/test').Page) {
  return (
    new AxeBuilder({ page })
      .withTags(WCAG_21_AA)
      .exclude('.nav-item.disabled')
      .analyze()
  );
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

test.describe('Smart Compare & Intelligence Accessibility @a11y', () => {
  let member: CreatedMember;

  test.beforeEach(async () => {
    member = await createMember('buyer');
  });

  async function signIn(page: import('@playwright/test').Page) {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  }

  // 1. Compare Screen
  test('the Smart Compare screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/offers/compare');
    await expect(page.locator('.page-title')).toContainText('Smart Compare');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Smart Compare screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/compare');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 2. Product Intelligence Screen
  test('the Product Intelligence screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/offers/product-intelligence');
    await expect(page.locator('.page-title')).toContainText('Product Price Intelligence');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Product Intelligence screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/product-intelligence');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 3. Basket Split Screen
  test('the Basket Split screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/offers/basket-split');
    await expect(page.locator('.page-title')).toContainText('Two-Supplier Basket Split');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Basket Split screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/offers/basket-split');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 4. Alerts Inbox Screen
  test('the Alerts Inbox screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/alerts');
    await expect(page.locator('.page-title')).toContainText('Actionable Alerts Inbox');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Alerts Inbox screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/alerts');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
