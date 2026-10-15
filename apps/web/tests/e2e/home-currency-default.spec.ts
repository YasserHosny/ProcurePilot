import { test, expect, type Page } from '@playwright/test';

import { createIsolatedWorkspace } from './support/api';
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
  await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);

  await page.goto('/orders/new');
  const orderCurrency = page.locator('input[formControlName="currency"]');
  await expect(orderCurrency).toHaveValue('EGP');
  await orderCurrency.fill('USD');
  await page.locator('input[formControlName="order_number"]').fill('E2E-CURRENCY-DEFAULT');
  await expect(orderCurrency).toHaveValue('USD');

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
