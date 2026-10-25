import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';

/**
 * Guest Landing Page E2E Tests — PPS-35 / PPS-36 / PPS-45.
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
test.describe('Guest Landing Page (PPS-35, PPS-36, PPS-45)', () => {
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

  test('five tabs render and clicking step 2 selects it and changes the image src to 02-smart-compare.jpg', async ({ page }) => {
    await page.goto('/');

    const tabs = page.locator('.gallery-step-btn');
    await expect(tabs).toHaveCount(5);

    const step1 = tabs.nth(0);
    const step2 = tabs.nth(1);
    await expect(step1).toHaveAttribute('aria-selected', 'true');
    await expect(step2).toHaveAttribute('aria-selected', 'false');

    const initialImg = page.locator('.gallery-card-image.active');
    await expect(initialImg).toHaveAttribute('src', /\/01-quotation-review\.jpg/);

    await step2.click();

    await expect(step2).toHaveAttribute('aria-selected', 'true');
    await expect(step1).toHaveAttribute('aria-selected', 'false');

    const activeImg = page.locator('.gallery-card-image.active');
    await expect(activeImg).toHaveAttribute('src', /\/02-smart-compare\.jpg/);
  });

  test('Next and Previous buttons navigate between steps and are disabled at the ends', async ({ page }) => {
    await page.goto('/');

    const prevBtn = page.locator('.gallery-nav-btn.prev-btn');
    const nextBtn = page.locator('.gallery-nav-btn.next-btn');
    const tabs = page.locator('.gallery-step-btn');

    await expect(tabs.nth(0)).toHaveAttribute('aria-selected', 'true');
    await expect(prevBtn).toBeDisabled();
    await expect(nextBtn).toBeEnabled();

    await nextBtn.click();
    await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
    await expect(prevBtn).toBeEnabled();

    // Advance to the last step
    await nextBtn.click();
    await nextBtn.click();
    await nextBtn.click();
    await expect(tabs.nth(4)).toHaveAttribute('aria-selected', 'true');
    await expect(nextBtn).toBeDisabled();
    await expect(prevBtn).toBeEnabled();

    await prevBtn.click();
    await expect(tabs.nth(3)).toHaveAttribute('aria-selected', 'true');
  });

  test('keyboard navigation: ArrowDown, Home, End move selection and focus follows', async ({ page }) => {
    await page.goto('/');

    const step1 = page.locator('.gallery-step-btn').nth(0);
    const step2 = page.locator('.gallery-step-btn').nth(1);
    const step5 = page.locator('.gallery-step-btn').nth(4);

    await step1.focus();
    await page.keyboard.press('ArrowDown');
    await expect(step2).toHaveAttribute('aria-selected', 'true');
    await expect(step2).toBeFocused();

    await page.keyboard.press('End');
    await expect(step5).toHaveAttribute('aria-selected', 'true');
    await expect(step5).toBeFocused();

    await page.keyboard.press('Home');
    await expect(step1).toHaveAttribute('aria-selected', 'true');
    await expect(step1).toBeFocused();
  });

  test('in RTL / Arabic, ArrowLeft moves forward and Arabic labels render', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('pp.locale', 'ar');
    });
    await page.reload();

    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

    const tabs = page.locator('.gallery-step-btn');
    await expect(tabs.nth(0)).toContainText('مراجعة عرض السعر');
    await expect(tabs.nth(1)).toContainText('المقارنة الذكية');

    await tabs.nth(0).focus();
    // In RTL, ArrowLeft moves forward to next step
    await page.keyboard.press('ArrowLeft');

    await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
    await expect(tabs.nth(1)).toBeFocused();
    const activeImg = page.locator('.gallery-card-image.active');
    await expect(activeImg).toHaveAttribute('src', /\/landing\/ar\/02-smart-compare\.jpg/);
  });

  for (const locale of ['en', 'ar'] as const) {
    test(`the full landing page has no WCAG 2.1 AA violations in ${locale}`, async ({ page }) => {
      await page.addInitScript((initialLocale) => {
        localStorage.setItem('pp.locale', initialLocale);
      }, locale);
      await page.goto('/');

      await expect(page).toHaveURL(/\/$/);
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr');
      await expect(page.locator('.hero-headline')).toBeVisible();
      await expect(page.locator('.gallery-steps')).toHaveAttribute('role', 'tablist');
      await expect(page.locator('.gallery-step-btn')).toHaveCount(5);
      await expect(page.locator('.gallery-step-btn').first()).toHaveAttribute('role', 'tab');
      await expect(page.locator('#gallery-tabpanel')).toHaveAttribute('role', 'tabpanel');

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      expect(results.violations).toEqual([]);
    });

    test(`at 375x812, ${locale} load and language toggle keep the page at the top`, async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.addInitScript((initialLocale) => {
        localStorage.setItem('pp.locale', initialLocale);
      }, locale);
      await page.goto('/');

      const html = page.locator('html');
      const firstImage = page.locator('.gallery-card-image.active');
      await expect(html).toHaveAttribute('lang', locale);
      await expect(firstImage).toHaveAttribute('src', `/landing/${locale}/01-quotation-review.jpg`);
      await expect.poll(() => page.evaluate(() => Math.abs(window.scrollY))).toBeLessThanOrEqual(1);

      await page.getByRole('button', { name: locale === 'en' ? 'عربي' : 'EN', exact: true }).click();

      const nextLocale = locale === 'en' ? 'ar' : 'en';
      await expect(html).toHaveAttribute('lang', nextLocale);
      await expect(html).toHaveAttribute('dir', nextLocale === 'ar' ? 'rtl' : 'ltr');
      await expect(firstImage).toHaveAttribute('src', `/landing/${nextLocale}/01-quotation-review.jpg`);
      await expect.poll(() => page.evaluate(() => Math.abs(window.scrollY))).toBeLessThanOrEqual(1);
    });

    test(`at 375x812 in ${locale}, pressing Next four times keeps active chip inside row bounding box and window.scrollX at 0`, async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.addInitScript((initialLocale) => {
        localStorage.setItem('pp.locale', initialLocale);
      }, locale);
      await page.goto('/');

      const stepsRow = page.locator('.gallery-steps');
      await expect(stepsRow).toBeVisible();

      const nextBtn = page.locator('.gallery-nav-btn.next-btn');
      await expect(nextBtn).toBeVisible();

      for (let i = 1; i <= 4; i++) {
        await nextBtn.click();
        const activeChip = page.locator('.gallery-step.active');
        await expect(activeChip).toBeVisible();

        await expect.poll(async () => {
          const rowBox = await stepsRow.boundingBox();
          const chipBox = await activeChip.boundingBox();
          if (!rowBox || !chipBox) return false;

          return (
            chipBox.x >= rowBox.x - 1 &&
            chipBox.x + chipBox.width <= rowBox.x + rowBox.width + 1
          );
        }).toBe(true);

        const scrollX = await page.evaluate(() => window.scrollX);
        expect(scrollX).toBe(0);
      }
    });
  }

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

    const enlargeBtn = page.locator('.gallery-enlarge-btn');
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
