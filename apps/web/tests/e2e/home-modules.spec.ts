import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

import { apiAsUser, createIsolatedWorkspace, signIn } from './support/api';

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

const EXPECTED_MODULE_PATHS = [
  '/quotations',
  '/rfq/history',
  '/offers/compare',
  '/requests',
  '/approvals',
  '/orders',
  '/savings',
  '/analyst',
  '/products',
  '/suppliers',
];

test.describe('Home Modules & Localized Config Labels', () => {
  test('renders module links and localized config labels in English and Arabic with zero axe violations', async ({
    page,
  }) => {
    const credentials = await createIsolatedWorkspace();
    const token = await signIn(credentials.ownerEmail, credentials.ownerPassword);
    const tenant = await apiAsUser<{ tax_model: string }>(token, 'GET', '/tenant');
    const config = await apiAsUser<{
      tax_models: readonly { code: string; label_en: string; label_ar: string }[];
    }>(token, 'GET', '/reference/config-options');
    const taxModel = config.tax_models.find((option) => option.code === tenant.tax_model);
    expect(taxModel).toBeDefined();
    await signInUi(page, credentials.ownerEmail, credentials.ownerPassword);
    await page.goto('/home');

    // English assertions
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    await expect(page.locator('.module-card')).toHaveCount(EXPECTED_MODULE_PATHS.length);

    await expect(page.locator('main, .home-container').first()).not.toContainText(
      /chunk|المرحلة\s*4/i,
    );
    await expect(page.getByTestId('home-tax-model-value')).toHaveText(taxModel!.label_en);

    for (const expectedPath of EXPECTED_MODULE_PATHS) {
      await expect(page.locator(`a.module-card[href="${expectedPath}"]`)).toBeVisible();
    }

    const enA11y = await runAxe(page);
    expect(enA11y.violations).toEqual([]);

    // Navigate via one of the module links and return to /home
    await page.locator('a.module-card[href="/rfq/history"]').click();
    await expect(page).toHaveURL(/\/rfq\/history$/);
    await page.goto('/home');

    // Switch to Arabic (RTL)
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');

    await expect(page.locator('.module-card')).toHaveCount(EXPECTED_MODULE_PATHS.length);
    await expect(page.locator('main, .home-container').first()).not.toContainText(
      /chunk|المرحلة\s*4/i,
    );
    await expect(page.getByTestId('home-tax-model-value')).toHaveText(taxModel!.label_ar);

    const arA11y = await runAxe(page);
    expect(arA11y.violations).toEqual([]);
  });
});
