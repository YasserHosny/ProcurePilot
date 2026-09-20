import { test, expect, type Page } from '@playwright/test';

import {
  createIsolatedWorkspace,
  createTestOrder,
  createTestProduct,
  createTestSupplier,
  signIn,
} from './support/api';

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

test.describe('Order tracking (R3.3)', () => {
  test('tracks order through confirmation and delivery evidence', async ({ page }) => {
    const credentials = await createIsolatedWorkspace();
    const token = await signIn(credentials.ownerEmail, credentials.ownerPassword);
    const supplier = await createTestSupplier(token, `E2E Order Supplier ${Date.now()}`);
    const product = await createTestProduct(token, { tenant_name: `E2E Delivery Paper ${Date.now()}` });
    const order = await createTestOrder(token, { supplier_id: supplier.id, product_id: product.id });

    await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);
    await page.goto('/orders');
    await expect(page.locator('[data-testid="orders-list"]')).toContainText(order.order_number);
    await page.getByRole('link', { name: new RegExp(order.order_number) }).first().click();
    await expect(page).toHaveURL(new RegExp(`/orders/${order.id}$`));
    await expect(page.locator('.evidence-value[data-state="pending"]')).toHaveCount(2);

    const submitResponse = page.waitForResponse(
      (response) => response.url().endsWith(`/orders/${order.id}/submit`) && response.request().method() === 'POST',
    );
    await page.locator('[data-testid="submit-order"]').click();
    expect((await submitResponse).status()).toBe(200);
    await expect(page.locator('.status-chip')).toContainText('Submitted');

    await page.locator('[data-testid="open-confirmation-form"]').click();
    await page.locator('input[name="confirmationReference"]').fill('SUP-CONF-1001');
    await page.locator('input[name="confirmationDate"]').fill(new Date().toISOString().slice(0, 10));
    await page.locator('input[name^="confirmation-"]').fill('10');
    const confirmationResponse = page.waitForResponse(
      (response) => response.url().endsWith(`/orders/${order.id}/confirmations`) && response.request().method() === 'POST',
    );
    await page.locator('[data-testid="save-confirmation"]').click();
    expect((await confirmationResponse).status()).toBe(200);
    await expect(page.locator('[data-testid="order-lines"]')).toContainText('10');

    await page.locator('[data-testid="open-receipt-form"]').click();
    await page.locator('input[name="receiptReference"]').fill('GRN-1001');
    await page.locator('input[name="receiptDate"]').fill(new Date().toISOString().slice(0, 10));
    await page.locator('input[name^="receipt-"]').fill('6');
    const receiptResponse = page.waitForResponse(
      (response) => response.url().endsWith(`/orders/${order.id}/receipts`) && response.request().method() === 'POST',
    );
    await page.locator('[data-testid="save-receipt"]').click();
    expect((await receiptResponse).status()).toBe(200);
    await expect(page.locator('.status-chip')).toContainText('Partially received');
    await expect(page.locator('.timeline')).toContainText('GRN-1001');
  });
});
