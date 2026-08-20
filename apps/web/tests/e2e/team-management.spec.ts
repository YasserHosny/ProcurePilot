import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { test, expect } from '@playwright/test';

/**
 * Credentials come from global-setup, which creates a real workspace through the sign-up
 * endpoint. They used to be hardcoded to an account nothing created, which is why every test
 * here failed at sign-in the first time the suite was ever executed.
 */
const credentials = JSON.parse(
  readFileSync(join(__dirname, '.credentials.json'), 'utf-8'),
) as { ownerEmail: string; ownerPassword: string; businessName: string };

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
 */
test.describe('ProcurePilot Team Management (T061)', () => {
  const ownerEmail = credentials.ownerEmail;
  const ownerPassword = credentials.ownerPassword;
  // Unique per run. A fixed address makes the suite pass once and fail forever after: the
  // server allows only ONE pending invitation per address per workspace (a deliberate rule), so
  // the second run gets a 409 from residue the first run left behind. CI reruns the same
  // database, so this is not hypothetical.
  const colleagueEmail = `buyer.colleague.${Date.now()}@example.test`;
  const colleaguePassword = 'ColleaguePassword123!';

  test.beforeEach(async ({ page }) => {
    // Sign in as owner
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', ownerEmail);
    await page.fill('input[formControlName="password"]', ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('should allow owner to navigate to team management and invite a colleague', async ({ page }) => {
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
    await expect(page.locator('.token-input')).toBeVisible();

    // Close dialog
    await page.click('button:has-text("Close")');

    // Check pending invitations tab
    await page.click('div[role="tab"]:has-text("Pending Invitations")');
    await expect(page.locator('.invitations-table')).toContainText(colleagueEmail);
  });

  test('should allow invitee to accept invitation and join the workspace', async ({ browser }) => {
    // New browser context representing the invitee
    const inviteeContext = await browser.newContext();
    const inviteePage = await inviteeContext.newPage();

    // Navigate to accept invitation with a token
    const testToken = 'mock_invitation_token_32_characters_long_for_test';
    await inviteePage.goto(`/onboarding/accept-invitation?token=${testToken}`);

    await expect(inviteePage.locator('.card-title')).toContainText('Accept workspace invitation');
    await expect(inviteePage.locator('input[formControlName="token"]')).toHaveValue(testToken);

    // Set new password
    await inviteePage.fill('input[formControlName="password"]', colleaguePassword);
    await inviteePage.click('button[type="submit"]');

    // Should authenticate and land on home
    await inviteePage.waitForURL('**/home');
    await expect(inviteePage.locator('.badge-active')).toBeVisible();

    await inviteeContext.close();
  });

  test('should allow owner to change a member role', async ({ page }) => {
    await page.goto('/team');

    // Find colleague row and open actions menu
    const memberRow = page.locator('tr.mat-row', { hasText: colleagueEmail });
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
    const ownerRow = page.locator('tr.mat-row', { hasText: ownerEmail });
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
    await page.goto('/team');

    const memberRow = page.locator('tr.mat-row', { hasText: colleagueEmail });
    await memberRow.locator('.action-menu-btn').click();
    await page.click('button:has-text("Remove member")');

    // Confirm dialog
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    await page.click('button:has-text("Remove Member")');

    // Member is removed
    await expect(page.locator('body')).toContainText('Member removed successfully.');
  });
});
