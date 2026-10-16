import { expect, test, type Page } from '@playwright/test';
import { apiAsUser, createIsolatedWorkspace, createTestProduct, createTestSupplier, signIn } from './support/api';
import { openAsyncSelect } from './support/select';

test.use({ timezoneId: 'Africa/Cairo' });

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

test('saves an RFQ with the picked local calendar day', async ({ page }) => {
  const credentials = await createIsolatedWorkspace();
  const token = await signIn(credentials.ownerEmail, credentials.ownerPassword);
  const product = await createTestProduct(token, { tenant_name: `Date RFQ Product ${Date.now()}` });
  const supplier = await createTestSupplier(token, `Date RFQ Supplier ${Date.now()}`);
  await apiAsUser(token, 'PATCH', `/suppliers/${supplier.id}`, { contact_email: 'quotes@example.test' });
  await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);
  await page.goto('/rfq/create');

  await openAsyncSelect(page, page.locator('mat-select[formControlName="workspace_product_id"]'));
  await page.locator('mat-option', { hasText: product.tenant_name }).click();
  await page.locator('input[formControlName="quantity"]').fill('2');
  await openAsyncSelect(page, page.locator('mat-select[formControlName="supplierIds"]'));
  await page.locator('mat-option', { hasText: supplier.name }).click();
  await page.keyboard.press('Escape');
  await page.locator('input[formControlName="neededByDate"]').click();
  await page.getByRole('button', { name: 'October 20, 2026' }).click();

  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/rfq') && response.request().method() === 'POST');
  await page.getByRole('button', { name: /save draft/i }).click();
  const response = await responsePromise;
  expect(response.status()).toBeLessThan(300);
  expect((response.request().postDataJSON() as { needed_by_date: string }).needed_by_date).toBe('2026-10-20');
  await expect(page.getByRole('alert')).toHaveCount(0);
});
