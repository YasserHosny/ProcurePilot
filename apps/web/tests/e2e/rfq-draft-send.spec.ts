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

async function createDraftRfq(token: string, productId: string, supplierId: string): Promise<void> {
  await apiAsUser(
    token,
    'POST',
    '/rfq',
    {
      lines: [{ workspace_product_id: productId, quantity: '5' }],
      recipient_supplier_ids: [supplierId],
      needed_by_date: '2026-12-15',
      tenant_terms: 'Standard delivery terms',
    },
    { 'Idempotency-Key': randomUUID() },
  );
}

test.describe('RFQ Draft Send from History', () => {
  test('sends a draft RFQ from history in English and Arabic with zero axe violations', async ({
    page,
  }) => {
    const credentials = await createIsolatedWorkspace();
    const token = await signIn(credentials.ownerEmail, credentials.ownerPassword);
    const product = await createTestProduct(token, {
      tenant_name: `RFQ Draft Product ${Date.now()}`,
    });
    const supplier = await createTestSupplier(token, `RFQ Draft Supplier ${Date.now()}`);
    await apiAsUser(token, 'PATCH', `/suppliers/${supplier.id}`, {
      contact_email: 'rfq-supplier@example.test',
    });

    // --- English flow ---
    await createDraftRfq(token, product.id, supplier.id);
    await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);
    await page.goto('/rfq/history');

    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    const enRow = page.locator('tr.mat-mdc-row').first();
    await expect(enRow.locator('[data-testid="rfq-sent-at-cell"]')).toHaveText('—');

    const enA11y = await runAxe(page);
    expect(enA11y.violations).toEqual([]);

    await enRow.locator('[data-testid="rfq-send-button"]').click();
    const dialog = page.locator('mat-dialog-container');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: /send rfq/i }).click();

    await expect(page.locator('mat-snack-bar-container')).toContainText(
      /RFQ sent to 1 suppliers/i,
    );
    await expect(enRow.locator('.status-badge')).toHaveText('Sent');
    await expect(enRow.locator('[data-testid="rfq-sent-at-cell"]')).not.toHaveText('—');

    // --- Arabic (RTL) flow ---
    await createDraftRfq(token, product.id, supplier.id);
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');

    await page.goto('/rfq/history');
    const arDraftRow = page
      .locator('tr.mat-mdc-row')
      .filter({ has: page.locator('[data-testid="rfq-send-button"]') })
      .first();
    await expect(arDraftRow.locator('[data-testid="rfq-sent-at-cell"]')).toHaveText('—');

    const arA11y = await runAxe(page);
    expect(arA11y.violations).toEqual([]);

    await arDraftRow.locator('[data-testid="rfq-send-button"]').click();
    const arDialog = page.locator('mat-dialog-container');
    await expect(arDialog).toBeVisible();
    await arDialog.getByRole('button', { name: /إرسال الطلب/ }).click();

    await expect(page.locator('mat-snack-bar-container')).toContainText(
      /تم إرسال طلب عرض الأسعار إلى 1 موردين/,
    );
    await expect(page.locator('tr.mat-mdc-row').first().locator('.status-badge')).toHaveText(
      'مرسل',
    );
    await expect(
      page.locator('tr.mat-mdc-row').first().locator('[data-testid="rfq-sent-at-cell"]'),
    ).not.toHaveText('—');
  });
});
