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

  await page.locator('input[formControlName="workspace_product_id"]').fill(product.tenant_name);
  await page.locator('mat-option', { hasText: product.tenant_name }).click();
  await page.locator('input[formControlName="quantity"]').fill('2');
  await openAsyncSelect(page, page.locator('mat-select[formControlName="supplierIds"]'));
  await page.locator('mat-option', { hasText: supplier.name }).click();
  await page.keyboard.press('Escape');
  const targetDate = await page.evaluate(() => {
    const today = new Date();
    const target = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 14);
    const year = target.getFullYear();
    const month = String(target.getMonth() + 1).padStart(2, '0');
    const day = String(target.getDate()).padStart(2, '0');
    return {
      // The date picker is day-first outside the US region (AppDateAdapter), so its cells are
      // labelled en-GB style: "1 November 2026".
      accessibleName: target.toLocaleDateString('en-GB', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      }),
      expectedIsoDate: `${year}-${month}-${day}`,
      targetMonth: target.getMonth(),
      currentMonth: today.getMonth(),
      targetYear: year,
      currentYear: today.getFullYear(),
    };
  });
  await page.getByRole('button', { name: 'Open calendar' }).click();
  if (targetDate.targetYear > targetDate.currentYear || targetDate.targetMonth > targetDate.currentMonth) {
    await page.getByRole('button', { name: 'Next month' }).click();
  }
  await page.getByRole('button', { name: targetDate.accessibleName, exact: true }).click();

  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/rfq') && response.request().method() === 'POST');
  await page.getByRole('button', { name: /save draft/i }).click();
  const response = await responsePromise;
  expect(response.status()).toBeLessThan(300);
  expect((response.request().postDataJSON() as { needed_by_date: string }).needed_by_date).toBe(targetDate.expectedIsoDate);
  await expect(page.getByRole('alert')).toHaveCount(0);
});
