import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

import { createMember, type CreatedMember } from './support/api';

/**
 * Value Proof & Launch Readiness Accessibility Audit (T067, US4).
 *
 * Scans all Chunk 4.6 screens in English and Arabic (RTL) for zero WCAG 2.1 AA violations:
 * - Savings Ledger (/savings)
 * - Outcome Capture (/savings/outcome-capture)
 * - Savings Export (/savings/export)
 * - Subscription Plan Display (/plan)
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

test.describe('Value Proof Accessibility Audit @a11y (T067)', () => {
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

  // 1. Savings Ledger
  test('Savings Ledger in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/savings');
    await expect(page.locator('.page-title')).toContainText('Savings Ledger');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Savings Ledger in Arabic has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/savings');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 2. Outcome Capture
  test('Outcome Capture in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/savings/outcome-capture');
    await expect(page.locator('.page-title')).toContainText('Record Purchase Outcome');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Outcome Capture in Arabic has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/savings/outcome-capture');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 3. Savings Export
  test('Savings Export in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/savings/export');
    await expect(page.locator('.page-title')).toContainText('Export Savings Ledger');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Savings Export in Arabic has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/savings/export');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 4. Plan Display
  test('Subscription Plan Display in English has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/plan');
    await expect(page.locator('.page-title')).toContainText('Your Workspace Plan');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Subscription Plan Display in Arabic has zero WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/plan');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
