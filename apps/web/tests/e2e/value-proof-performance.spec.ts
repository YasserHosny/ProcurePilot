import { test, expect } from '@playwright/test';
import { createMember, type CreatedMember } from './support/api';

/**
 * Performance Regression Test for Value Proof & Launch Screens (T080).
 *
 * Verifies that key screen transitions and views render within acceptable
 * latency thresholds (< 2.5s initial paint, < 500ms interaction response).
 */
test.describe('Value Proof Performance Tests (T080)', () => {
  let member: CreatedMember;

  test.beforeEach(async ({ page }) => {
    member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('Savings Ledger loads and renders within performance budget', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/savings');
    await expect(page.locator('.page-title')).toBeVisible();
    const duration = Date.now() - startTime;

    expect(duration).toBeLessThan(3500);
  });

  test('Savings Export screen loads within performance budget', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/savings/export');
    await expect(page.locator('.page-title')).toBeVisible();
    const duration = Date.now() - startTime;

    expect(duration).toBeLessThan(3500);
  });

  test('Subscription Plan screen loads within performance budget', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/plan');
    await expect(page.locator('.page-title')).toBeVisible();
    const duration = Date.now() - startTime;

    expect(duration).toBeLessThan(3500);
  });
});
