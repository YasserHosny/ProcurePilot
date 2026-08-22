import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

import { createMember, type CreatedMember } from './support/api';

/**
 * Accessibility for Quotation Inbox & Extraction (T065, SC-006).
 *
 * WCAG 2.1 AA on Quotation screens in both English and Arabic (RTL), asserted with zero violations.
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

test.describe('Quotation Accessibility @a11y', () => {
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

  test('the quotation upload screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/quotations/upload');
    await expect(page.locator('.page-title')).toContainText('Upload Supplier Quotation');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the quotation upload screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/quotations/upload');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the quotation review queue screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/quotations');
    await expect(page.locator('.page-title')).toContainText('Quotation Review Queue');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the quotation review queue screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/quotations');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the quotation review screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/quotations/test-quote-id/review');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the quotation review screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/quotations/test-quote-id/review');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
