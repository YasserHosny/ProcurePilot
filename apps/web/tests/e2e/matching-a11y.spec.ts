import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

import { createMember, type CreatedMember } from './support/api';

/**
 * Accessibility for Matching and Normalisation (T054, SC-004, FR-012).
 *
 * WCAG 2.1 AA on Matching screens in both English and Arabic (RTL), asserted with zero violations.
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

test.describe('Matching Accessibility @a11y', () => {
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

  test('the match resolution queue screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/matching');
    await expect(page.locator('.page-title')).toContainText('Match Resolution Queue');
    // The title renders before the task list's own async fetch resolves; scanning too early can
    // catch a transient loading skeleton with poor contrast, especially under CI/full-suite load.
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the match resolution queue screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/matching');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the match resolution screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/matching/test-line-id');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the match resolution screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/matching/test-line-id');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
