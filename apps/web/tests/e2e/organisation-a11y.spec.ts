import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import { createIsolatedWorkspace, type Credentials } from './support/api';

/**
 * Accessibility for the Organisation Settings screen (chunk 007, T043, FR-011).
 *
 * WCAG 2.1 AA on /settings in both English and Arabic (RTL), asserted with zero violations.
 *
 * Signed in as the tenant owner (via an isolated workspace, not the shared global-setup member)
 * so every owner-gated "create" action across the branch/cost-centre/budget sections actually
 * renders — a buyer or viewer sign-in would hide those buttons entirely and scan a smaller
 * surface than the screen a real owner sees.
 */
const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_21_AA).exclude('.nav-item.disabled').analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

test.describe('Organisation Settings Accessibility @a11y', () => {
  let workspace: Credentials;

  test.beforeAll(async () => {
    workspace = await createIsolatedWorkspace();
  });

  async function signIn(page: Page) {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', workspace.ownerEmail);
    await page.fill('input[formControlName="password"]', workspace.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  }

  /**
   * Language choice persists server-side on the owner's profile (preferred_locale), and this
   * file reuses one owner across every test — so an English test that runs after the Arabic
   * scan below must not just skip switching, it must switch BACK, or it inherits Arabic from
   * the owner's last saved preference.
   */
  async function ensureEnglish(page: Page) {
    if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
      await page.click('.account-btn');
      await page.click('button:has-text("English")');
      await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    }
  }

  test('the organisation settings screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signIn(page);
    await ensureEnglish(page);
    await page.goto('/settings');
    await expect(page.locator('.settings-title')).toContainText('Organisation Settings');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the create-branch dialog in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signIn(page);
    await ensureEnglish(page);
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await page.click('app-branch-list button:has-text("New Branch")');
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the create-cost-centre dialog in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signIn(page);
    await ensureEnglish(page);
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await page.click('app-cost-centre-list button:has-text("New Cost Centre")');
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the create-budget dialog in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signIn(page);
    await ensureEnglish(page);
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await page.click('app-budget-list button:has-text("Define Budget")');
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // Declared last: switching to Arabic here persists server-side to the shared owner's
  // preferred_locale (see ensureEnglish above), so every test that needs English must run
  // before this one.
  test('the organisation settings screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signIn(page);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await page.goto('/settings');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
