import { expect, type Locator, type Page } from '@playwright/test';

/**
 * Opens a mat-select whose options arrive asynchronously (reference data, supplier / product /
 * branch / member lookups). MatSelect._canOpen() is false while it has zero options, so a click
 * that lands before the response is silently ignored and the following option lookup then waits
 * forever -- the cause of the intermittent CI failure in the budgets overlap test. Retries the
 * click until an option panel is actually showing. `select` may be the mat-select or any element
 * inside its form field (a click anywhere in the field opens it).
 */
export async function openAsyncSelect(page: Page, select: Locator): Promise<void> {
  // Key on THIS select's own aria-expanded, not on any visible mat-option: a previously used
  // select's panel is still in the DOM while it animates closed.
  const trigger = select.locator('xpath=descendant-or-self::mat-select').first();
  await expect(async () => {
    if ((await trigger.getAttribute('aria-expanded')) !== 'true') {
      await select.click();
    }
    await expect(trigger).toHaveAttribute('aria-expanded', 'true', { timeout: 2000 });
    await expect(page.locator('mat-option').first()).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 15000 });
}
