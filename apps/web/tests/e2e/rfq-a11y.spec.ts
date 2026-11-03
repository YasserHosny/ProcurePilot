import { randomUUID } from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import {
  apiAsUser,
  createMember,
  createTestProduct,
  createTestSupplier,
  signIn,
  type CreatedMember,
} from './support/api';

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

async function expectAccessible(page: Page): Promise<void> {
  const results = await scan(page);
  expect(results.violations, describeViolations(results)).toEqual([]);
}

async function signInUi(page: Page, member: CreatedMember, locale: 'en' | 'ar'): Promise<void> {
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', member.email);
  await page.fill('input[formControlName="password"]', member.password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
  if (locale === 'ar') {
    await page.click('.account-btn');
    const localeSave = page.waitForResponse((response) =>
      response.request().method() === 'PATCH' &&
      new URL(response.url()).pathname.endsWith('/me') && response.ok(),
    );
    await page.getByRole('menuitem', { name: /العربية/ }).click();
    await localeSave;
  }
  await expect(page.locator('html')).toHaveAttribute('lang', locale);
  await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr');
}

// support/api has product/supplier helpers but no RFQ seed helper. Keep this
// minimal draft local: no email delivery or additional API endpoints are needed.
async function seedRfqWithRecipient(member: CreatedMember): Promise<string> {
  const token = await signIn(member.email, member.password);
  const product = await createTestProduct(token);
  const supplier = await createTestSupplier(token, undefined, 'rfq-a11y@example.test');
  const result = await apiAsUser<{ rfq: { id: string } }>(token, 'POST', '/rfq', {
    lines: [{ workspace_product_id: product.id, quantity: '5' }],
    recipient_supplier_ids: [supplier.id],
    needed_by_date: new Date(Date.now() + 30 * 86400_000).toISOString().slice(0, 10),
    tenant_terms: 'RFQ accessibility fixture',
  }, { 'Idempotency-Key': randomUUID() });
  return result.rfq.id;
}

for (const locale of ['en', 'ar'] as const) {
  test.describe(`RFQ accessibility (${locale}) @a11y`, () => {
    test('History and open recipients dialog have no WCAG 2.1 AA violations', async ({ page }) => {
      const member = await createMember('buyer');
      const rfqId = await seedRfqWithRecipient(member);
      await signInUi(page, member, locale);
      await page.goto('/rfq/history');
      const trigger = page.locator(`[data-testid="rfq-recipients-button"][aria-controls="rfq-recipients-${rfqId}"]`);
      await expect(trigger).toBeVisible();
      await expectAccessible(page);

      await trigger.click();
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();
      await expect(trigger).toHaveAttribute('aria-expanded', 'true');
      await expect(dialog.locator('.recipient-row')).toHaveCount(1);
      await expectAccessible(page);
      await page.keyboard.press('Tab');
      await expect(dialog.locator('.view-all-link')).toBeFocused();
      await page.keyboard.press('Escape');
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
    });

    test('Create has no WCAG 2.1 AA violations', async ({ page }) => {
      const member = await createMember('buyer');
      await signInUi(page, member, locale);
      await page.goto('/rfq/create');
      await expect(page.locator('.rfq-form')).toBeVisible();
      await expect(page.locator('.rfq-form button[type="submit"]')).toBeEnabled();
      await expect(page.locator('.rfq-form input[formControlName="workspace_product_id"]')).toBeVisible();
      await expectAccessible(page);
    });

    for (const [index, tab] of ['details', 'items', 'recipients', 'responses'].entries()) {
      test(`Detail ${tab} tab has no WCAG 2.1 AA violations`, async ({ page }) => {
        const member = await createMember('buyer');
        const rfqId = await seedRfqWithRecipient(member);
        await signInUi(page, member, locale);
        await page.goto(`/rfq/${rfqId}?tab=${tab}`);
        const selectedTab = page.getByRole('tab').nth(index);
        await expect(selectedTab).toHaveAttribute('aria-selected', 'true');
        await expect(page.getByRole('tabpanel')).toBeVisible();
        await expect(page.locator('app-rfq-detail mat-spinner')).toHaveCount(0);
        await expectAccessible(page);
      });
    }

    test('Guardrails has no WCAG 2.1 AA violations', async ({ page }) => {
      const member = await createMember('owner');
      await signInUi(page, member, locale);
      await Promise.all([
        page.waitForResponse((response) =>
          response.request().method() === 'GET' &&
          new URL(response.url()).pathname.endsWith('/rfq/guardrails') && response.ok(),
        ),
        page.goto('/rfq/guardrails'),
      ]);
      await expect(page.locator('app-rfq-guardrails .form-card')).toBeVisible();
      await expect(page.locator('app-rfq-guardrails mat-spinner')).toHaveCount(0);
      await expectAccessible(page);
    });
  });
}
