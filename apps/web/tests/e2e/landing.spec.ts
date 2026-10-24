import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

/**
 * Guest Landing Page E2E Tests — PPS-35 & PPS-36.
 *
 * Requirements:
 * - Unauthenticated "/" displays the landing page (not a redirect to /auth/sign-in)
 * - Sign in navigates to /auth/sign-in
 * - RTL (ar) render has dir="rtl" and Arabic copy
 * - Runs as a guest without storageState
 * - Gallery tab switch changes the active image
 * - Enlarge opens a dialog and Escape closes it returning focus
 * - Iron Systems links point to https://www.iron-sys.com/ with rel noopener
 */
test.describe('Guest Landing Page (PPS-35 / PPS-36)', () => {
  test('unauthenticated "/" displays the landing page without redirecting', async ({ page }) => {
    await page.goto('/');

    // Verify URL remains "/" and does not redirect to /auth/sign-in
    await expect(page).toHaveURL(/\/$/);

    // Verify hero headline is visible
    const headline = page.locator('.hero-headline');
    await expect(headline).toBeVisible();
    await expect(headline).toContainText('Compare supplier quotes. Keep purchasing under control.');

    // Verify workflow section is rendered with four steps
    const stepCards = page.locator('.step-card');
    await expect(stepCards).toHaveCount(4);

    // Verify Gallery section is rendered with tabs
    const gallerySection = page.locator('.gallery-section');
    await expect(gallerySection).toBeVisible();

    // Verify hero request access CTA is primary and has mailto
    const requestAccess = page.locator('.hero-primary-btn');
    await expect(requestAccess).toBeVisible();
    await expect(requestAccess).toHaveAttribute('href', /^mailto:/);

    // Verify Iron Systems link
    const ironSysLinks = page.locator('a[href="https://www.iron-sys.com/"]');
    await expect(ironSysLinks.first()).toHaveAttribute('rel', /noopener/);
    await expect(ironSysLinks.first()).toHaveAttribute('target', '_blank');
  });

  test('gallery tab switch changes the displayed screenshot', async ({ page }) => {
    await page.goto('/');

    const galleryImage = page.locator('.gallery-section .gallery-image').first();
    await expect(galleryImage).toBeVisible();
    await expect(galleryImage).toHaveAttribute('src', /01-quotation-review\.jpg/);

    // Click the second tab (Smart Compare)
    const secondTab = page.locator('.gallery-tab-group .mat-mdc-tab').nth(1);
    await secondTab.click();

    // Check that gallery image switches to 02-smart-compare.jpg
    const activeGalleryImage = page.locator('.mat-mdc-tab-body-active .gallery-image');
    await expect(activeGalleryImage).toHaveAttribute('src', /02-smart-compare\.jpg/);
  });

  test('Enlarge opens a dialog and Escape closes it returning focus', async ({ page }) => {
    await page.goto('/');

    const enlargeBtn = page.locator('.mat-mdc-tab-body-active .enlarge-button').first();
    await expect(enlargeBtn).toBeVisible();
    await enlargeBtn.focus();
    await enlargeBtn.click();

    // Verify dialog with accessible name matching the screenshot caption is visible
    const captionText =
      'Check extracted details beside the source document and resolve fields that need attention.';
    const dialog = page.getByRole('dialog', { name: captionText });
    await expect(dialog).toBeVisible();

    // Verify no accessibility violations while dialog is open
    const axeResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(axeResults.violations).toEqual([]);

    // Close via Escape key
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);

    // Verify focus is returned to the trigger button
    await expect(enlargeBtn).toBeFocused();
  });

  test('header Sign in button navigates to /auth/sign-in', async ({ page }) => {
    await page.goto('/');

    const headerSignIn = page.locator('.header-signin-btn');
    await expect(headerSignIn).toBeVisible();
    await headerSignIn.click();

    await page.waitForURL('**/auth/sign-in');
    await expect(page).toHaveURL(/\/auth\/sign-in$/);
  });

  test('footer Sign in link navigates to /auth/sign-in', async ({ page }) => {
    await page.goto('/');

    const footerSignIn = page.locator('.footer-signin-link');
    await expect(footerSignIn).toBeVisible();
    await footerSignIn.click();

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
    await expect(headline).toContainText('قارن عروض الموردين، وأحكم متابعة مشترياتك.');
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
    await expect(headline).toContainText('قارن عروض الموردين، وأحكم متابعة مشترياتك.');

    await page.reload();
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');
    await expect(headline).toContainText('قارن عروض الموردين، وأحكم متابعة مشترياتك.');

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
