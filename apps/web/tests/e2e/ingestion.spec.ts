import { join } from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import {
  createIsolatedWorkspace,
  createMember,
  createTestSupplier,
  credentials,
  setOwnerLocale,
  signIn,
  signInOwner,
} from './support/api';

/**
 * End-to-End test suite for Automated Ingestion (013-automated-ingestion, T035).
 *
 * Covers the four core ingestion flows against the live running stack:
 * 1. Email config setup: configure, toggle enabled state, add allowed domain, reload and persist.
 * 2. Capture upload flow: route guard blocks viewer, allows buyer/owner, uploads PDF, quotation link created.
 * 3. Catalogue import flow: requires supplier selection before file upload, imports CSV, asserts summary counts.
 * 4. Dashboard stats: fresh zero-activity workspace renders stat cards with zero/empty states and resolves channel links.
 */

async function ensureEnglish(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
    await page.click('.account-btn');
    await page.locator('button[mat-menu-item]', { hasText: 'English' }).click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  }
}

async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.context().clearCookies();
  await page.goto('/auth/sign-in');
  await page.evaluate(() => localStorage.clear());
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
  await ensureEnglish(page);
}

test.describe('Automated Ingestion (013-automated-ingestion, T035)', () => {
  test.beforeAll(async () => {
    try {
      await setOwnerLocale('en');
    } catch {
      // Ignore if owner session is not initialized yet; signInUi handles locale reset
    }
  });

  test('Flow 1: Email config setup - configure, toggle enable/disable, add allowed domain, and verify persistence', async ({
    page,
  }) => {
    const creds = credentials();
    await signInUi(page, creds.ownerEmail, creds.ownerPassword);

    await page.goto('/ingestion/email-config');
    await expect(page.locator('.page-title')).toContainText('Email Ingestion Settings');

    // Wait for the unconfigured setup button or the status badge to appear
    const setupBtn = page.locator('[data-testid="setup-email-config-btn"]');
    const badge = page.locator('[data-testid="status-badge"]');

    await expect(
      page.locator('[data-testid="setup-email-config-btn"], [data-testid="status-badge"]')
    ).toBeVisible({ timeout: 15000 });

    if (await setupBtn.isVisible()) {
      await setupBtn.click();
      await expect(badge).toBeVisible({ timeout: 15000 });
    }

    const toggle = page.locator('[data-testid="toggle-enabled"]');
    await expect(toggle).toBeVisible();

    const initialBadgeText = (await badge.textContent())?.trim();

    // Toggle enabled status and assert the status badge updates
    await toggle.click();
    if (initialBadgeText === 'Enabled') {
      await expect(badge).toContainText('Disabled');
      // Toggle back to Enabled
      await toggle.click();
      await expect(badge).toContainText('Enabled');
    } else {
      await expect(badge).toContainText('Enabled');
    }

    // Add a domain to the allowlist via real input + add button
    const uniqueDomain = `vendor-${Date.now()}.example.com`;
    await page.fill('[data-testid="domain-input"]', uniqueDomain);
    await page.click('[data-testid="add-domain-btn"]');

    // Assert the domain chip renders
    const chip = page.locator('.domain-chip', { hasText: uniqueDomain });
    await expect(chip).toBeVisible();

    // Reload page and assert domain persisted across page reload
    await page.reload();
    await expect(page.locator('.domain-chip', { hasText: uniqueDomain })).toBeVisible();
  });

  test('Flow 2: Capture upload flow - route guard blocks viewer, allows buyer to upload PDF, and creates quotation link', async ({
    page,
  }) => {
    // Negative test: viewer role must be blocked by route guard and redirected to /home
    const viewer = await createMember('viewer');
    await signInUi(page, viewer.email, viewer.password);

    await page.goto('/ingestion/capture');
    await page.waitForURL('**/home');
    expect(page.url()).toContain('/home');

    // Positive test: buyer role can access /ingestion/capture
    const buyer = await createMember('buyer');
    await signInUi(page, buyer.email, buyer.password);

    await page.goto('/ingestion/capture');
    await expect(page.locator('.page-title')).toContainText('Quotation Capture');

    // Upload a small real PDF fixture
    const pdfFixturePath = join(__dirname, 'fixtures', 'test-quotation.pdf');
    await page.locator('input.file-input').first().setInputFiles(pdfFixturePath);
    await expect(page.locator('.selected-file-card')).toBeVisible();

    // Submit the upload
    await page.locator('button.submit-btn').click();

    // Assert the success state renders
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 15000 });

    // Assert the "view quotation" link's href matches /quotations/<uuid>
    const quotationLink = page.locator('.result-container.success a.action-btn', {
      hasText: 'View Quotation',
    });
    await expect(quotationLink).toBeVisible();
    await expect(quotationLink).toHaveAttribute('href', /\/quotations\/[0-9a-fA-F-]+/);
  });

  test('Flow 3: Catalogue import flow - supplier required before upload, imports CSV fixture, and matches counts', async ({
    page,
  }) => {
    const ownerToken = await signInOwner();
    const supplier = await createTestSupplier(ownerToken);
    const buyer = await createMember('buyer');

    await signInUi(page, buyer.email, buyer.password);
    await page.goto('/ingestion/catalogue-import');
    await expect(page.locator('.page-title')).toContainText('Catalogue Import');

    // Confirm file picker and browse button are disabled before a supplier is chosen
    await expect(page.locator('input.file-input')).toBeDisabled();
    await expect(page.locator('button.browse-btn')).toBeDisabled();

    // Select the seeded supplier
    await page.locator('mat-select').click();
    await page.locator('mat-option', { hasText: supplier.name }).click();

    // Confirm file picker is now enabled
    await expect(page.locator('input.file-input')).toBeEnabled();

    // Upload small real CSV fixture (3 known rows with supported currency GBP)
    const csvFixturePath = join(__dirname, 'fixtures', 'test-catalogue.csv');
    await page.locator('input.file-input').setInputFiles(csvFixturePath);
    await expect(page.locator('.selected-file-card')).toBeVisible();

    // Submit the import
    await page.locator('button.submit-btn').click();

    // Assert results summary matches fixture counts exactly (3 total, 3 imported, 0 skipped, 0 errors)
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.stat-total .stat-value')).toHaveText('3');
    await expect(page.locator('.stat-imported .stat-value')).toHaveText('3');
    await expect(page.locator('.stat-skipped .stat-value')).toHaveText('0');
    await expect(page.locator('.stat-errors .stat-value')).toHaveText('0');
  });

  test('Flow 4: Dashboard stats - fresh zero-activity workspace renders stats without crashing and channel links resolve', async ({
    page,
  }) => {
    // Create an isolated workspace so it is genuinely zero-activity
    const isolatedWorkspace = await createIsolatedWorkspace();
    const isolatedOwnerToken = await signIn(
      isolatedWorkspace.ownerEmail,
      isolatedWorkspace.ownerPassword,
    );
    const freshBuyer = await createMember('buyer', isolatedOwnerToken);

    await signInUi(page, freshBuyer.email, freshBuyer.password);
    await page.goto('/ingestion');
    await expect(page.locator('.page-title')).toContainText('Ingestion Dashboard');

    // Assert stat cards render without crashing and show zero states
    const statValues = page.locator('.stats-section .stat-card .stat-value');
    await expect(statValues).toHaveCount(3);
    await expect(statValues.nth(0)).toHaveText('0');
    await expect(statValues.nth(1)).toHaveText('0');
    await expect(statValues.nth(2)).toHaveText('0');

    // Assert empty state renders for recent emails
    await expect(page.locator('.empty-state')).toBeVisible();
    await expect(page.locator('.empty-state .empty-title')).toContainText('No emails received yet');

    // Assert all four channel cards in the channels grid point to the right routes
    const channelsGrid = page.locator('.channels-grid');

    const emailConfigLink = channelsGrid.locator('a[routerLink="/ingestion/email-config"]');
    await expect(emailConfigLink).toBeVisible();
    await expect(emailConfigLink).toHaveAttribute('href', '/ingestion/email-config');

    const emailLogLink = channelsGrid.locator('a[routerLink="/ingestion/email-log"]');
    await expect(emailLogLink).toBeVisible();
    await expect(emailLogLink).toHaveAttribute('href', '/ingestion/email-log');

    const captureLink = channelsGrid.locator('a[routerLink="/ingestion/capture"]');
    await expect(captureLink).toBeVisible();
    await expect(captureLink).toHaveAttribute('href', '/ingestion/capture');

    const catalogueImportLink = channelsGrid.locator('a[routerLink="/ingestion/catalogue-import"]');
    await expect(catalogueImportLink).toBeVisible();
    await expect(catalogueImportLink).toHaveAttribute('href', '/ingestion/catalogue-import');
  });
});
