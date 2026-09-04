import { test, expect, type Locator, type Page } from '@playwright/test';

import { createIsolatedWorkspace, createMember, signIn, type Credentials } from './support/api';

/**
 * End-to-End test suite for Organisation Cost Centre Management (chunk 007, User Story 2).
 *
 * Covered:
 * - Owner creates an organisation-wide cost centre (no branch, no budget owner) and sees it
 *   listed with the "Organisation-wide" branch value.
 * - Owner creates a cost centre linked to a real branch and a real budget owner; the row shows
 *   the branch's name and the owner's email.
 * - Reusing a code is refused by the API (409) and surfaced inline: the dialog stays open with
 *   the duplicateCodeError message, and cancelling leaves exactly one row with that code.
 * - Archiving flips the status to Archived and removes the archive action while edit remains.
 * - Deactivating a branch that still has a cost centre attached (dependents confirmation) flags
 *   that cost centre orphaned with the branch_deactivated reason.
 * - Removing a member who owns a cost centre flags it orphaned with the owner_removed reason.
 * - The cost centres section mirrors to RTL with its Arabic title.
 *
 * Unlike the User Story 1 suite, no direct-DB helper is needed: cost centres now have both UI
 * and API, so every fixture here is built the way a customer would build it. Members come from
 * support/api.ts (real invite-and-accept), and their removal goes through team management's own
 * remove flow rather than raw API calls.
 */
test.describe('Organisation Cost Centre Management (chunk 007 US2)', () => {
  let workspace: Credentials;
  /** Owner token for the ISOLATED workspace — never the shared global owner. */
  let ownerToken: string;

  test.beforeAll(async () => {
    workspace = await createIsolatedWorkspace();
    ownerToken = await signIn(workspace.ownerEmail, workspace.ownerPassword);
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

  function uniqueCostCentreName(): string {
    return `E2E Cost Centre ${Date.now()}.${Math.floor(Math.random() * 10000)}`;
  }

  function uniqueCostCentreCode(): string {
    return `E2ECC-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  }

  /** hasText filters are substring matches; these names need whole-string comparisons. */
  function escapeRegExp(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function costCentreRow(page: Page, name: string): Locator {
    return page.locator('app-cost-centre-list tr[mat-row]', { hasText: name });
  }

  /**
   * Drives the branch create dialog to completion. Both settings sections render a `.action-btn`,
   * so the click is scoped to the branch section; closed Material dialogs can leave empty
   * containers in the overlay, so the title text scopes every dialog lookup instead.
   */
  async function createBranchViaDialog(
    page: Page,
    data: { name: string; address: string; region: string },
  ): Promise<void> {
    await page.goto('/settings');
    await page.locator('app-branch-list .action-btn').click();

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'New Branch' });
    await expect(dialog).toBeVisible();
    await dialog.locator('input[formControlName="name"]').fill(data.name);
    await dialog.locator('input[formControlName="address"]').fill(data.address);
    await dialog.locator('input[formControlName="region"]').fill(data.region);
    await dialog.locator('button[type="submit"][form="branch-form"]').click();
    await expect(dialog).toBeHidden();

    await expect(page.locator('app-branch-list tr[mat-row]', { hasText: data.name })).toBeVisible();
  }

  interface CostCentreDraft {
    name: string;
    code: string;
    budgetOwnerEmail?: string;
    branchName?: string;
  }

  /**
   * Drives the cost-centre create dialog to completion, leaving everything not named in the
   * draft at its default (no budget owner / organisation-wide).
   */
  async function createCostCentreViaDialog(page: Page, draft: CostCentreDraft): Promise<void> {
    await page.goto('/settings');
    await page.locator('app-cost-centre-list .action-btn').click();

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'New Cost Centre' });
    await expect(dialog).toBeVisible();
    await dialog.locator('input[formControlName="name"]').fill(draft.name);
    await dialog.locator('input[formControlName="code"]').fill(draft.code);

    // mat-select panels render in the overlay outside mat-dialog-container, hence the
    // page-level option lookup.
    if (draft.budgetOwnerEmail) {
      await dialog.locator('mat-select[formControlName="budget_owner_membership_id"]').click();
      await page.locator('mat-option').filter({ hasText: draft.budgetOwnerEmail }).click();
    }
    if (draft.branchName) {
      await dialog.locator('mat-select[formControlName="branch_id"]').click();
      await page.locator('mat-option').filter({ hasText: draft.branchName }).click();
    }

    await dialog.locator('button[type="submit"][form="cost-centre-form"]').click();
    await expect(dialog).toBeHidden();
  }

  async function expectOrphanReason(page: Page, row: Locator, reasonText: string): Promise<void> {
    const badge = row.locator('.status-indicator.status-orphaned');
    await expect(badge).toBeVisible();
    await badge.hover();
    // Material 19 renders tooltips as .mat-mdc-tooltip; the legacy .mat-tooltip is kept in the
    // lookup in case the tooltip implementation changes underneath us.
    await expect(page.locator('.mat-mdc-tooltip, .mat-tooltip')).toContainText(reasonText);
  }

  test('owner creates an organisation-wide cost centre with defaults', async ({ page }) => {
    const ccSection = page.locator('app-cost-centre-list');
    await page.goto('/settings');
    await expect(ccSection.locator('.section-title')).toContainText('Cost Centres');
    // Fresh isolated workspace: nothing created yet, so the empty state shows first.
    await expect(ccSection.locator('.empty-message')).toBeVisible();
    await expect(ccSection.locator('.empty-message')).toContainText(
      'No cost centres have been defined yet.',
    );

    const cc = { name: uniqueCostCentreName(), code: uniqueCostCentreCode() };
    await createCostCentreViaDialog(page, cc);

    const row = costCentreRow(page, cc.name);
    await expect(row.locator('.cost-centre-name')).toHaveText(cc.name);
    await expect(row.locator('.code-chip')).toHaveText(cc.code);
    // Column order is fixed by displayedColumns: name, code, budgetOwner, branch, status, actions.
    await expect(row.locator('td').nth(2)).toHaveText('—');
    await expect(row.locator('td').nth(3)).toContainText('Organisation-wide');
  });

  test('owner creates a cost centre linked to a branch and a budget owner', async ({ page }) => {
    // A real member of THIS workspace, created through invite-and-accept (support/api.ts).
    const member = await createMember('buyer', ownerToken);
    const branch = { name: uniqueBranchName(), address: '7 Foundry Rd', region: 'GB' };
    await createBranchViaDialog(page, branch);

    const cc = { name: uniqueCostCentreName(), code: uniqueCostCentreCode() };
    await createCostCentreViaDialog(page, {
      ...cc,
      budgetOwnerEmail: member.email,
      branchName: branch.name,
    });

    const row = costCentreRow(page, cc.name);
    await expect(row.locator('.cost-centre-name')).toHaveText(cc.name);
    await expect(row.locator('td').nth(2)).toHaveText(member.email);
    await expect(row.locator('td').nth(3)).toHaveText(branch.name);
    await expect(row.locator('.status-indicator.status-active')).toContainText('Active');
  });

  test('duplicate cost centre codes are rejected inline', async ({ page }) => {
    const ccSection = page.locator('app-cost-centre-list');
    const original = { name: uniqueCostCentreName(), code: uniqueCostCentreCode() };
    await createCostCentreViaDialog(page, original);

    // Second attempt reuses the first code with a different name.
    await ccSection.locator('.action-btn').click();
    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'New Cost Centre' });
    await expect(dialog).toBeVisible();
    await dialog.locator('input[formControlName="name"]').fill(uniqueCostCentreName());
    await dialog.locator('input[formControlName="code"]').fill(original.code);
    await dialog.locator('button[type="submit"][form="cost-centre-form"]').click();

    // The 409 surfaces inline: the dialog stays open with the duplicateCodeError message.
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('.error-message')).toContainText('already in use');

    await dialog.locator('button:has-text("Cancel")').click();
    await expect(dialog).toBeHidden();
    // Exactly one cost centre carries the code — the original.
    await expect(
      ccSection
        .locator('.code-chip')
        .filter({ hasText: new RegExp(`^${escapeRegExp(original.code)}$`) }),
    ).toHaveCount(1);
  });

  test('archiving a cost centre sets its status and removes the archive action', async ({
    page,
  }) => {
    const cc = { name: uniqueCostCentreName(), code: uniqueCostCentreCode() };
    await createCostCentreViaDialog(page, cc);

    const row = costCentreRow(page, cc.name);
    await row.locator('button[aria-label="Archive cost centre"]').click();

    const confirmDialog = page
      .locator('mat-dialog-container')
      .filter({ hasText: 'Archive Cost Centre' });
    await expect(confirmDialog).toBeVisible();
    await confirmDialog.locator('button.mat-warn').click();
    await expect(confirmDialog).toBeHidden();

    await expect(row.locator('.status-indicator.status-archived')).toContainText('Archived');
    // The archive button only renders while the cost centre is not archived; edit stays.
    await expect(row.locator('button[aria-label="Archive cost centre"]')).toHaveCount(0);
    await expect(row.locator('button[aria-label="Edit cost centre"]')).toBeVisible();
  });

  test('deactivating a linked branch orphans its cost centre', async ({ page }) => {
    const branch = { name: uniqueBranchName(), address: '3 Kiln Way', region: 'GB' };
    await createBranchViaDialog(page, branch);

    const cc = { name: uniqueCostCentreName(), code: uniqueCostCentreCode() };
    await createCostCentreViaDialog(page, { ...cc, branchName: branch.name });

    // The branch now has a dependent, so deactivation demands explicit confirmation.
    const branchRow = page.locator('app-branch-list tr[mat-row]', { hasText: branch.name });
    await branchRow.locator('button.danger-action').click();

    const confirmDialog = page
      .locator('mat-dialog-container')
      .filter({ hasText: 'Deactivate Branch' });
    await expect(confirmDialog).toBeVisible();
    // The warning interpolates the dependent count via {{count}} — exactly one cost centre.
    await expect(confirmDialog.locator('.dialog-warning')).toContainText('1');

    // Cancelling changes nothing.
    await confirmDialog.locator('button:has-text("Cancel")').click();
    await expect(confirmDialog).toBeHidden();
    await expect(branchRow.locator('.status-indicator.status-active')).toContainText('Active');

    // Second attempt, this time confirmed.
    await branchRow.locator('button.danger-action').click();
    await expect(confirmDialog).toBeVisible();
    await confirmDialog.locator('button.mat-warn').click();
    await expect(branchRow.locator('.status-indicator.status-inactive')).toContainText('Inactive');

    // The orphan flag is set server-side during the PATCH; reload so the table refetches.
    await page.reload();
    const row = costCentreRow(page, cc.name);
    await expect(row.locator('.status-indicator.status-orphaned')).toContainText('Orphaned');
    await expectOrphanReason(
      page,
      row,
      'The branch linked to this cost centre has been deactivated',
    );
  });

  test('removing the budget owner orphans their cost centre', async ({ page }) => {
    const member = await createMember('buyer', ownerToken);
    const cc = { name: uniqueCostCentreName(), code: uniqueCostCentreCode() };
    await createCostCentreViaDialog(page, { ...cc, budgetOwnerEmail: member.email });

    // Remove the member through team management's own remove flow — the same interaction the
    // team-management spec exercises, against this file's isolated workspace.
    await page.goto('/team');
    const memberRow = page.locator('tr[mat-row]', { hasText: member.email });
    await memberRow.locator('.action-menu-btn').click();
    await page.click('button:has-text("Remove member")');
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    await page.click('button:has-text("Remove Member")');
    await expect(page.locator('body')).toContainText('Member removed successfully.');

    await page.goto('/settings');
    const row = costCentreRow(page, cc.name);
    await expect(row.locator('.status-indicator.status-orphaned')).toContainText('Orphaned');
    await expectOrphanReason(page, row, 'The budget owner assigned to this cost centre has been removed');
  });

  test('cost centres section renders correctly in Arabic RTL', async ({ page }) => {
    // Kept last on purpose: switching language persists per member, so running it first would
    // turn the English-text assertions of the other tests into Arabic. Each run gets a fresh
    // owner from beforeAll, whose locale starts at English.
    await page.click('.account-btn');
    await page.click('button:has-text("العربية")');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');

    await page.goto('/settings');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
    await expect(page.locator('app-cost-centre-list .section-title')).toContainText(
      'مراكز التكلفة',
    );
  });
});
