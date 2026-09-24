import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import {
  credentials,
  type Credentials,
  signInOwner,
  apiAsUser,
  createTestProduct,
  createTestSupplier,
  createTestOrder,
} from './support/api';

/**
 * Accessibility for the Grounded Procurement Analyst (R4.2, T036).
 *
 * WCAG 2.1 AA across the analyst surfaces in both English and Arabic (RTL):
 * 1. Ask a question (/analyst) — empty state and a cited, calculated answer
 * 2. Question history (/analyst/history) — with at least one past conversation
 *
 * Asserted with zero violations using data seeded via API helpers, matching the
 * pattern already established in requests-a11y.spec.ts.
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

test.describe('Grounded Procurement Analyst Accessibility @a11y', () => {
  let workspace: Credentials;
  let ownerToken: string;

  test.beforeAll(async () => {
    workspace = credentials();
    ownerToken = await signInOwner();

    // Seed one purchase order so a spend_savings question is grounded with a real citation.
    const product = await createTestProduct(ownerToken, {
      tenant_name: `A11y Analyst Item ${Date.now()}`,
    });
    const supplier = await createTestSupplier(ownerToken, `A11y Analyst Supplier ${Date.now()}`);
    await createTestOrder(ownerToken, { supplier_id: supplier.id, product_id: product.id });

    // Seed one past conversation so the history page has a real item to render.
    await apiAsUser(
      ownerToken,
      'POST',
      '/analyst/conversations',
      { question_text: 'How much have we spent this month?' },
      { 'Idempotency-Key': crypto.randomUUID() },
    );
  });

  async function signInUser(page: Page) {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', workspace.ownerEmail);
    await page.fill('input[formControlName="password"]', workspace.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  }

  async function ensureEnglish(page: Page) {
    if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
      await page.click('.account-btn');
      await page.locator('button[mat-menu-item]', { hasText: 'English' }).click();
      await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    }
  }

  async function switchToArabic(page: Page) {
    if ((await page.locator('html').getAttribute('dir')) !== 'rtl') {
      await page.click('.account-btn');
      await page.locator('button[mat-menu-item]', { hasText: 'العربية' }).click();
      await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    }
  }

  // --- English WCAG 2.1 AA Scans ---

  test('the ask-a-question empty state in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/analyst');
    await expect(page.locator('.page-title')).toContainText('Procurement Analyst');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('a cited, calculated answer in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/analyst');
    await page
      .locator('[data-testid="analyst-question-input"]')
      .fill('How much have we spent this month?');
    await page.locator('[data-testid="analyst-ask-button"]').click();
    await expect(page.locator('[data-testid="analyst-turn"]').first()).toBeVisible();
    // Expand the calculation panel so its content is also in scope for the scan.
    await page.locator('.calculation-panel mat-expansion-panel-header').first().click();
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the question history screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await ensureEnglish(page);
    await page.goto('/analyst/history');
    await expect(page.locator('[data-testid="analyst-history-item"]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // --- Arabic (RTL) WCAG 2.1 AA Scans ---
  // Declared after English scans so persisted locale changes do not affect earlier tests.

  test('the ask-a-question empty state in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/analyst');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.page-title')).toContainText('محلل المشتريات');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('a cited, calculated answer in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/analyst');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    // The deployed intent provider is the deterministic English-keyword stub (no
    // ANALYST_INTENT_PROVIDER_MODE=bedrock configured here), so the question text stays
    // English — this scan is exercising the RTL rendering of the answer/citation/
    // calculation UI, not Arabic-language question understanding, which R4.2 does not
    // claim to support.
    await page
      .locator('[data-testid="analyst-question-input"]')
      .fill('How much have we spent this month?');
    await page.locator('[data-testid="analyst-ask-button"]').click();
    await expect(page.locator('[data-testid="analyst-turn"]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the question history screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInUser(page);
    await switchToArabic(page);
    await page.goto('/analyst/history');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('h1')).toContainText('سجل الأسئلة');
    await page.waitForLoadState('networkidle');
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });
});
