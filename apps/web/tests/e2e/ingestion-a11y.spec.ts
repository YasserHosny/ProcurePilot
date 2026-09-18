import { join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page, type Browser } from '@playwright/test';

import {
  createMember,
  createTestSupplier,
  credentials,
  setOwnerLocale,
  signInOwner,
  type CreatedMember,
} from './support/api';

/**
 * Accessibility & RTL test suite for Automated Ingestion (013-automated-ingestion, T036).
 *
 * Covers:
 * 1. Axe-core WCAG 2.1 AA scan in English AND Arabic across all five surfaces:
 *    - /ingestion (Dashboard)
 *    - /ingestion/email-config (Email Ingestion Settings)
 *    - /ingestion/email-log (Email Log)
 *    - /ingestion/capture (Quotation Capture)
 *    - /ingestion/catalogue-import (Catalogue Import)
 * 2. Keyboard navigation for file upload on /ingestion/capture and /ingestion/catalogue-import:
 *    proving keyboard-only users can focus and activate browse/file-picker, and separately focus and activate remove-file.
 * 3. RTL layout verification: document.body.scrollWidth <= window.innerWidth (no horizontal scroll)
 *    and directional icon mirroring via .rtl-flip.
 *
 * NOTE per parallel-execution-plan-ingestion-wave7.md §4:
 * English tests run first and Arabic/RTL tests run last to prevent server-side persisted locale leakage
 * across test cases sharing a session.
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page: Page) {
  return new AxeBuilder({ page })
    .withTags(WCAG_21_AA)
    .exclude('.nav-item.disabled')
    .analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

/**
 * Activates any Angular production-inlined stylesheets whose media attribute defaults to "print"
 * (media="print" onload="this.media='all'") so that full global styles and RTL transform rules apply.
 */
async function ensureStyles(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"][media="print"]').forEach((el) => {
      el.media = 'all';
    });
  });
}

async function switchToArabic(page: Page): Promise<void> {
  if ((await page.locator('html').getAttribute('dir')) !== 'rtl') {
    await page.click('.account-btn');
    await page.locator('button:has-text("العربية")').click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.mat-mdc-menu-panel')).toHaveCount(0);
  }
  await ensureStyles(page);
}

type StoredSession = Awaited<ReturnType<Page['context']['storageState']>>;

test.describe('Automated Ingestion Accessibility & RTL @a11y', () => {
  let buyer: CreatedMember;
  let ownerCreds: { ownerEmail: string; ownerPassword: string };
  let testSupplier: { id: string; name: string };
  let buyerStorage: StoredSession;
  let ownerStorage: StoredSession;

  test.beforeAll(async ({ browser }: { browser: Browser }) => {
    try {
      await setOwnerLocale('en');
    } catch {
      // Ignore if owner session is not initialized yet
    }
    ownerCreds = credentials();
    buyer = await createMember('buyer');
    const ownerToken = await signInOwner();
    testSupplier = await createTestSupplier(ownerToken);

    // Perform UI sign-in once for buyer and once for owner, saving session storage state.
    // This strictly adheres to the standard sign-in flow while avoiding the 10/minute auth rate limit
    // across the suite's tests.
    const buyerCtx = await browser.newContext();
    const buyerPage = await buyerCtx.newPage();
    await buyerPage.goto('/auth/sign-in');
    await buyerPage.fill('input[formControlName="email"]', buyer.email);
    await buyerPage.fill('input[formControlName="password"]', buyer.password);
    await buyerPage.click('button[type="submit"]');
    await buyerPage.waitForURL('**/home');
    buyerStorage = await buyerCtx.storageState();
    await buyerCtx.close();

    const ownerCtx = await browser.newContext();
    const ownerPage = await ownerCtx.newPage();
    await ownerPage.goto('/auth/sign-in');
    await ownerPage.fill('input[formControlName="email"]', ownerCreds.ownerEmail);
    await ownerPage.fill('input[formControlName="password"]', ownerCreds.ownerPassword);
    await ownerPage.click('button[type="submit"]');
    await ownerPage.waitForURL('**/home');
    ownerStorage = await ownerCtx.storageState();
    await ownerCtx.close();
  });

  async function applySession(page: Page, storage: StoredSession): Promise<void> {
    await page.context().addCookies(storage.cookies);
    for (const origin of storage.origins) {
      await page.addInitScript(
        ({ originData }) => {
          for (const item of originData.localStorage) {
            localStorage.setItem(item.name, item.value);
          }
        },
        { originData: origin },
      );
    }
  }

  async function signInBuyer(page: Page): Promise<void> {
    await applySession(page, buyerStorage);
    await ensureStyles(page);
  }

  async function signInOwnerSession(page: Page): Promise<void> {
    await applySession(page, ownerStorage);
    await ensureStyles(page);
  }

  // =========================================================================
  // Section A: All English Axe-core WCAG 2.1 AA Scans (5 surfaces)
  // =========================================================================

  test('the Ingestion Dashboard in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion');
    await expect(page.locator('.page-title')).toContainText('Ingestion Dashboard');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Email Ingestion Settings screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/ingestion/email-config');
    await expect(page.locator('.page-title')).toContainText('Email Ingestion Settings');

    // Ensure email config is initialized if tenant is fresh
    const setupBtn = page.locator('[data-testid="setup-email-config-btn"]');
    const badge = page.locator('[data-testid="status-badge"]');
    await expect(
      page.locator('[data-testid="setup-email-config-btn"], [data-testid="status-badge"]'),
    ).toBeVisible({ timeout: 15000 });
    if (await setupBtn.isVisible()) {
      await setupBtn.click();
      await expect(badge).toBeVisible({ timeout: 15000 });
    }

    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Ingestion Email Log screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/email-log');
    await expect(page.locator('.page-title')).toContainText('Email Inbound Log');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Quotation Capture screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/capture');
    await expect(page.locator('.page-title')).toContainText('Quotation Capture');
    await expect(page.locator('button.browse-btn')).toBeVisible();
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Catalogue Import screen in English has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/catalogue-import');
    await expect(page.locator('.page-title')).toContainText('Catalogue Import');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // =========================================================================
  // Section B: Keyboard Navigation for File Upload & Removal
  // =========================================================================

  test('Keyboard navigation: Quotation Capture file input trigger and remove file control @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/capture');
    await expect(page.locator('.page-title')).toContainText('Quotation Capture');

    const browseBtn = page.locator('button.browse-btn');
    await expect(browseBtn).toBeVisible();

    // Focus the page header back-link and Tab into the browse button
    const backLink = page.locator('.page-header .back-link');
    await backLink.focus();
    await expect(backLink).toBeFocused();

    // Tab to browse button and verify focus actually lands on it
    await page.keyboard.press('Tab');
    await expect(browseBtn).toBeFocused();
    const isBrowseActive = await browseBtn.evaluate((el) => el === document.activeElement);
    expect(isBrowseActive).toBe(true);

    // Activate the file input trigger via keyboard Enter and handle the file chooser
    const pdfFixturePath = join(__dirname, 'fixtures', 'test-quotation.pdf');
    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.keyboard.press('Enter'),
    ]);
    await fileChooser.setFiles(pdfFixturePath);

    // Selected file card appears with the file details and remove control
    const selectedFileCard = page.locator('.selected-file-card');
    await expect(selectedFileCard).toBeVisible();

    // Reach the remove file control via keyboard Tab
    const removeBtn = selectedFileCard.locator('button');
    await backLink.focus();
    for (let i = 0; i < 5; i++) {
      if (await removeBtn.evaluate((el) => el === document.activeElement)) {
        break;
      }
      await page.keyboard.press('Tab');
    }
    await expect(removeBtn).toBeFocused();
    const isRemoveActive = await removeBtn.evaluate((el) => el === document.activeElement);
    expect(isRemoveActive).toBe(true);

    // Activate remove button via keyboard Space/Enter
    await page.keyboard.press('Enter');

    // Confirm file was removed and browse button is restored
    await expect(selectedFileCard).not.toBeVisible();
    await expect(browseBtn).toBeVisible();
  });

  test('Keyboard navigation: Catalogue Import file input trigger and remove file control @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/catalogue-import');
    await expect(page.locator('.page-title')).toContainText('Catalogue Import');

    // Select supplier so the browse button becomes enabled
    await page.locator('mat-select').click();
    await page.locator('mat-option', { hasText: testSupplier.name }).click();

    const browseBtn = page.locator('button.browse-btn');
    await expect(browseBtn).toBeEnabled();

    // Navigate with Tab from the supplier selector to the browse button
    const backLink = page.locator('.page-header .back-link');
    await backLink.focus();
    await expect(backLink).toBeFocused();

    // Tab through to browse button
    for (let i = 0; i < 5; i++) {
      if (await browseBtn.evaluate((el) => el === document.activeElement)) {
        break;
      }
      await page.keyboard.press('Tab');
    }
    await expect(browseBtn).toBeFocused();
    const isBrowseActive = await browseBtn.evaluate((el) => el === document.activeElement);
    expect(isBrowseActive).toBe(true);

    // Activate file picker via keyboard Enter
    const csvFixturePath = join(__dirname, 'fixtures', 'test-catalogue.csv');
    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.keyboard.press('Enter'),
    ]);
    await fileChooser.setFiles(csvFixturePath);

    // Selected file card appears
    const selectedFileCard = page.locator('.selected-file-card');
    await expect(selectedFileCard).toBeVisible();

    // Reach the remove file button via Tab
    const removeBtn = selectedFileCard.locator('button');
    await backLink.focus();
    for (let i = 0; i < 5; i++) {
      if (await removeBtn.evaluate((el) => el === document.activeElement)) {
        break;
      }
      await page.keyboard.press('Tab');
    }
    await expect(removeBtn).toBeFocused();
    const isRemoveActive = await removeBtn.evaluate((el) => el === document.activeElement);
    expect(isRemoveActive).toBe(true);

    // Activate remove button via keyboard Space/Enter
    await page.keyboard.press('Enter');

    // Confirm file was removed and browse button is restored
    await expect(selectedFileCard).not.toBeVisible();
    await expect(browseBtn).toBeVisible();
  });

  // =========================================================================
  // Section C: All Arabic Axe-core WCAG 2.1 AA Scans (5 surfaces)
  // =========================================================================

  test('the Ingestion Dashboard in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Email Ingestion Settings screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInOwnerSession(page);
    await page.goto('/ingestion/email-config');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

    const setupBtn = page.locator('[data-testid="setup-email-config-btn"]');
    const badge = page.locator('[data-testid="status-badge"]');
    await expect(
      page.locator('[data-testid="setup-email-config-btn"], [data-testid="status-badge"]'),
    ).toBeVisible({ timeout: 15000 });
    if (await setupBtn.isVisible()) {
      await setupBtn.click();
      await expect(badge).toBeVisible({ timeout: 15000 });
    }

    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Ingestion Email Log screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/email-log');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Quotation Capture screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/capture');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('button.browse-btn')).toBeVisible();
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  test('the Catalogue Import screen in Arabic has no WCAG 2.1 AA violations @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/catalogue-import');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await ensureStyles(page);
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  });

  // =========================================================================
  // Section D: RTL Layout Verification (scrollWidth check & directional element styling)
  // =========================================================================

  test('RTL layout: Ingestion Dashboard has no horizontal scroll and mirrors directional icons @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await ensureStyles(page);

    // Structural check: no horizontal scroll in RTL
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const innerWidth = await page.evaluate(() => window.innerWidth);
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth);

    // Verify directional element styling: channel action forward arrows use .rtl-flip
    const directionalIcon = page.locator('.channel-action-btn mat-icon.rtl-flip').first();
    await expect(directionalIcon).toBeVisible();
    const transform = await directionalIcon.evaluate(
      (el) => window.getComputedStyle(el).transform,
    );
    // [dir="rtl"] .rtl-flip applies transform: scaleX(-1) -> computed as matrix(-1, 0, 0, 1, 0, 0)
    expect(transform).toBe('matrix(-1, 0, 0, 1, 0, 0)');
  });

  test('RTL layout: Quotation Capture sub-page has no horizontal scroll in RTL @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/capture');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await ensureStyles(page);

    // Structural check: no horizontal scroll in RTL on sub-page
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const innerWidth = await page.evaluate(() => window.innerWidth);
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
  });

  test('RTL layout: Inbound Email Log sub-page has no horizontal scroll in RTL @a11y', async ({
    page,
  }) => {
    await signInBuyer(page);
    await page.goto('/ingestion/email-log');
    await switchToArabic(page);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await ensureStyles(page);

    // Structural check: no horizontal scroll in RTL on table-heavy sub-page
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const innerWidth = await page.evaluate(() => window.innerWidth);
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
  });
});
