import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { test, expect } from '@playwright/test';

/**
 * Credentials come from global-setup, which creates a real workspace through the sign-up
 * endpoint. They used to be hardcoded to an account nothing created, which is why every test
 * here failed at sign-in the first time the suite was ever executed.
 */
const credentials = JSON.parse(
  readFileSync(join(__dirname, '.credentials.json'), 'utf-8'),
) as { ownerEmail: string; ownerPassword: string; businessName: string };

/**
 * E2E tests for English/Arabic localisation and Right-to-Left (RTL) mirroring (T071).
 *
 * Requirements:
 * - FR-017: Shared catalogue for English and Arabic strings.
 * - FR-018: RTL layout when Arabic is active.
 * - FR-019: Persistence across sessions and reloads.
 */
test.describe('ProcurePilot Localisation & RTL Layout (T071)', () => {
  test('should render in English and LTR by default', async ({ page }) => {
    await page.goto('/auth/sign-in');

    const html = page.locator('html');
    await expect(html).toHaveAttribute('dir', 'ltr');
    await expect(html).toHaveAttribute('lang', 'en');

    await expect(page.locator('.brand-name')).toContainText('ProcurePilot');
    await expect(page.locator('.card-title')).toContainText('Sign in to your workspace');
  });

  test('should mirror layout to RTL and render Arabic strings when language is switched', async ({ page }) => {
    // Sign in and land on authenticated shell
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', credentials.ownerEmail);
    await page.fill('input[formControlName="password"]', credentials.ownerPassword);
    await page.click('button[type="submit"]');

    await page.waitForURL('**/home');

    // Confirm initial LTR
    const html = page.locator('html');
    await expect(html).toHaveAttribute('dir', 'ltr');

    // Open account menu
    await page.click('.account-btn');
    await expect(page.locator('.menu-section-header')).toBeVisible();

    // Select Arabic language
    await page.click('button:has-text("العربية")');

    // Verify document root attributes changed to RTL and Arabic
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');

    // Verify Shell & Home navigation strings are now Arabic
    await expect(page.locator('.nav-item.active .nav-label')).toHaveText('نظرة عامة');
    await expect(page.locator('.nav-section-title')).toHaveText('التنقل الرئيسي');
    await expect(page.locator('.badge-active span')).toHaveText('مساحة العمل المستقلة نشطة');

    // Reload page to verify persistence across reloads
    await page.reload();
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');
    await expect(page.locator('.nav-item.active .nav-label')).toHaveText('نظرة عامة');
  });

  test('should persist Arabic language preference across sign-out and sign-in', async ({ page }) => {
    // Sign in
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', credentials.ownerEmail);
    await page.fill('input[formControlName="password"]', credentials.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');

    // Switch to Arabic
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

    // Sign out
    await page.click('.account-btn');
    await page.click('button:has-text("تسجيل الخروج")');
    await page.waitForURL('**/auth/sign-in');

    // Sign in again with same account
    await page.fill('input[formControlName="email"]', credentials.ownerEmail);
    await page.fill('input[formControlName="password"]', credentials.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');

    // Verify language choice is restored
    const html = page.locator('html');
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(html).toHaveAttribute('lang', 'ar');
    await expect(page.locator('.nav-item.active .nav-label')).toHaveText('نظرة عامة');
  });
});
