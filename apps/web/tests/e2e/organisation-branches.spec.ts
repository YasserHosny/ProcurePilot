import { test, expect, type Page } from '@playwright/test';

import { createIsolatedWorkspace, type Credentials } from './support/api';
import { createBranchCostCentre } from './support/db';

/**
 * End-to-End test suite for Organisation Branch Management (chunk 007, User Story 1).
 *
 * Covered:
 * - Owner creates a branch from /settings and sees it listed as Active.
 * - Owner renames a branch and the table reflects it.
 * - Deactivating a branch with no dependents succeeds directly (no confirmation dialog) and the
 *   deactivate action disappears from its row (the template only renders it while is_active).
 * - Deactivating a branch with a dependent cost centre demands explicit confirmation: cancelling
 *   keeps the branch active; confirming deactivates it. The cost centre itself has no UI or API
 *   until User Story 2, so support/db.ts inserts one via psql.
 * - The settings page mirrors to RTL with the Arabic organisation title.
 *
 * One isolated workspace per FILE (not per test): every write here is owner-gated and mutates
 * real branch rows, so — like team-management.spec.ts — this file must not share the global
 * owner every other spec signs in as.
 */
test.describe('Organisation Branch Management (chunk 007 US1)', () => {
  let workspace: Credentials;

  test.beforeAll(async () => {
    workspace = await createIsolatedWorkspace();
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', workspace.ownerEmail);
    await page.fill('input[formControlName="password"]', workspace.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  /** Timestamped so tests never collide with residue from earlier runs of this file. */
  function uniqueBranchName(): string {
    return `E2E Branch ${Date.now()}.${Math.floor(Math.random() * 10000)}`;
  }

  /** hasText filters are substring matches; these names need whole-string comparisons. */
  function escapeRegExp(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /**
   * Drives the create dialog to completion. The dialog title text scopes every lookup: closed
   * Material dialogs can leave empty containers in the overlay, so an unscoped
   * mat-dialog-container locator would trip strict mode.
   */
  async function createBranchViaDialog(
    page: Page,
    data: { name: string; address: string; region: string },
  ): Promise<void> {
    await page.goto('/settings');
    await page.click('.action-btn');

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'New Branch' });
    await expect(dialog).toBeVisible();
    await dialog.locator('input[formControlName="name"]').fill(data.name);
    await dialog.locator('input[formControlName="address"]').fill(data.address);
    await dialog.locator('input[formControlName="region"]').fill(data.region);
    await dialog.locator('button[type="submit"][form="branch-form"]').click();
    await expect(dialog).toBeHidden();

    const row = page.locator('tr[mat-row]', { hasText: data.name });
    await expect(row).toBeVisible();
  }

  test('owner creates a branch and sees it Active in the table', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('.settings-title')).toContainText('Organisation Settings');
    // Fresh workspace: nothing created yet, so the empty state shows before the first branch.
    await expect(page.locator('.empty-message')).toBeVisible();

    const branch = { name: uniqueBranchName(), address: '12 Market St', region: 'GB' };
    await createBranchViaDialog(page, branch);

    const row = page.locator('tr[mat-row]', { hasText: branch.name });
    await expect(row.locator('.branch-name')).toHaveText(branch.name);
    await expect(row).toContainText(branch.address);
    await expect(row).toContainText(branch.region);
    await expect(row.locator('.status-indicator.status-active')).toContainText('Active');
  });

  test('owner edits a branch name and the table reflects it', async ({ page }) => {
    const branch = { name: uniqueBranchName(), address: '4 Industrial Way', region: 'GB' };
    await createBranchViaDialog(page, branch);

    const row = page.locator('tr[mat-row]', { hasText: branch.name });
    await row.locator('button[aria-label="Edit branch"]').click();

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'Edit Branch' });
    await expect(dialog).toBeVisible();
    // The form opens pre-filled with the branch's current values.
    await expect(dialog.locator('input[formControlName="name"]')).toHaveValue(branch.name);

    const newName = `${branch.name} Renamed`;
    await dialog.locator('input[formControlName="name"]').fill(newName);
    await dialog.locator('button[type="submit"][form="branch-form"]').click();
    await expect(dialog).toBeHidden();

    const renamedRow = page.locator('tr[mat-row]', { hasText: newName });
    await expect(renamedRow.locator('.branch-name')).toHaveText(newName);
    // The renamed row still CONTAINS the old name as a prefix, so the old-name check must be
    // exact — no cell anywhere in the table holds just the old name anymore.
    await expect(
      page
        .locator('.branch-name')
        .filter({ hasText: new RegExp(`^${escapeRegExp(branch.name)}$`) }),
    ).toHaveCount(0);
  });

  test('deactivating a branch with no dependents succeeds without confirmation', async ({ page }) => {
    const branch = { name: uniqueBranchName(), address: '9 Harbour Rd', region: 'GB' };
    await createBranchViaDialog(page, branch);

    const row = page.locator('tr[mat-row]', { hasText: branch.name });
    await row.locator('button.danger-action').click();

    // Direct path: the PATCH succeeds, so no confirmation dialog may appear at any point.
    await expect(row.locator('.status-indicator.status-inactive')).toContainText('Inactive');
    await expect(page.locator('mat-dialog-container')).toHaveCount(0);

    // The deactivate button only renders while the branch is active; edit stays.
    await expect(row.locator('button.danger-action')).toHaveCount(0);
    await expect(row.locator('button[aria-label="Edit branch"]')).toBeVisible();
  });

  test('deactivating a branch with dependents requires explicit confirmation', async ({ page }) => {
    const branch = { name: uniqueBranchName(), address: '2 Depot Lane', region: 'GB' };
    await createBranchViaDialog(page, branch);

    // No cost-centre UI/API exists yet (User Story 2), so attach the dependent straight in the DB.
    createBranchCostCentre(workspace.ownerEmail, branch.name);

    const row = page.locator('tr[mat-row]', { hasText: branch.name });
    await row.locator('button.danger-action').click();

    const confirmDialog = page
      .locator('mat-dialog-container')
      .filter({ hasText: 'Deactivate Branch' });
    await expect(confirmDialog).toBeVisible();
    // The warning interpolates the dependent count via {{count}} — exactly one cost centre.
    await expect(confirmDialog.locator('.dialog-warning')).toContainText('1');

    // Cancelling changes nothing.
    await confirmDialog.locator('button:has-text("Cancel")').click();
    await expect(confirmDialog).toBeHidden();
    await expect(row.locator('.status-indicator.status-active')).toContainText('Active');
    await expect(row.locator('button.danger-action')).toBeVisible();

    // Second attempt, this time confirmed.
    await row.locator('button.danger-action').click();
    await expect(confirmDialog).toBeVisible();
    await confirmDialog.locator('button.mat-warn').click();
    await expect(row.locator('.status-indicator.status-inactive')).toContainText('Inactive');
  });

  test('settings renders correctly in RTL', async ({ page }) => {
    // Kept last on purpose: switching language persists per member, so running it first would
    // turn the English-text assertions of the other tests into Arabic. Each run also gets a fresh
    // owner from beforeAll, whose locale starts at English.
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');

    await page.goto('/settings');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.settings-title')).toContainText('إعدادات المنشأة');
  });
});
