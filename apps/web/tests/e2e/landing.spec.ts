import { test, expect } from '@playwright/test';

/**
 * Guest Landing Page E2E Tests — PPS-35.
 *
 * Requirements:
 * - Unauthenticated "/" displays the landing page (not a redirect to /auth/sign-in)
 * - Sign in navigates to /auth/sign-in
 * - RTL (ar) render has dir="rtl" and Arabic copy
 * - Runs as a guest without storageState
 */
test.describe('Guest Landing Page (PPS-35)', () => {
  test('unauthenticated "/" displays the landing page without redirecting', async ({ page }) => {
    await page.goto('/');

    // Verify URL remains "/" and does not redirect to /auth/sign-in
    await expect(page).toHaveURL(/\/$/);

    // Verify hero headline and lede are visible
    const headline = page.locator('.hero-headline');
    await expect(headline).toBeVisible();
    await expect(headline).toContainText('Every number traces back to the quote it came from.');

    // Verify How It Works section is rendered with three steps
    const stepCards = page.locator('.step-card');
    await expect(stepCards).toHaveCount(3);

    // Verify Gallery section is absent when screenshot cards array is empty
    await expect(page.locator('.gallery-section')).toHaveCount(0);

    // Verify support mailto links
    const requestAccess = page.locator('.hero-secondary-btn');
    await expect(requestAccess).toHaveAttribute('href', /^mailto:/);
  });

  test('Sign in action navigates to /auth/sign-in', async ({ page }) => {
    await page.goto('/');

    // Click hero primary Sign in button
    const heroSignIn = page.locator('.hero-primary-btn');
    await expect(heroSignIn).toBeVisible();
    await heroSignIn.click();

    await page.waitForURL('**/auth/sign-in');
    await expect(page).toHaveURL(/\/auth\/sign-in$/);
  });

  test('header Sign in button navigates to /auth/sign-in', async ({ page }) => {
    await page.goto('/');

    const headerSignIn = page.locator('.header-signin-btn');
    await expect(headerSignIn).toBeVisible();
    await headerSignIn.click();

    await page.waitForURL('**/auth/sign-in');
    await expect(page).toHaveURL(/\/auth\/sign-in$/);
  });

  test('renders in RTL and Arabic when Arabic locale is selected', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('pp.locale', 'ar');
    });
    await page.reload();

    const html = page.locator('html');
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');

    const headline = page.locator('.hero-headline');
    await expect(headline).toBeVisible();
    await expect(headline).toContainText('كل رقم يعود إلى عرض السعر الذي جاء منه.');
  });

  test('toggles language between EN and Arabic on public pages', async ({ page }) => {
    await page.goto('/');

    const html = page.locator('html');
    await expect(html).toHaveAttribute('dir', 'ltr');
    await expect(html).toHaveAttribute('lang', 'en');

    const landingToggle = page.getByRole('button', { name: 'عربي' });
    await expect(landingToggle).toBeVisible();
    await landingToggle.click();

    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');
    const headline = page.locator('.hero-headline');
    await expect(headline).toContainText('كل رقم يعود إلى عرض السعر الذي جاء منه.');

    await page.reload();
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');
    await expect(headline).toContainText('كل رقم يعود إلى عرض السعر الذي جاء منه.');

    await page.goto('/auth/sign-in');
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');

    const signinToggle = page.getByRole('button', { name: 'EN' });
    await expect(signinToggle).toBeVisible();
    await signinToggle.click();
    await expect(html).toHaveAttribute('dir', 'ltr');
    await expect(html).toHaveAttribute('lang', 'en');
  });
});
