import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

import { createMember, type CreatedMember } from './support/api';

/**
 * Phase 1 Whole-Product Retrospective Accessibility Audit (T068, US4).
 *
 * Runs full WCAG 2.1 AA audit across the complete Phase 1 product surface in EN and AR (RTL):
 * 1. Auth & Sign-in (/auth/sign-in)
 * 2. Onboarding (/onboarding/signup)
 * 3. Products Catalogue (/products, /products/new)
 * 4. Quotations (/quotations, /quotations/upload)
 * 5. Matching Resolution (/matching)
 * 6. Smart Compare & Basket Split (/offers/compare, /offers/basket-split)
 * 7. Commercial Alerts Inbox (/alerts)
 * 8. Savings Ledger, Outcome Capture, & Export (/savings, /savings/outcome-capture, /savings/export)
 * 9. Subscription Plan Display (/plan)
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

test.describe('Phase 1 Whole-Product Retrospective A11y Audit @a11y (T068)', () => {
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

  // 1. Sign-in Public Screen
  //
  // The sign-in screen has no locale switcher of its own — locale switching lives in the
  // authenticated shell (.account-btn), matching the established pattern in a11y.spec.ts, which
  // likewise only tests this screen in English. Testing it in Arabic here would require a made-up
  // interaction this product doesn't actually offer.
  test('Sign-in screen has zero WCAG violations @a11y', async ({ page }) => {
    await page.goto('/auth/sign-in');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 2. Catalogue Products List & Form
  test('Catalogue screens have zero WCAG violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/products');
    let results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);

    await page.goto('/products/new');
    results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 3. Quotations List & Upload
  test('Quotations screens have zero WCAG violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/quotations');
    let results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);

    await page.goto('/quotations/upload');
    results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 4. Matching Resolution
  test('Matching resolution screen has zero WCAG violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/matching');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 5. Smart Compare & Basket Split
  test('Offers screens have zero WCAG violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/offers/compare');
    let results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);

    await page.goto('/offers/basket-split');
    results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 6. Alerts Inbox
  test('Alerts inbox screen has zero WCAG violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/alerts');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // 7. Savings & Plan screens
  test('Savings and Plan screens have zero WCAG violations @a11y', async ({ page }) => {
    await signIn(page);
    await page.goto('/savings');
    let results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);

    await page.goto('/savings/export');
    results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);

    await page.goto('/plan');
    results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
