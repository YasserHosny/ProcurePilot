import { test, expect } from '@playwright/test';

import {
  createIsolatedWorkspace,
  createMember,
  createPendingInvitation,
  signIn,
  type Credentials,
} from './support/api';

/**
 * End-to-End test suite for User Story 2: Team Management (T061).
 *
 * Requirements:
 * - FR-008: Role matrix (owner, buyer, branch manager, approver, viewer).
 * - FR-009: Owner invites colleague by email and chosen role, revokes pending invitations.
 * - FR-010: Invitations must be accepted by invited address.
 * - FR-011: Owner changes member role and removes members.
 * - FR-012: System prevents any action that would leave a workspace with no owner (409 Conflict).
 * - FR-013: Non-owners cannot access team management or perform administrative mutations.
 *
 * This is the one file that mutates real membership rows — role changes, removals, and a
 * deliberate attempt to demote/remove the sole owner. It gets its OWN isolated workspace rather
 * than the shared one every other spec signs in as: a suite-wide shared owner left every later
 * file unable to invite once anything here went sideways.
 */
test.describe('ProcurePilot Team Management (T061)', () => {
  let credentials: Credentials;
  let ownerToken: string;
  // Unique per run. A fixed address makes the suite pass once and fail forever after: the
  // server allows only ONE pending invitation per address per workspace (a deliberate rule), so
  // the second run gets a 409 from residue the first run left behind. CI reruns the same
  // database, so this is not hypothetical.
  const colleagueEmail = `buyer.colleague.${Date.now()}@example.test`;
  const colleaguePassword = 'ColleaguePassword123!';

  test.beforeAll(async () => {
    credentials = await createIsolatedWorkspace();
    ownerToken = await signIn(credentials.ownerEmail, credentials.ownerPassword);
  });

  test.beforeEach(async ({ page }) => {
    // Sign in as owner
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', credentials.ownerEmail);
    await page.fill('input[formControlName="password"]', credentials.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('should allow owner to navigate to team management and invite a colleague', async ({ page }) => {
    // SC-003: an owner can invite a colleague and see them active in under 2 minutes.
    const started = Date.now();
    // Navigate to Team Management
    await page.click('a[routerLink="/team"]');
    await page.waitForURL('**/team');

    await expect(page.locator('.page-title')).toContainText('Team Management');
    await expect(page.locator('.invite-btn')).toBeVisible();

    // Open invite dialog
    await page.click('.invite-btn');
    await expect(page.locator('mat-dialog-container')).toBeVisible();

    // Fill invitation form
    await page.fill('input[formControlName="email"]', colleagueEmail);
    await page.click('mat-select[formControlName="role"]');
    await page.click('mat-option:has-text("Buyer")');

    // Submit invitation
    await page.click('button[type="submit"]');

    // Token creation confirmation should appear
    await expect(page.locator('.success-icon')).toBeVisible();
    // Two .token-input fields exist — the shareable link and the raw token — so an unqualified
    // locator is ambiguous and Playwright's strict mode rejects it. Assert both, specifically.
    await expect(page.locator('.token-input').first()).toBeVisible();

    const elapsedSeconds = (Date.now() - started) / 1000;
    expect(
      elapsedSeconds,
      `SC-003 allows 2 minutes to invite a colleague; this took ${elapsedSeconds.toFixed(1)}s`,
    ).toBeLessThan(120);
    await expect(page.locator('.token-input.mono')).toBeVisible();
    await expect(page.locator('.token-input.mono')).not.toHaveValue('');

    // Close dialog
    await page.click('button:has-text("Close")');

    // Check pending invitations tab
    await page.click('div[role="tab"]:has-text("Pending Invitations")');
    await expect(page.locator('.invitations-table')).toContainText(colleagueEmail);
  });

  test('should allow invitee to accept invitation and join the workspace', async ({ browser, page }) => {
    // A real pending invitation, and the real token that came with it. This test previously used
    // a fabricated token string, so it exercised nothing: the invitation it claimed to accept
    // never existed, and the member the next three tests depended on was never created.
    const { email, token } = await createPendingInvitation('buyer', ownerToken);

    const inviteeContext = await browser.newContext();
    const inviteePage = await inviteeContext.newPage();

    await inviteePage.goto(`/onboarding/accept-invitation?token=${encodeURIComponent(token)}`);
    await expect(inviteePage.locator('input[formControlName="token"]')).toHaveValue(token);

    await inviteePage.fill('input[formControlName="password"]', colleaguePassword);
    await inviteePage.click('button[type="submit"]');

    await inviteePage.waitForURL('**/home');
    await inviteeContext.close();

    // And the workspace genuinely contains them now.
    await page.goto('/team');
    await expect(page.locator('tr[mat-row]', { hasText: email })).toBeVisible();
  });

  test('should allow owner to change a member role', async ({ page }) => {
    // This test used to act on a member the two tests above were supposed to have created, so a
    // failure there took this one with it and it could never be run alone. It now makes its own.
    const member = await createMember('buyer', ownerToken);
    await page.goto('/team');

    const memberRow = page.locator('tr[mat-row]', { hasText: member.email });
    await memberRow.locator('.action-menu-btn').click();

    // Click Change role
    await page.click('button:has-text("Change role")');
    await expect(page.locator('mat-dialog-container')).toBeVisible();

    // Select new role (Approver)
    await page.click('mat-select[formControlName="role"]');
    await page.click('mat-option:has-text("Approver")');
    await page.click('button:has-text("Update Role")');

    // Verify role updated in table
    await expect(memberRow.locator('.role-pill')).toContainText('Approver');
  });

  test('should prevent removing or demoting the last owner with 409 conflict explanation', async ({ page }) => {
    await page.goto('/team');

    // Attempt to change owner's role to Viewer
    const ownerRow = page.locator('tr[mat-row]', { hasText: credentials.ownerEmail });
    await ownerRow.locator('.action-menu-btn').click();
    await page.click('button:has-text("Change role")');

    await page.click('mat-select[formControlName="role"]');
    await page.click('mat-option:has-text("Viewer")');
    await page.click('button:has-text("Update Role")');

    // Expect clear explanation of last owner refusal
    await expect(page.locator('.error-banner')).toBeVisible();
    await expect(page.locator('.error-message')).toContainText('must retain at least one active owner');
  });

  test('should allow owner to remove a member from the workspace', async ({ page }) => {
    const member = await createMember('buyer', ownerToken);
    await page.goto('/team');

    const memberRow = page.locator('tr[mat-row]', { hasText: member.email });
    await memberRow.locator('.action-menu-btn').click();
    await page.click('button:has-text("Remove member")');

    // Confirm dialog
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    await page.click('button:has-text("Remove Member")');

    // Member is removed
    await expect(page.locator('body')).toContainText('Member removed successfully.');
  });
});
