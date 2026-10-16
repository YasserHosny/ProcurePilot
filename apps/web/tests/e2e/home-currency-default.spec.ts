import { test, expect, type Page } from '@playwright/test';

import {
  apiAsUser,
  createIsolatedWorkspace,
  createTestProduct,
  createTestSupplier,
  signIn,
} from './support/api';
import { openAsyncSelect } from './support/select';

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

test('uses the workspace home currency as the default without overriding explicit choices', async ({ page }) => {
  const credentials = await createIsolatedWorkspace('EGP');
  const ownerToken = await signIn(credentials.ownerEmail, credentials.ownerPassword);
  const supplier = await createTestSupplier(ownerToken, `E2E Currency Supplier ${Date.now()}`);
  const product = await createTestProduct(ownerToken, { tenant_name: `E2E Currency Product ${Date.now()}` });
  await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);

  await page.goto('/orders/new');
  const orderCurrency = page.locator('input[formControlName="currency"]');
  await expect(orderCurrency).toHaveValue('EGP');
  await orderCurrency.fill('USD');
  const orderNumber = `E2E-CURRENCY-DEFAULT-${Date.now()}`;
  await page.locator('input[formControlName="order_number"]').fill(orderNumber);
  await expect(orderCurrency).toHaveValue('USD');

  const supplierSelect = page.locator('mat-select[formControlName="supplier_id"]');
  await openAsyncSelect(page, supplierSelect);
  await page.getByRole('option', { name: supplier.name, exact: true }).click();

  const productSelect = page.locator('mat-select[formControlName="workspace_product_id"]');
  await openAsyncSelect(page, productSelect);
  await page.getByRole('option', { name: product.tenant_name, exact: true }).click();
  await page.locator('input[formControlName="quantity"]').fill('2');
  await page.locator('input[formControlName="unit_price"]').fill('12.50');

  const createOrderResponse = page.waitForResponse((response) =>
    response.url().endsWith('/orders') &&
    response.request().method() === 'POST' &&
    response.status() >= 200 && response.status() < 300,
  );
  await page.locator('form button[type="submit"]').click();
  const createdOrder = await createOrderResponse;
  const orderPayload = (await createdOrder.json()) as { id: string };
  await expect(page).toHaveURL(new RegExp(`/orders/${orderPayload.id}$`));

  const persisted = await apiAsUser<{ order: { order_number: string; total: { currency: string } } }>(
    ownerToken,
    'GET',
    `/orders/${orderPayload.id}`,
  );
  expect(persisted.order.order_number).toBe(orderNumber);
  expect(persisted.order.total.currency).toBe('USD');

  await page.goto('/rfq/guardrails');
  const guardrailCurrency = page.locator('mat-form-field').filter({ hasText: 'Currency' }).locator('mat-select');
  await expect(guardrailCurrency).toContainText('EGP');

  await page.goto('/suppliers/new');
  const minimumOrderCurrency = page.locator('mat-select[formControlName="min_order_currency"]');
  const deliveryFeeCurrency = page.locator('mat-select[formControlName="delivery_fee_currency"]');
  await expect(minimumOrderCurrency).toBeVisible();
  await expect(deliveryFeeCurrency).toBeVisible();

  await openAsyncSelect(page, minimumOrderCurrency);
  await expect(page.locator('mat-option.mat-mdc-option[aria-selected="true"]')).toContainText('EGP');
  await page.keyboard.press('Escape');

  await openAsyncSelect(page, deliveryFeeCurrency);
  await expect(page.locator('mat-option.mat-mdc-option[aria-selected="true"]')).toContainText('EGP');
});
