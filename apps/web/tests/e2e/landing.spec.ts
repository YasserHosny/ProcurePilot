import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

/**
 * Guest Landing Page E2E Tests — PPS-37 (Landing v2).
 *
 * Guarantees:
 * - Unauthenticated "/" displays the landing page (not a redirect to /auth/sign-in)
 * - Sign in navigates to /auth/sign-in
 * - Iron Systems links point to https://www.iron-sys.com/ with rel noopener
 * - RTL (ar) render has dir="rtl" and Arabic copy
 * - Language toggle flow between EN and Arabic
 * - Screenshot dialog named by caption + axe scan while open + focus return
 * - Next button scrolls the rail so card 2 becomes active
 * - Keyboard ArrowRight on the rail does the same
 * - In Arabic the rail starts at the right and "next" moves leftwards
 * - No horizontal page scroll at 375px
 */
test.describe('Guest Landing Page (PPS-37)', () => {
  test('unauthenticated "/" displays the landing page without redirecting', async ({ page }) => {
    await page.goto('/');

    // Verify URL remains "/" and does not redirect to /auth/sign-in
    await expect(page).toHaveURL(/\/$/);

    // Verify hero headline is visible
    const headline = page.locator('.hero-headline');
    await expect(headline).toBeVisible();
    await expect(headline).toContainText('Every supplier price, traced to the quote it came from.');

    // Verify workflow section is rendered with four steps
    const stepCards = page.locator('.step-card');
    await expect(stepCards).toHaveCount(4);

    // Verify Gallery section is rendered
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

  test('next button scrolls the rail so card 2 becomes active', async ({ page }) => {
    await page.goto('/');

    const step1 = page.locator('.gallery-step-btn').nth(0);
    const step2 = page.locator('.gallery-step-btn').nth(1);
    await expect(step1).toHaveClass(/active/);

    const nextBtn = page.locator('.gallery-nav-btn.next-btn');
    await nextBtn.click();

    await expect(step2).toHaveClass(/active/);
    const card2 = page.locator('.gallery-card').nth(1);
    await expect(card2).toHaveClass(/active/);
  });

  test('keyboard ArrowRight on the rail scrolls so card 2 becomes active', async ({ page }) => {
    await page.goto('/');

    const rail = page.locator('.gallery-rail');
    await rail.focus();
    await page.keyboard.press('ArrowRight');

    const step2 = page.locator('.gallery-step-btn').nth(1);
    await expect(step2).toHaveClass(/active/);
  });

  test('in Arabic the rail starts at the right and next moves leftwards', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('pp.locale', 'ar');
    });
    await page.reload();

    const rail = page.locator('.gallery-rail');
    const initialScrollLeft = await rail.evaluate((el) => el.scrollLeft);

    const nextBtn = page.locator('.gallery-nav-btn.next-btn');
    await nextBtn.click();

    const step2 = page.locator('.gallery-step-btn').nth(1);
    await expect(step2).toHaveClass(/active/);

    const newScrollLeft = await rail.evaluate((el) => el.scrollLeft);
    expect(newScrollLeft).toBeLessThanOrEqual(initialScrollLeft);
  });

  test('no horizontal page scroll at 375px', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    const hasHorizontalScroll = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(hasHorizontalScroll).toBe(false);
  });

  test('Enlarge opens a dialog named by caption, runs axe scan, and Escape closes it returning focus', async ({ page }) => {
    await page.goto('/');

    const enlargeBtn = page.locator('.gallery-card.active .gallery-enlarge-btn');
    await expect(enlargeBtn).toBeVisible();
    await enlargeBtn.focus();
    await enlargeBtn.click();

    // Wait for the dialog to be visible
    const dialog = page.locator('mat-dialog-container');
    await expect(dialog).toBeVisible();

    // Verify dialog is named by caption
    const dialogTitle = dialog.locator('[mat-dialog-title]');
    await expect(dialogTitle).toBeVisible();
    await expect(dialogTitle).toHaveText(/The supplier's PDF/i);

    // Run axe scan while dialog is open
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(results.violations).toEqual([]);

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
    await expect(headline).toContainText('كل سعر من مورديك، موثَّق بعرض السعر الذي جاء منه.');
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
    await expect(headline).toContainText('كل سعر من مورديك، موثَّق بعرض السعر الذي جاء منه.');

    await page.reload();
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');
    await expect(headline).toContainText('كل سعر من مورديك، موثَّق بعرض السعر الذي جاء منه.');

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
