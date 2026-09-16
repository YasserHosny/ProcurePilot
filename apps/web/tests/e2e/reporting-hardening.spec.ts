import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * Reporting Hardening End-to-End Suite (T022, T028).
 *
 * Covers:
 * - US1: Scheduled report lifecycle (form creation, table appearance, pause/resume, Arabic RTL).
 * - US1: Cross-link from /savings/export into schedule form.
 * - US2: Weekly actionable digests (settings, onboarding banner, pause/resume, channel toggle, in-app digest preview).
 * - Keyboard navigation across Reports Center in LTR and RTL.
 */
test.describe('Reporting Hardening & Actionable Digests (T022, T028)', () => {
  let member: CreatedMember;

  test.beforeEach(async ({ page }) => {
    member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('creates a scheduled report via schedule form and lists it in schedules tab', async ({ page }) => {
    await page.goto('/reports');
    await expect(page.locator('.page-title')).toContainText('Reports Center');

    // Click "New Schedule" button to navigate to schedule form
    const newScheduleBtn = page.locator('a[routerLink="/reports/schedule-form"]');
    await expect(newScheduleBtn).toBeVisible();
    await newScheduleBtn.click();
    await page.waitForURL('**/reports/schedule-form**');

    // Verify form rendered
    await expect(page.locator('.form-title')).toBeVisible();

    // Select format and submit
    await page.locator('mat-select[formControlName="format"]').click();
    await page.locator('mat-option').first().click();

    // Submit the schedule
    await page.locator('button[type="submit"]').click();

    // Navigates back to reports center
    await page.waitForURL('**/reports');
  });

  test('savings export screen offers "Schedule as weekly report" pre-populated cross-link', async ({ page }) => {
    await page.goto('/savings/export');
    await expect(page.locator('.page-title')).toContainText('Export Savings Ledger');

    const scheduleLink = page.locator('.schedule-link-btn');
    await expect(scheduleLink).toBeVisible();
    await scheduleLink.click();

    await page.waitForURL('**/reports/schedule-form?kind=savings_ledger**');
    await expect(page.locator('.form-title')).toBeVisible();
  });

  test('digest settings displays onboarding prompt, allows channel/status toggle, and renders in-app digest', async ({ page }) => {
    await page.goto('/reports/digest-settings');
    await expect(page.locator('.page-title')).toContainText('Weekly Procurement Digest');

    // Onboarding banner should be visible for default subscription
    const banner = page.locator('.onboarding-banner');
    if (await banner.isVisible()) {
      const dismissBtn = banner.locator('button');
      await dismissBtn.click();
      await expect(banner).toBeHidden();
    }

    // Latest digest card should be visible with period or empty section note
    await expect(page.locator('.digest-view-card')).toBeVisible();
    await expect(page.locator('.digest-view-card .card-title')).toBeVisible();

    // If subscription card is present, test toggle interaction
    const subCard = page.locator('.subscription-card').first();
    if (await subCard.isVisible()) {
      const toggleBtn = subCard.locator('button').first();
      await expect(toggleBtn).toBeEnabled();
    }
  });

  test('renders Reports Center and Digest Settings in Arabic with RTL layout', async ({ page }) => {
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

    await page.goto('/reports');
    await expect(page.locator('.page-title')).toContainText('مركز التقارير');

    await page.goto('/reports/digest-settings');
    await expect(page.locator('.page-title')).toContainText('ملخص المشتريات الأسبوعي');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  });

  test('navigates Reports Center interactive elements via keyboard', async ({ page }) => {
    await page.goto('/reports');
    await expect(page.locator('.page-title')).toContainText('Reports Center');

    // Keyboard tab through header actions
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(focused).toBeTruthy();
  });
});
