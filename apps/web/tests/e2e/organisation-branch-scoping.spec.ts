import { test, expect, type Page } from '@playwright/test';

import { apiAsUser, createIsolatedWorkspace, createMember, signIn, type Credentials } from './support/api';

/**
 * End-to-End test suite for Branch-Scoped Visibility (chunk 007, User Story 4 / T038).
 *
 * The RLS mechanism itself (research.md R1) and its full proof already exist at the database
 * layer: apps/api/tests/integration/test_branch_scoped_visibility.py. This suite proves the SAME
 * guarantees carry through the whole stack for a real signed-in branch-scoped member — not
 * re-deriving RLS, just confirming nothing above the database loses the property:
 *
 * - The owner assigns a branch-scoped role AND the branch itself through the change-role
 *   dialog's new branch picker (the one genuinely new UI behaviour here).
 * - That member's own /settings view shows only their branch's data — and, just as important,
 *   does NOT show the other branch's rows anywhere.
 * - The member's OWN authenticated API responses (their real token, the same enforcement point
 *   a guessed Branch B URL would have hit anyway — RLS at the database layer, not a route
 *   guard) exclude Branch B's ids and everything linked to them. The contract has list +
 *   create + PATCH-by-id only, so "a guessed URL resolves as not found" is proven as: the
 *   scoped member's own LIST never contains Branch B.
 * - The owner still sees both branches end-to-end — establishing that what is missing for the
 *   scoped member is their scoping, not some broader bug hiding data from everyone.
 *
 * Why the shared fixture member starts as `approver` rather than `buyer`: assigning a branch
 * requires the target membership to ALREADY hold a branch-scopable role in the database at the
 * moment the assignment is created (the API answers 422 branch_scopable_role_required
 * otherwise). The dialog itself only COLLECTS the role + branch pick — TeamComponent sequences
 * the two API calls afterwards, role change first, THEN the assignment, specifically so a
 * buyer → branch_manager + branch change in one confirm DOES work correctly (see
 * ChangeRoleDialogComponent's own doc comment on ChangeRoleDialogResult). This file's shared
 * fixture member still starts at `approver` (itself already branch-scopable) purely so the
 * branch picker is visible from the moment the dialog opens, which is what the picker-mechanics
 * assertions in `changeRoleViaDialog` check — the separate 'promotes a buyer directly' test
 * below is the actual regression proof for the buyer → branch_manager + branch ordering fix,
 * using its own throwaway member so it doesn't disturb this file's shared visibility fixtures.
 *
 * Fixtures (branches, cost centres, budgets) are created via the owner's API rather than the
 * create dialogs: the sibling suites already prove those dialogs exhaustively, this suite needs
 * the created ids directly for the exclusion assertions, and everything under test here is the
 * assignment flow and downstream visibility, not creation.
 *
 * No RTL test: T017/T024/T031 already cover RTL for these exact settings screens, and this
 * story changes only how many rows a member sees, not any layout — there is no
 * branch-scoping-specific RTL surface to check.
 *
 * One isolated workspace per FILE (not per test): like every other chunk-007 suite, this file
 * mutates real membership and organisation rows against its own workspace only.
 */
test.describe('Organisation Branch-Scoped Visibility (chunk 007 US4)', () => {
  let workspace: Credentials;
  /** Owner token for the ISOLATED workspace — never the shared global owner. */
  let ownerToken: string;

  interface Fixture {
    id: string;
    /** Branches/cost centres carry names; budgets are told apart by formatted amount instead. */
    label: string;
  }

  let branchA: Fixture;
  let branchB: Fixture;
  let costCentreA: Fixture;
  let costCentreB: Fixture;
  let budgetA: Fixture;
  let budgetB: Fixture;

  let member: { email: string; password: string };

  test.beforeAll(async () => {
    workspace = await createIsolatedWorkspace();
    ownerToken = await signIn(workspace.ownerEmail, workspace.ownerPassword);

    const stamp = `${Date.now()}`;
    const createBranch = async (name: string): Promise<Fixture> => {
      const created = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/organisation/branches', {
        name,
        address: '1 Harbour Way',
        region: 'GB',
      });
      return { id: created.id, label: name };
    };
    branchA = await createBranch(`E2E Scoping Branch A ${stamp}`);
    branchB = await createBranch(`E2E Scoping Branch B ${stamp}`);

    const createCostCentre = async (
      name: string,
      code: string,
      branchId: string,
    ): Promise<Fixture> => {
      const created = await apiAsUser<{ id: string }>(
        ownerToken,
        'POST',
        '/organisation/cost-centres',
        { name, code, branch_id: branchId },
      );
      return { id: created.id, label: name };
    };
    costCentreA = await createCostCentre(
      `E2E Scoping Cost Centre A ${stamp}`,
      `E2ESCCA-${stamp}`,
      branchA.id,
    );
    costCentreB = await createCostCentre(
      `E2E Scoping Cost Centre B ${stamp}`,
      `E2ESCCB-${stamp}`,
      branchB.id,
    );

    // Amounts chosen so each renders ('6,100.00' / '9,200.00') as a string that is not a
    // substring of the other — rows are keyed by formatted amount, matching the budget suite.
    const createBudget = (amount: string, branchId: string): Promise<Fixture> =>
      apiAsUser<Fixture>(ownerToken, 'POST', '/organisation/budgets', {
        amount,
        currency: 'GBP',
        period: 'monthly',
        period_start: '2033-01-01',
        scope: 'branch',
        branch_id: branchId,
      });
    budgetA = { id: (await createBudget('6100', branchA.id)).id, label: '6,100.00' };
    budgetB = { id: (await createBudget('9200', branchB.id)).id, label: '9,200.00' };

    // Starting role is deliberate — see the block comment at the top of this file.
    const created = await createMember('approver', ownerToken);
    member = { email: created.email, password: created.password };
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', workspace.ownerEmail);
    await page.fill('input[formControlName="password"]', workspace.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  /**
   * Drives the change-role dialog to completion: selects `newRoleLabel` in the role picker,
   * optionally picks `branchName` in the newly-visible branch picker, confirms. The dialog
   * title text scopes every dialog lookup (closed Material dialogs can leave empty containers
   * in the overlay); mat-select panels render OUTSIDE mat-dialog-container, hence the
   * page-level option lookups.
   */
  async function changeRoleViaDialog(
    page: Page,
    data: { memberEmail: string; newRoleLabel: string; branchName?: string },
  ): Promise<void> {
    await page.goto('/team');
    const memberRow = page.locator('tr[mat-row]', { hasText: data.memberEmail });
    await memberRow.locator('.action-menu-btn').click();
    await page.click('button:has-text("Change role")');

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'Change Member Role' });
    await expect(dialog).toBeVisible();

    const confirmBtn = dialog.locator('button[type="submit"][form="change-role-form"]');
    // Unchanged role → confirm stays disabled until something actually changes.
    await expect(confirmBtn).toBeDisabled();

    // The member starts at a branch-scopable role, so the picker is visible from the start;
    // switching to a non-scopable role must remove it, and back must restore it.
    const branchPicker = dialog.locator('mat-select[formControlName="branch_id"]');
    await expect(branchPicker).toBeVisible();
    await expect(dialog.locator('mat-hint')).toContainText('Optional — pick a branch');

    await dialog.locator('mat-select[formControlName="role"]').click();
    await page.locator('mat-option').filter({ hasText: 'Buyer' }).click();
    await expect(branchPicker).toHaveCount(0);
    await expect(confirmBtn).toBeEnabled();

    await dialog.locator('mat-select[formControlName="role"]').click();
    await page.locator('mat-option').filter({ hasText: data.newRoleLabel }).click();
    await expect(branchPicker).toBeVisible();

    if (data.branchName) {
      await branchPicker.click();
      await page.locator('mat-option').filter({ hasText: data.branchName }).click();
    }

    await confirmBtn.click();
    await expect(dialog).toBeHidden();
  }

  test('owner assigns branch_manager plus the branch through the change-role dialog', async ({
    page,
  }) => {
    await changeRoleViaDialog(page, {
      memberEmail: member.email,
      newRoleLabel: 'Branch Manager',
      branchName: branchA.label,
    });

    // Success surfaces twice: the role-change confirmation and the updated role pill.
    await expect(page.locator('body')).toContainText('Member role updated successfully.');
    const memberRow = page.locator('tr[mat-row]', { hasText: member.email });
    await expect(memberRow.locator('.role-pill')).toContainText('Branch Manager');
  });

  test('owner promotes a buyer directly to branch_manager with an immediate branch assignment', async ({
    page,
  }) => {
    // The actual regression proof for the ordering fix: TeamComponent must call
    // changeMemberRole BEFORE createBranchRoleAssignment, never the reverse, or this exact
    // transition (a role that is NOT YET branch-scopable, changed to one that is, with a branch
    // picked in the same confirm) 422s on branch_scopable_role_required. A throwaway member of
    // its own, so this doesn't disturb the shared visibility fixtures used by the tests below.
    const buyer = await createMember('buyer', ownerToken);

    await page.goto('/team');
    const memberRow = page.locator('tr[mat-row]', { hasText: buyer.email });
    await memberRow.locator('.action-menu-btn').click();
    await page.click('button:has-text("Change role")');

    const dialog = page.locator('mat-dialog-container').filter({ hasText: 'Change Member Role' });
    await expect(dialog).toBeVisible();
    // Buyer is not branch-scopable, so the picker must not exist yet.
    await expect(dialog.locator('mat-select[formControlName="branch_id"]')).toHaveCount(0);

    await dialog.locator('mat-select[formControlName="role"]').click();
    await page.locator('mat-option').filter({ hasText: 'Branch Manager' }).click();

    const branchPicker = dialog.locator('mat-select[formControlName="branch_id"]');
    await expect(branchPicker).toBeVisible();
    await branchPicker.click();
    await page.locator('mat-option').filter({ hasText: branchA.label }).click();

    await dialog.locator('button[type="submit"][form="change-role-form"]').click();
    await expect(dialog).toBeHidden();

    // No error toast/banner anywhere — a failed assignment after a 422 would have surfaced one.
    await expect(page.locator('body')).toContainText('Member role updated successfully.');
    await expect(memberRow.locator('.role-pill')).toContainText('Branch Manager');

    // Prove the ASSIGNMENT itself actually landed, not just the role: an unassigned
    // branch_manager falls back to unscoped (sees every branch, research.md R1), so if the
    // assignment had silently failed, this member would see BOTH branches, not just one.
    const buyerToken = await signIn(buyer.email, buyer.password);
    const branches = await apiAsUser<{ items: { id: string }[] }>(
      buyerToken,
      'GET',
      '/organisation/branches?limit=100',
    );
    expect(branches.items.map((b) => b.id)).toEqual([branchA.id]);
  });

  test('the branch-scoped member sees only their own branch across the settings screens', async ({
    browser,
  }) => {
    const memberContext = await browser.newContext();
    const memberPage = await memberContext.newPage();
    try {
      await memberPage.goto('/auth/sign-in');
      await memberPage.fill('input[formControlName="email"]', member.email);
      await memberPage.fill('input[formControlName="password"]', member.password);
      await memberPage.click('button[type="submit"]');
      await memberPage.waitForURL('**/home');
      await memberPage.goto('/settings');

      // Branches: Branch A present, Branch B absent — checked as absence, not merely A's presence.
      const branchRows = memberPage.locator('app-branch-list tr[mat-row]');
      await expect(branchRows.filter({ hasText: branchA.label })).toBeVisible();
      await expect(branchRows.filter({ hasText: branchB.label })).toHaveCount(0);
      await expect(branchRows).toHaveCount(1);

      // Cost centres: only the one linked to Branch A.
      const costCentreRows = memberPage.locator('app-cost-centre-list tr[mat-row]');
      await expect(costCentreRows.filter({ hasText: costCentreA.label })).toBeVisible();
      await expect(costCentreRows.filter({ hasText: costCentreB.label })).toHaveCount(0);
      await expect(costCentreRows).toHaveCount(1);

      // Budgets: only Branch A's, keyed by formatted amount per the budget suite's convention.
      const budgetRows = memberPage.locator('app-budget-list tr[mat-row]');
      await expect(budgetRows.filter({ hasText: budgetA.label })).toBeVisible();
      await expect(budgetRows.filter({ hasText: budgetB.label })).toHaveCount(0);
      await expect(budgetRows).toHaveCount(1);
    } finally {
      await memberContext.close();
    }
  });

  test("the branch-scoped member's own API responses never contain the other branch", async () => {
    // The member's real token IS the session; this hits the same enforcement point (RLS at the
    // database layer) a guessed Branch B URL would have reached — there is no singular GET to
    // guess against, so exclusion from the member's own LIST is the meaningful equivalent.
    const token = await signIn(member.email, member.password);

    interface BranchRow {
      id: string;
      name: string;
    }
    interface CostCentreRow {
      id: string;
      branch_id: string | null;
    }
    interface BudgetRow {
      id: string;
      branch_id: string | null;
    }
    interface List<T> {
      items: T[];
      next_cursor: string | null;
    }

    const branches = await apiAsUser<List<BranchRow>>(
      token,
      'GET',
      '/organisation/branches?limit=100',
    );
    const branchIds = branches.items.map((b) => b.id);
    expect(branchIds).toContain(branchA.id);
    expect(branchIds).not.toContain(branchB.id);

    const costCentres = await apiAsUser<List<CostCentreRow>>(
      token,
      'GET',
      '/organisation/cost-centres?limit=100',
    );
    const costCentreIds = costCentres.items.map((c) => c.id);
    expect(costCentreIds).toContain(costCentreA.id);
    expect(costCentreIds).not.toContain(costCentreB.id);
    // Nothing linked to Branch B either way — neither its cost centre nor any reference to it.
    expect(costCentres.items.map((c) => c.branch_id)).not.toContain(branchB.id);

    const budgets = await apiAsUser<List<BudgetRow>>(token, 'GET', '/organisation/budgets?limit=100');
    const budgetIds = budgets.items.map((b) => b.id);
    expect(budgetIds).toContain(budgetA.id);
    expect(budgetIds).not.toContain(budgetB.id);
    expect(budgets.items.map((b) => b.branch_id)).not.toContain(branchB.id);
  });

  test('contrast: the owner still sees both branches end-to-end', async ({ page }) => {
    await page.goto('/settings');

    const branchRows = page.locator('app-branch-list tr[mat-row]');
    await expect(branchRows.filter({ hasText: branchA.label })).toBeVisible();
    await expect(branchRows.filter({ hasText: branchB.label })).toBeVisible();
    await expect(branchRows).toHaveCount(2);

    const costCentreRows = page.locator('app-cost-centre-list tr[mat-row]');
    await expect(costCentreRows.filter({ hasText: costCentreA.label })).toBeVisible();
    await expect(costCentreRows.filter({ hasText: costCentreB.label })).toBeVisible();
    await expect(costCentreRows).toHaveCount(2);

    const budgetRows = page.locator('app-budget-list tr[mat-row]');
    await expect(budgetRows.filter({ hasText: budgetA.label })).toBeVisible();
    await expect(budgetRows.filter({ hasText: budgetB.label })).toBeVisible();
    await expect(budgetRows).toHaveCount(2);
  });
});
