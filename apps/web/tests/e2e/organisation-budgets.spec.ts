import { test, expect, type Locator, type Page } from '@playwright/test';

import { createIsolatedWorkspace, type Credentials } from './support/api';

/**
 * End-to-End test suite for Organisation Budget Management (chunk 007, User Story 3).
 *
 * Covered:
 * - Owner defines an organisation-wide budget; the row shows amount, currency, period, scope,
 *   and an em-dash under "Applies To" (organisation scope names no single target row).
 * - Owner defines a branch-scoped budget; only the branch picker exists for that scope and the
 *   row names the branch under "Applies To".
 * - Owner defines a cost-centre-scoped budget; only the cost-centre picker exists for that
 *   scope and the row names the cost centre.
 * - FR-005: an overlapping budget is saved anyway. The first budget raises no banner, a second
 *   overlapping one saves AND raises the informational banner, and a third outside both ranges
 *   saves with the banner gone again.
 * - The budgets section mirrors to RTL with its Arabic title.
 *
 * Create-only chunk: budgets have no edit/archive actions, so there is no row-action coverage.
 *
 * One isolated workspace per FILE (not per test): budget creation is owner-gated and mutates
 * real budget rows, so — like the branch and cost-centre suites — this file must not share the
 * global owner every other spec signs in as. Tests keep their fixture periods years apart so
 * they never overlap each other's data; the overlap test creates its overlaps deliberately.
 */
test.describe('Organisation Budget Management (chunk 007 US3)', () => {
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

  function uniqueCostCentreName(): string {
    return `E2E Cost Centre ${Date.now()}.${Math.floor(Math.random() * 10000)}`;
  }

  function uniqueCostCentreCode(): string {
    return `E2ECC-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  }

  /**
   * Rows are keyed by their formatted amount: every fixture in this file uses an amount whose
   * rendered form is not a substring of any other's, so hasText stays unambiguous even though
   * all of this file's budgets accumulate in the one shared workspace.
   */
  function budgetRow(page: Page, formattedAmount: string): Locator {
    return page.locator('app-budget-list tr[mat-row]', { hasText: formattedAmount });
  }

  interface BudgetDraft {
    /** Pattern-validated decimal string, as typed into the form. */
    amount: string;
    period: 'Monthly' | 'Quarterly' | 'Annual';
    /** Plain YYYY-MM-DD — native date inputs fill that way regardless of display locale. */
    periodStart: string;
    scope: 'Whole organisation' | 'Branch' | 'Cost centre';
    /** Branch or cost-centre name, required unless scope is whole-organisation. */
    targetName?: string;
  }

  /**
   * Drives the Define Budget dialog to completion. The dialog title text scopes every lookup:
   * closed Material dialogs can leave empty containers in the overlay, so an unscoped
   * mat-dialog-container locator would trip strict mode. mat-select panels render in the
   * overlay OUTSIDE mat-dialog-container, hence the page-level option lookups.
   *
   * Starts by loading /settings afresh: the section resolves "Applies To" names from
   * branch/cost-centre lookups taken at mount, so a target created earlier in the test is only
   * labelled after a fresh mount — otherwise the column degrades to raw IDs by design.
   *
   * `onScopeSelected` runs after the scope is picked but before submission, so a test can
   * assert which scope-dependent pickers exist mid-dialog.
   */
  async function defineBudgetViaDialog(
    page: Page,
    draft: BudgetDraft,
    onScopeSelected?: (dialog: Locator) => Promise<void>,
  ): Promise<void> {
    await page.goto('/settings');

    // Every settings section renders its own `.action-btn`, so scope the click to budgets.
    await page.locator('app-budget-list .action-btn').click();

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'Define Budget' });
    await expect(dialog).toBeVisible();

    await dialog.locator('input[formControlName="amount"]').fill(draft.amount);

    // Chosen explicitly even though the dialog preselects the workspace currency (GBP for
    // seeded workspaces): the option label ends in the ISO code in either language.
    await dialog.locator('mat-select[formControlName="currency"]').click();
    await page.locator('mat-option').filter({ hasText: '(GBP)' }).click();

    await dialog.locator('mat-select[formControlName="period"]').click();
    await page.locator('mat-option').filter({ hasText: draft.period }).click();

    await dialog.locator('input[formControlName="period_start"]').fill(draft.periodStart);

    await dialog.locator('mat-select[formControlName="scope"]').click();
    await page.locator('mat-option').filter({ hasText: draft.scope }).click();
    if (onScopeSelected) {
      await onScopeSelected(dialog);
    }
    if (draft.targetName) {
      const picker =
        draft.scope === 'Branch'
          ? dialog.locator('mat-select[formControlName="branch_id"]')
          : dialog.locator('mat-select[formControlName="cost_centre_id"]');
      await picker.click();
      await page.locator('mat-option').filter({ hasText: draft.targetName }).click();
    }

    await dialog.locator('button[type="submit"][form="budget-form"]').click();
    await expect(dialog).toBeHidden();
  }

  /** Reused create flows for the scope-target fixtures; mirrors the sibling specs verbatim. */
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

  async function createCostCentreViaDialog(
    page: Page,
    draft: { name: string; code: string },
  ): Promise<void> {
    await page.goto('/settings');
    await page.locator('app-cost-centre-list .action-btn').click();

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'New Cost Centre' });
    await expect(dialog).toBeVisible();
    await dialog.locator('input[formControlName="name"]').fill(draft.name);
    await dialog.locator('input[formControlName="code"]').fill(draft.code);
    await dialog.locator('button[type="submit"][form="cost-centre-form"]').click();
    await expect(dialog).toBeHidden();

    await expect(
      page.locator('app-cost-centre-list tr[mat-row]', { hasText: draft.name }),
    ).toBeVisible();
  }

  test('owner defines an organisation-wide budget', async ({ page }) => {
    const budgetsSection = page.locator('app-budget-list');
    await page.goto('/settings');
    await expect(budgetsSection.locator('.section-title')).toContainText('Budgets');
    // Fresh isolated workspace: nothing defined yet, so the empty state shows first.
    await expect(budgetsSection.locator('.empty-message')).toBeVisible();
    await expect(budgetsSection.locator('.empty-message')).toContainText(
      'No budgets have been defined yet.',
    );

    await defineBudgetViaDialog(page, {
      amount: '5000',
      period: 'Monthly',
      periodStart: '2030-01-01',
      scope: 'Whole organisation',
    }, async (dialog) => {
      // Organisation scope names no single target, so neither dependent picker may exist.
      await expect(dialog.locator('mat-select[formControlName="branch_id"]')).toHaveCount(0);
      await expect(dialog.locator('mat-select[formControlName="cost_centre_id"]')).toHaveCount(0);
    });

    // Column order is fixed by displayedColumns: amount, currency, period, scope, appliesTo.
    const row = budgetRow(page, '5,000.00');
    await expect(row).toBeVisible();
    await expect(row.locator('.budget-amount')).toContainText('5,000.00');
    await expect(row.locator('td').nth(1)).toHaveText('GBP');
    await expect(row.locator('td').nth(2)).toHaveText('Monthly');
    await expect(row.locator('td').nth(3)).toHaveText('Whole organisation');
    await expect(row.locator('td').nth(4)).toHaveText('—');
    // A first, non-overlapping budget must not raise the FR-005 banner.
    await expect(budgetsSection.locator('.info-banner')).toHaveCount(0);
  });

  test('owner defines a branch-scoped budget', async ({ page }) => {
    const branch = { name: uniqueBranchName(), address: '8 Foundry Rd', region: 'GB' };
    await createBranchViaDialog(page, branch);

    await defineBudgetViaDialog(page, {
      amount: '7300.25',
      period: 'Quarterly',
      periodStart: '2031-02-01',
      scope: 'Branch',
      targetName: branch.name,
    }, async (dialog) => {
      // Exactly one dependent picker exists for branch scope: the branch one.
      await expect(dialog.locator('mat-select[formControlName="branch_id"]')).toBeVisible();
      await expect(dialog.locator('mat-select[formControlName="cost_centre_id"]')).toHaveCount(0);
    });

    const row = budgetRow(page, '7,300.25');
    await expect(row).toBeVisible();
    await expect(row.locator('td').nth(3)).toHaveText('Branch');
    await expect(row.locator('td').nth(4)).toHaveText(branch.name);
  });

  test('owner defines a cost-centre-scoped budget', async ({ page }) => {
    const cc = { name: uniqueCostCentreName(), code: uniqueCostCentreCode() };
    await createCostCentreViaDialog(page, cc);

    await defineBudgetViaDialog(page, {
      amount: '3100.75',
      period: 'Monthly',
      periodStart: '2032-03-01',
      scope: 'Cost centre',
      targetName: cc.name,
    }, async (dialog) => {
      // Exactly one dependent picker exists for cost-centre scope: the cost-centre one.
      await expect(dialog.locator('mat-select[formControlName="cost_centre_id"]')).toBeVisible();
      await expect(dialog.locator('mat-select[formControlName="branch_id"]')).toHaveCount(0);
    });

    const row = budgetRow(page, '3,100.75');
    await expect(row).toBeVisible();
    await expect(row.locator('td').nth(3)).toHaveText('Cost centre');
    await expect(row.locator('td').nth(4)).toHaveText(cc.name);
  });

  test('overlapping budgets save with a warning instead of blocking', async ({ page }) => {
    const banner = page.locator('app-budget-list .info-banner');

    // First budget: annual, organisation-wide, 2026. Nothing to overlap with yet.
    await defineBudgetViaDialog(page, {
      amount: '11250',
      period: 'Annual',
      periodStart: '2026-01-01',
      scope: 'Whole organisation',
    });
    const annualRow = budgetRow(page, '11,250.00');
    await expect(annualRow).toBeVisible();
    await expect(banner).toHaveCount(0);

    // Second budget: a quarter INSIDE the annual's window. FR-005 — the save goes through.
    await defineBudgetViaDialog(page, {
      amount: '4200',
      period: 'Quarterly',
      periodStart: '2026-04-01',
      scope: 'Whole organisation',
    });
    const quarterlyRow = budgetRow(page, '4,200.00');
    await expect(quarterlyRow).toBeVisible();
    await expect(annualRow).toBeVisible();
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('A budget already exists for this scope');

    // Third budget: outside both existing ranges — saved with no banner raised this time.
    await defineBudgetViaDialog(page, {
      amount: '850',
      period: 'Monthly',
      periodStart: '2028-01-01',
      scope: 'Whole organisation',
    });
    await expect(budgetRow(page, '850.00')).toBeVisible();
    // The flag resets on every successful create, so the stale warning must actually be gone.
    await expect(banner).toHaveCount(0);
  });

  test('budgets section renders correctly in Arabic RTL', async ({ page }) => {
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
    await expect(page.locator('app-budget-list .section-title')).toContainText('الميزانيات');
  });
});
