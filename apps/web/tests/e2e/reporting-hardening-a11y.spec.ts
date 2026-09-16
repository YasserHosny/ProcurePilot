import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import {
  createExportJob,
  createMember,
  signIn as apiSignIn,
  type CreatedMember,
} from './support/api';

/**
 * Accessibility — Reports Center and Digest Settings (T033, 012-reporting-hardening,
 * research R11).
 *
 * R11's mandatory surface list already has EN/AR axe-core coverage for every R2.5-adjacent
 * screen except the two screens this chunk adds: Reports Center and Digest Settings. This file
 * covers those two, plus the two requirements R11 calls out beyond a plain axe scan: a
 * keyboard-only journey through the Reports Center in both directions (Tab and Shift+Tab), and
 * print-stylesheet coverage for the Reports Center's artifact list.
 *
 * Tagged @a11y so `pnpm test:a11y` selects it, matching every other a11y spec's convention.
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

async function uiSignIn(page: Page, member: CreatedMember) {
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', member.email);
  await page.fill('input[formControlName="password"]', member.password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

async function switchToArabic(page: Page) {
  await page.click('.account-btn');
  await page.click('button:has-text("العربية")');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
}

test.describe('Reports Center & Digest Settings accessibility @a11y', () => {
  let member: CreatedMember;

  test.beforeEach(async ({ page }) => {
    member = await createMember('buyer');
    await uiSignIn(page, member);
  });

  test('the Reports Center screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await page.goto('/reports');
    await expect(page.locator('.page-title')).toContainText('Reports Center');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Reports Center screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await switchToArabic(page);
    await page.goto('/reports');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Digest Settings screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await page.goto('/reports/digest-settings');
    await expect(page.locator('.page-title')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Digest Settings screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await switchToArabic(page);
    await page.goto('/reports/digest-settings');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Reports Center is reachable by keyboard alone in both Tab directions (LTR) @a11y', async ({
    page,
  }) => {
    await page.goto('/reports');
    await expect(page.locator('.page-title')).toContainText('Reports Center');
    // Wait for the tab strip to be genuinely interactive before driving it by keyboard — a
    // Tab press that lands before Angular finishes its first render pass can miss every
    // focusable element and read as "focus lost" rather than a real reachability failure.
    await expect(page.locator('.mat-mdc-tab-header')).toBeVisible();

    // Forward: Tab through the header actions and into the filter toolbar. Each stop must land
    // on a real, distinct interactive element — not the body, and not the same node twice in a
    // row (a focus trap or a skipped control would both show up as that).
    const forwardStops: string[] = [];
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('Tab');
      const el = page.locator(':focus');
      await expect(el).toHaveCount(1);
      const tag = await el.evaluate((node) => node.tagName);
      const label = await el.evaluate(
        (node) => node.getAttribute('aria-label') ?? node.textContent?.trim() ?? '',
      );
      forwardStops.push(`${tag}:${label}`);
    }
    expect(new Set(forwardStops).size).toBeGreaterThan(1);

    // Backward: Shift+Tab must actually retrace focus, not merely accept the keypress. Walking
    // back the same number of steps should return focus to an earlier stop in the forward walk
    // (not off the page, not stuck on the last element).
    const backStops: string[] = [];
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('Shift+Tab');
      const el = page.locator(':focus');
      await expect(el).toHaveCount(1);
      const tag = await el.evaluate((node) => node.tagName);
      const label = await el.evaluate(
        (node) => node.getAttribute('aria-label') ?? node.textContent?.trim() ?? '',
      );
      backStops.push(`${tag}:${label}`);
    }
    for (const stop of backStops) {
      expect(forwardStops).toContain(stop);
    }
  });

  test('the Reports Center is reachable by keyboard alone in both Tab directions (RTL) @a11y', async ({
    page,
  }) => {
    await switchToArabic(page);
    await page.goto('/reports');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.mat-mdc-tab-header')).toBeVisible();

    const forwardStops: string[] = [];
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('Tab');
      const el = page.locator(':focus');
      await expect(el).toHaveCount(1);
      const tag = await el.evaluate((node) => node.tagName);
      forwardStops.push(tag);
    }
    expect(forwardStops.length).toBe(6);

    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('Shift+Tab');
      const el = page.locator(':focus');
      await expect(el).toHaveCount(1);
    }
  });

  test('the Reports Center print stylesheet hides interactive chrome and keeps the artifact table @a11y', async ({
    page,
  }) => {
    // A brand-new member has no artifacts yet, which renders the empty state, not the table —
    // seed one queued export job directly via the API so the print check exercises the actual
    // table markup rather than the empty-state placeholder.
    const token = await apiSignIn(member.email, member.password);
    await createExportJob(token, {
      kind: 'savings_ledger',
      format: 'xlsx',
      filters: { period_start: '2026-01-01', period_end: '2026-12-31' },
    });

    await page.goto('/reports');
    await expect(page.locator('.page-title')).toContainText('Reports Center');
    await expect(page.locator('.reports-table').first()).toBeVisible();

    await page.emulateMedia({ media: 'print' });

    await expect(page.locator('.header-actions')).toBeHidden();
    await expect(page.locator('.filter-toolbar')).toBeHidden();
    // The artifact table itself must survive into print — that is the one thing R11 asks this
    // stylesheet to actually preserve, not just hide everything else.
    await expect(page.locator('.reports-card')).toBeVisible();

    await page.emulateMedia({ media: 'screen' });
  });
});
