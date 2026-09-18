import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page, type Browser } from '@playwright/test';

import {
  apiAsUser,
  credentials,
  setOwnerLocale,
  signInOwner,
} from './support/api';

/**
 * Accessibility & RTL test suite for Accounting Integration (014-accounting-integration, T037).
 *
 * Covers:
 * 1. Axe-core WCAG 2.1 AA scan in English AND Arabic across all three accounting screens:
 *    - /accounting (Connection Settings)
 *    - /accounting/bills (Synced Bills & Invoices)
 *    - /accounting/discrepancies (Reconciliation Discrepancies)
 * 2. Keyboard navigation for the resolve-discrepancy action on /accounting/discrepancies:
 *    proving keyboard-only users can navigate to the resolve button, activate it,
 *    input an optional resolution note, and confirm resolution using keyboard only.
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: Page) {
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

/**
 * Activates any Angular production-inlined stylesheets whose media attribute defaults to "print"
 * so full styles and RTL transform rules apply reliably during scans.
 */
async function ensureStyles(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"][media="print"]').forEach((el) => {
      el.media = 'all';
    });
  });
}

async function ensureEnglish(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
    await page.click('.account-btn');
    await page.click('button:has-text("English")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  }
  await ensureStyles(page);
}

async function switchToArabic(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) !== 'rtl') {
    await page.click('.account-btn');
    await page.locator('button:has-text("العربية")').click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.mat-mdc-menu-panel')).toHaveCount(0);
  }
  await ensureStyles(page);
}

type StoredSession = Awaited<ReturnType<Page['context']['storageState']>>;

test.describe('Accounting Accessibility & RTL (014-accounting-integration, T037) @a11y', () => {
  let ownerCreds: { ownerEmail: string; ownerPassword: string };
  let ownerStorage: StoredSession;
  let ownerToken: string;

  test.beforeAll(async ({ browser }: { browser: Browser }) => {
    try {
      await setOwnerLocale('en');
    } catch {
      // Ignore if owner session is not initialized yet
    }
    ownerCreds = credentials();
    ownerToken = await signInOwner();

    // Ensure connection is active and bills/discrepancies are synced so screens test populated states
    try {
      let needsConnect = false;
      try {
        const conn = await apiAsUser<{ status: string }>(ownerToken, 'GET', '/accounting/connection');
        if (conn.status !== 'active') {
          needsConnect = true;
        }
      } catch {
        needsConnect = true;
      }

      if (needsConnect) {
        const startRes = await apiAsUser<{ authorization_url: string }>(
          ownerToken,
          'POST',
          '/accounting/connect',
        );
        const authUrl = new URL(startRes.authorization_url);
        const state = authUrl.searchParams.get('state');
        const apiBase = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';
        await fetch(
          `${apiBase}/accounting/connect/callback?code=stub-auth-code&realmId=stub-realm-12345&state=${state}`,
          { redirect: 'manual' },
        );
      }

      // Check if bills or discrepancies exist; if not, trigger sync
      const bills = await apiAsUser<{ items: unknown[] }>(ownerToken, 'GET', '/accounting/bills');
      if (bills.items.length === 0) {
        await apiAsUser(ownerToken, 'POST', '/accounting/sync');
      }
    } catch {
      // Best-effort setup; tests will still navigate and assert
    }

    // Capture owner authenticated storage state once to avoid repeated sign-ins
    const ownerCtx = await browser.newContext();
    const ownerPage = await ownerCtx.newPage();
    await ownerPage.goto('/auth/sign-in');
    await ownerPage.fill('input[formControlName="email"]', ownerCreds.ownerEmail);
    await ownerPage.fill('input[formControlName="password"]', ownerCreds.ownerPassword);
    await ownerPage.click('button[type="submit"]');
    await ownerPage.waitForURL('**/home');
    ownerStorage = await ownerCtx.storageState();
    await ownerCtx.close();
  });

  async function applySession(page: Page, storage: StoredSession): Promise<void> {
    await page.context().addCookies(storage.cookies);
    for (const origin of storage.origins) {
      await page.addInitScript(
        ({ originData }) => {
          for (const item of originData.localStorage) {
            localStorage.setItem(item.name, item.value);
          }
        },
        { originData: origin },
      );
    }
  }

  async function signInOwnerSession(page: Page): Promise<void> {
    await applySession(page, ownerStorage);
    await ensureStyles(page);
  }

  // =========================================================================
  // Section A: English Axe-core WCAG 2.1 AA Scans (3 screens)
  // =========================================================================

  test('Accounting connection settings screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/accounting');
    await ensureEnglish(page);
    await expect(page.locator('.page-title')).toContainText('Accounting Integration');
    await page.waitForLoadState('networkidle');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Accounting bills list screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/accounting/bills');
    await ensureEnglish(page);
    await expect(page.locator('.page-title')).toContainText('Synced Bills & Invoices');
    await page.waitForLoadState('networkidle');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Accounting discrepancies screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/accounting/discrepancies');
    await ensureEnglish(page);
    await expect(page.locator('.page-title')).toContainText('Reconciliation Discrepancies');
    await page.waitForLoadState('networkidle');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // =========================================================================
  // Section B: Keyboard Navigation for Resolve Discrepancy Action
  // =========================================================================

  test('Keyboard navigation: resolve-discrepancy action from open discrepancies list @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/accounting/discrepancies');
    await ensureEnglish(page);
    await expect(page.locator('.page-title')).toContainText('Reconciliation Discrepancies');
    await page.waitForLoadState('networkidle');

    // Find the first open discrepancy's resolve button
    const resolveBtn = page.locator('[data-testid="resolve-btn"]').first();
    await expect(resolveBtn).toBeVisible();

    // Start navigation from the page back link and tab forward
    const backLink = page.locator('.back-link a');
    await backLink.focus();
    await expect(backLink).toBeFocused();

    // Tab through until reaching the resolve action button
    let reachedResolve = false;
    for (let i = 0; i < 15; i++) {
      await page.keyboard.press('Tab');
      if (await resolveBtn.evaluate((el) => el === document.activeElement)) {
        reachedResolve = true;
        break;
      }
    }
    expect(reachedResolve).toBe(true);

    // Activate the resolve action using keyboard Enter
    await page.keyboard.press('Enter');

    // Inline resolve form should open with note input focused
    const resolveNoteInput = page.locator('[data-testid="resolve-note-input"]');
    await expect(resolveNoteInput).toBeVisible();
    await expect(resolveNoteInput).toBeFocused();

    // Type a resolution note via keyboard
    await page.keyboard.type('A11y verified keyboard discrepancy resolution note');

    // Tab from note input to the Cancel button, then Tab to Confirm button
    await page.keyboard.press('Tab');
    const cancelBtn = page.locator('[data-testid="cancel-resolve-btn"]');
    await expect(cancelBtn).toBeFocused();

    await page.keyboard.press('Tab');
    const confirmBtn = page.locator('[data-testid="confirm-resolve-btn"]');
    await expect(confirmBtn).toBeFocused();

    // Activate confirm resolution via keyboard Enter
    await page.keyboard.press('Enter');

    // Assert the resolve form closes and a success message appears
    await expect(page.locator('[data-testid="inline-resolve-form"]')).toHaveCount(0);
    await expect(page.locator('.mat-mdc-snack-bar-container')).toBeVisible({ timeout: 5000 });
  });

  // =========================================================================
  // Section C: Arabic Axe-core WCAG 2.1 AA Scans (3 screens)
  // =========================================================================

  test('Accounting connection settings screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/accounting');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await page.waitForLoadState('networkidle');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Accounting bills list screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/accounting/bills');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await page.waitForLoadState('networkidle');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('Accounting discrepancies screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/accounting/discrepancies');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await page.waitForLoadState('networkidle');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
