import { test, expect } from '@playwright/test';

import { mintPlatformInvitation } from './support/api';

/**
 * Sign-up, end to end — task T050, with the SC-001 timing budget (T089).
 *
 * This is the journey the whole chunk exists to enable: an invited business creates a configured
 * workspace and lands in it. Everything else in the product is downstream of this working.
 */

/**
 * Open a Material select and take its first option, via the keyboard.
 *
 * Clicking is unreliable here: the floating <mat-label> overlays the select's centre, and the
 * inner trigger never settles Playwright's "stable" check while the form animates. Focusing and
 * pressing Enter is how a keyboard user opens the control, so it is both robust and a small
 * accessibility assertion in its own right — if this stops working, the control has become
 * unreachable without a mouse.
 */
async function chooseFirstOption(
  page: import('@playwright/test').Page,
  controlName: string,
): Promise<void> {
  const select = page.locator(`mat-select[formControlName="${controlName}"]`);
  await select.scrollIntoViewIfNeeded();
  await select.focus();
  await page.keyboard.press('Enter');
  await page.locator('mat-option').first().waitFor({ state: 'visible' });
  await page.locator('mat-option').first().click();
}

test.describe('Workspace sign-up (US1)', () => {
  test('an invited business creates a workspace and lands in the shell', async ({ page }) => {
    const stamp = Date.now();
    const email = `e2e.signup.${stamp}@example.test`;
    const password = 'E2eSignupPassword123!';
    const businessName = `Signup Test Co ${stamp}`;

    // The invitation must be addressed to the registrant: holding a token is not authority to
    // register as anyone (the server returns 403 on a mismatch).
    const invitation = mintPlatformInvitation(email);

    // SC-001: landing on sign-up to standing in a workspace, unaided, in under 3 minutes.
    const started = Date.now();

    await page.goto('/onboarding/signup');

    await page.fill('input[formControlName="invitation_token"]', invitation.invitation_token);
    await page.fill('input[formControlName="business_name"]', businessName);
    await page.fill('input[formControlName="email"]', email);
    await page.fill('input[formControlName="password"]', password);

    // Region, currency and tax model have NO pre-selected default (FR-031): the registrant states
    // them. A test that did not choose them would not be exercising sign-up as specified.
    await chooseFirstOption(page, 'region');
    await chooseFirstOption(page, 'currency');
    await chooseFirstOption(page, 'tax_model');

    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');

    const elapsedSeconds = (Date.now() - started) / 1000;
    expect(
      elapsedSeconds,
      `SC-001 allows 3 minutes from sign-up to workspace; this took ${elapsedSeconds.toFixed(1)}s`,
    ).toBeLessThan(180);

    // And they are genuinely the owner of a real workspace, not merely on a page that looks right.
    await page.goto('/team');
    await expect(page.locator('tr[mat-row]', { hasText: email })).toBeVisible();
  });

  test('sign-up without a valid invitation is refused', async ({ page }) => {
    // FR-033: the pilot is invitation-gated. This is the negative half of the same requirement,
    // and without it the test above would pass just as happily if the gate were removed.
    const stamp = Date.now();
    await page.goto('/onboarding/signup');

    await page.fill('input[formControlName="invitation_token"]', 'not-a-real-invitation-token');
    await page.fill('input[formControlName="business_name"]', `Rejected Co ${stamp}`);
    await page.fill('input[formControlName="email"]', `e2e.rejected.${stamp}@example.test`);
    await page.fill('input[formControlName="password"]', 'E2eRejectedPassword123!');

    await chooseFirstOption(page, 'region');
    await chooseFirstOption(page, 'currency');
    await chooseFirstOption(page, 'tax_model');

    await page.click('button[type="submit"]');

    // Refused, and still on sign-up — not signed in to anything.
    await expect(page).toHaveURL(/signup/);
    await expect(page.locator('.error-banner, .error-message, mat-error').first()).toBeVisible();
  });
});
