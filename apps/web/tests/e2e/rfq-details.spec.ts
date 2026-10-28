import { randomUUID } from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestProduct,
  createTestSupplier,
  signIn,
} from './support/api';

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

async function runAxe(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
}

test.describe('RFQ Details page', () => {
  test('navigates from history to RFQ details with tabs, breadcrumb, and zero axe violations', async ({
    page,
  }) => {
    const credentials = await createIsolatedWorkspace();
    const token = await signIn(credentials.ownerEmail, credentials.ownerPassword);

    const product1 = await createTestProduct(token, {
      tenant_name: `Zaatar Mix ${Date.now()}`,
    });
    const product2 = await createTestProduct(token, {
      tenant_name: `Basmati Rice ${Date.now()}`,
    });

    const supplier = await createTestSupplier(token, `Delta Produce ${Date.now()}`);
    await apiAsUser(token, 'PATCH', `/suppliers/${supplier.id}`, {
      contact_email: 'rfq-delta@example.test',
    });

    const rfqRes = await apiAsUser<{ rfq: { id: string } }>(
      token,
      'POST',
      '/rfq',
      {
        lines: [
          { workspace_product_id: product1.id, quantity: '10' },
          { workspace_product_id: product2.id, quantity: '20' },
        ],
        recipient_supplier_ids: [supplier.id],
        needed_by_date: '2026-12-15',
        tenant_terms: 'Payment terms: net 30 days.',
      },
      { 'Idempotency-Key': randomUUID() },
    );
    const rfqId = rfqRes.rfq.id;

    // Send the RFQ so row click routes to /rfq/:id
    await apiAsUser(token, 'POST', `/rfq/${rfqId}/send`, {}, { 'Idempotency-Key': randomUUID() });

    await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);
    await page.goto('/rfq/history');

    const row = page.locator('tr.mat-mdc-row').first();
    await expect(row).toBeVisible();
    await row.click();

    await expect(page).toHaveURL(new RegExp(`/rfq/${rfqId}(?:\\?.*)?$`));

    const breadcrumb = page.locator('nav.breadcrumb');
    await expect(breadcrumb).toBeVisible();
    await expect(breadcrumb.locator('.breadcrumb-link')).toHaveText(/RFQ History/i);

    const a11y = await runAxe(page);
    expect(a11y.violations).toEqual([]);

    // Verify Items tab in order
    await page.getByRole('tab', { name: /Items/i }).click();
    const itemRows = page.locator('[data-testid="detail-item-row"]');
    await expect(itemRows).toHaveCount(2);
    await expect(itemRows.nth(0)).toContainText(product1.tenant_name);
    await expect(itemRows.nth(1)).toContainText(product2.tenant_name);

    // Verify Recipients tab
    await page.getByRole('tab', { name: /Recipients/i }).click();
    const recipientRows = page.locator('[data-testid="detail-recipient-row"]');
    await expect(recipientRows).toHaveCount(1);
    await expect(recipientRows.first()).toContainText(supplier.name);

    // Breadcrumb link returns to RFQ History
    await breadcrumb.locator('.breadcrumb-link').click();
    await expect(page).toHaveURL(/\/rfq\/history$/);

    await expect(row).toBeVisible();
    await row.locator('[data-testid="rfq-actions-button"]').click();
    await expect(page.getByRole('menuitem', { name: /View details/i })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: /Compare responses/i })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: /Duplicate/i })).toBeVisible();
    await page.keyboard.press('Escape');
  });
});
