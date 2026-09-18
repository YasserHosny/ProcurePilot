import { test, expect, type Page } from '@playwright/test';
import {
  createIsolatedWorkspace,
  createTestProduct,
  createTestSupplier,
  recordPurchaseOutcome,
  setOwnerLocale,
  signIn,
} from './support/api';

/**
 * End-to-End test suite for Accounting Integration (014-accounting-integration, T036).
 *
 * One continuous end-to-end flow given the pipeline dependency between stories:
 * US2 requires US1's active connection, and US3 requires US2's sync/match results.
 *
 * Covers:
 * 1. Sign in as owner in an isolated workspace, navigate to /accounting.
 * 2. Click Connect, complete the stub OAuth flow (intercepting the authorization redirect
 *    and driving the server-side callback to establish active connection).
 *    Includes SC-001 timing assertion (< 60s, well within 2m budget).
 * 3. Assert connection shows status='active' with display name ("ProcurePilot Demo Company").
 * 4. Navigate to /accounting/bills, click "Sync now", wait for and assert bill list populates.
 * 5. Assert automatic match: with a pre-seeded matching purchase record for "Global Office Supplies",
 *    stub-bill-101 produces a genuine automatic match (FR-007), while other stub bills remain unmatched.
 *    Verify matched/unmatched filter behavior.
 * 6. Navigate to /accounting/discrepancies, assert open discrepancy list populates from unmatched bills (FR-010).
 * 7. Resolve a discrepancy with a note, assert it disappears from open list and renders in resolved list.
 *    Includes SC-003 timing assertion (< 30s, well within 60s budget).
 */

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';

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

test.describe('Accounting Integration (014-accounting-integration, T036)', () => {
  test.beforeAll(async () => {
    try {
      await setOwnerLocale('en');
    } catch {
      // Ignore if owner session is not initialized yet; signInUi handles locale reset
    }
  });

  test('one continuous flow: connect, sync, verify bills and match, resolve discrepancy', async ({
    page,
  }) => {
    // Fresh isolated workspace to prevent interference with other suites and ensure zero-state
    const creds = await createIsolatedWorkspace();
    const token = await signIn(creds.ownerEmail, creds.ownerPassword);

    // Guaranteed Automatic Match Pre-seeding (FR-007):
    // StubConnector provides 3 fixed fake bills:
    // - stub-bill-101: 1250.00 USD, 15 days ago, vendor "Global Office Supplies"
    // - stub-bill-102: 3450.50 USD, 30 days ago, vendor "Industrial Parts Direct"
    // - stub-bill-103: 890.25 USD, 5 days ago, vendor "Apex Logistics"
    //
    // We seed a matching supplier ("Global Office Supplies") and a purchase record
    // matching stub-bill-101 (same supplier, 1250.00 USD, 15 days ago).
    // On sync, SyncService links the vendor by name and MatchingService auto-matches stub-bill-101.
    const supplier = await createTestSupplier(token, 'Global Office Supplies');
    const product = await createTestProduct(token, { tenant_name: 'Printer Paper A4' });
    const fifteenDaysAgo = new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString();
    await recordPurchaseOutcome(token, {
      workspace_product_id: product.id,
      supplier_id: supplier.id,
      quantity: '1.000000',
      base_unit: 'each',
      unit_price: { amount: '1250.00', currency: 'USD' },
      total_paid: { amount: '1250.00', currency: 'USD' },
      delivery_result: 'delivered',
      ordered_at: fifteenDaysAgo,
    });

    // 1. Sign in as owner and navigate to /accounting
    await signInUi(page, creds.ownerEmail, creds.ownerPassword);
    await page.goto('/accounting');
    await expect(page.locator('.page-title')).toContainText('Accounting Integration');

    // Assert initial unconfigured empty state
    await expect(page.locator('[data-testid="empty-connection-card"]')).toBeVisible();
    const connectBtn = page.locator('[data-testid="connect-btn"]');
    await expect(connectBtn).toBeVisible();

    // 2. Click Connect and complete the stub OAuth flow
    // Intercept the browser's navigation to QuickBooks OAuth consent screen and fulfill
    // with a redirect to the backend's OAuth completion callback endpoint.
    await page.route('**/connect/oauth2**', async (route) => {
      const url = new URL(route.request().url());
      const state = url.searchParams.get('state') ?? '';
      const callbackUrl = `${API}/accounting/connect/callback?code=stub-auth-code&realmId=stub-realm-12345&state=${encodeURIComponent(state)}`;
      await route.fulfill({
        status: 302,
        headers: { Location: callbackUrl },
      });
    });

    // SC-001 timing requirement: Connect flow completes well within 2 minutes (budget: < 60s)
    const connectStartTime = Date.now();
    await connectBtn.click();

    // 3. Assert connection now shows status='active' with display name
    const statusCard = page.locator('[data-testid="connection-status-card"]');
    await expect(statusCard).toBeVisible({ timeout: 15_000 });

    const statusBadge = page.locator('[data-testid="connection-status-badge"]');
    await expect(statusBadge).toContainText('Active');

    const displayName = page.locator('[data-testid="connection-display-name"]');
    await expect(displayName).toContainText('ProcurePilot Demo Company');

    const connectDuration = Date.now() - connectStartTime;
    expect(connectDuration).toBeLessThan(60_000); // SC-001: < 60s

    // 4. Navigate to /accounting/bills, click "Sync now", wait for bill list to populate
    const viewBillsBtn = page.locator('[data-testid="view-bills-btn"]');
    await viewBillsBtn.click();
    await page.waitForURL('**/accounting/bills');
    await expect(page.locator('.page-title')).toContainText('Synced Bills');

    const syncBtn = page.locator('[data-testid="sync-now-btn"]');
    await expect(syncBtn).toBeVisible();

    const syncResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/accounting/sync') && res.request().method() === 'POST',
    );
    await syncBtn.click();
    const syncResponse = await syncResponsePromise;
    expect(syncResponse.status()).toBe(202);

    // Refresh bills list following manual sync trigger
    const refreshBtn = page.locator('[data-testid="refresh-bills-btn"]');
    await refreshBtn.click();

    const billsTable = page.locator('[data-testid="bills-table"]');
    await expect(billsTable).toBeVisible({ timeout: 15_000 });

    const billRows = page.locator('[data-testid="bill-row"]');
    await expect(billRows).toHaveCount(3);

    // 5. Assert at least one bill shows a matched indicator and others show unmatched
    const matchedBadges = page.locator('[data-testid="match-badge-matched"]');
    await expect(matchedBadges.first()).toBeVisible();

    const unmatchedBadges = page.locator('[data-testid="match-badge-unmatched"]');
    await expect(unmatchedBadges.first()).toBeVisible();

    // Verify filter by 'matched' shows only the matched bill
    const matchFilter = page.locator('[data-testid="match-status-filter"]');
    await matchFilter.click();
    await page.locator('[data-testid="filter-opt-matched"]').click();
    await expect(page.locator('[data-testid="bill-row"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="match-badge-matched"]')).toBeVisible();

    // Reset filter to 'all'
    await matchFilter.click();
    await page.locator('[data-testid="filter-opt-all"]').click();
    await expect(page.locator('[data-testid="bill-row"]')).toHaveCount(3);

    // 6. Navigate to /accounting/discrepancies, assert at least one discrepancy appears
    // SC-003 timing requirement: Discrepancy resolution completes well within 60 seconds (budget: < 30s)
    const resolveStartTime = Date.now();

    await page.goto('/accounting/discrepancies');
    await expect(page.locator('.page-title')).toContainText('Reconciliation Discrepancies');

    const discrepanciesTable = page.locator('[data-testid="discrepancies-table"]');
    await expect(discrepanciesTable).toBeVisible({ timeout: 15_000 });

    const openDiscrepancies = page.locator('[data-testid="discrepancy-row"]');
    const initialOpenCount = await openDiscrepancies.count();
    expect(initialOpenCount).toBeGreaterThan(0);

    // 7. Resolve a discrepancy with a note, assert it disappears from open list
    const resolveBtn = page.locator('[data-testid="resolve-btn"]').first();
    await resolveBtn.click();

    const resolveNoteInput = page.locator('[data-testid="resolve-note-input"]');
    await expect(resolveNoteInput).toBeVisible();
    await resolveNoteInput.fill('Verified and resolved in E2E test');

    const confirmResolveBtn = page.locator('[data-testid="confirm-resolve-btn"]');
    await confirmResolveBtn.click();

    // Assert open discrepancy count decreased by 1
    await expect(openDiscrepancies).toHaveCount(initialOpenCount - 1);

    const resolveDuration = Date.now() - resolveStartTime;
    expect(resolveDuration).toBeLessThan(30_000); // SC-003: < 30s

    // Verify the resolved discrepancy appears in the 'resolved' status filter
    const statusFilter = page.locator('[data-testid="status-filter"]');
    await statusFilter.click();
    await page.locator('[data-testid="filter-opt-resolved"]').click();

    const resolvedRows = page.locator('[data-testid="discrepancy-row"]');
    await expect(resolvedRows).toHaveCount(1);
    await expect(page.locator('[data-testid="resolution-note"]')).toContainText(
      'Verified and resolved in E2E test',
    );
  });
});
