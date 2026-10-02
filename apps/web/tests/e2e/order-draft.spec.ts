import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

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

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function runAxe(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
}

test.describe('Order Draft (US4)', () => {
  test('creates, edits, and cancels a draft order with zero a11y violations', async ({ page }) => {
    const credentials = await createIsolatedWorkspace();
    const token = await signIn(credentials.ownerEmail, credentials.ownerPassword);
    const supplier = await createTestSupplier(token, `E2E Draft Supplier ${Date.now()}`);
    const product = await createTestProduct(token, { tenant_name: `E2E Draft Product ${Date.now()}` });
    const order = await createTestOrder(token, { supplier_id: supplier.id, product_id: product.id }); // This might create a draft order, let's assume so based on the other spec, or we can just start from order details of a draft order.
    
    // Sign in and go to the order
    await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);
    
    // Go to order detail
    await page.goto(`/orders/${order.id}`);
    await expect(page.locator('.status-chip')).toContainText('Draft');
    
    // Check accessibility on order detail
    const detailA11y = await runAxe(page);
    expect(detailA11y.violations).toEqual([]);

    // Click edit
    await page.locator('[data-testid="edit-order"]').click();
    await expect(page).toHaveURL(new RegExp(`/orders/${order.id}/edit$`));

    // Wait for form
    await expect(page.locator('input[formControlName="order_number"]')).toBeVisible();
    
    // Check accessibility on edit form
    const editA11y = await runAxe(page);
    expect(editA11y.violations).toEqual([]);

    // We can cancel back to order list
    await page.getByRole('button', { name: /cancel/i }).first().click();
    await expect(page).toHaveURL(new RegExp(`/orders$`));

    // Go back to order detail to cancel the order
    await page.goto(`/orders/${order.id}`);

    // Cancel the order
    await page.locator('[data-testid="cancel-order"]').click();
    await expect(page.locator('.cancel-form')).toBeVisible();

    // Confirm cancel
    const cancelResponse = page.waitForResponse(
      (response) => response.url().endsWith(`/orders/${order.id}/cancel`) && response.request().method() === 'POST',
    );
    await page.locator('[data-testid="confirm-cancel"]').click();
    expect((await cancelResponse).status()).toBe(200);

    await expect(page.locator('.status-chip')).toContainText('Cancelled');
  });
});
