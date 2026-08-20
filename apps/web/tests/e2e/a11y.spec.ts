import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

import { createMember, type CreatedMember } from './support/api';

/**
 * Accessibility — task T075 (FR-022, SC-006).
 *
 * WCAG 2.1 AA on every shell screen, asserted with zero violations. The constitution lists this
 * as a release gate, not an aspiration, so it runs in CI on every change.
 *
 * Tagged @a11y so `pnpm test:a11y` selects exactly these. Note that before this file existed that
 * script matched nothing and therefore passed — a check that cannot fail, which is worse than no
 * check because it reports assurance it never earned.
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: import('@playwright/test').Page) {
  return (
    new AxeBuilder({ page })
      .withTags(WCAG_21_AA)
      // Placeholder navigation for features that do not exist yet: rendered greyed out, marked
      // aria-disabled, not focusable, not actionable. WCAG 1.4.3 exempts text that is part of an
      // inactive user interface component from the contrast requirement, and axe cannot infer
      // that from a div. This is the ONLY exclusion, and it disappears when those features ship
      // and the entries become real links.
      .exclude('.nav-item.disabled')
      .analyze()
  );
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

test.describe('Accessibility @a11y', () => {
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

  test('the sign-in screen has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await page.goto('/auth/sign-in');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the password reset screen has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await page.goto('/auth/password-reset');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the authenticated shell has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the shell in Arabic and RTL has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    // RTL is where accessibility regressions hide: mirrored layout, bidirectional text, and
    // direction-dependent focus order are all easy to break without noticing in English.
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // --- Catalogue and Suppliers A11y (T040, SC-008) ---

  test('the product list screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/products');
    await expect(page.locator('.page-title')).toContainText('Product Master');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the product list screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/products');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the product form screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/products/new');
    await expect(page.locator('.page-title')).toContainText('Create Product');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the product form screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/products/new');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the supplier list screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/suppliers');
    await expect(page.locator('.page-title')).toContainText('Suppliers');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the supplier list screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/suppliers');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the supplier form screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/suppliers/new');
    await expect(page.locator('.page-title')).toContainText('Create Supplier');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the supplier form screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/suppliers/new');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the import wizard screen in English has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/import');
    await expect(page.locator('.page-title')).toContainText('Import Wizard');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the import wizard screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/import');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});

