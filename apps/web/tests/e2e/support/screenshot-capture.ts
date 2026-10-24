import { expect, type Page } from '@playwright/test';

export async function waitForNoVisibleLoading(page: Page): Promise<void> {
  await page.waitForFunction(
    () => {
      const selectors = [
        '.loading-state',
        '.loading-container',
        '.progress-card',
        'mat-spinner:not(.button-spinner):not(.btn-spinner):not(.inline-spinner)',
      ];
      return selectors.every((selector) =>
        Array.from(document.querySelectorAll(selector)).every((element) => {
          const style = window.getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return style.display === 'none' || style.visibility === 'hidden' ||
            rect.width === 0 || rect.height === 0;
        }),
      );
    },
    undefined,
    { timeout: 20_000 },
  );
}

/** Publication readiness shared by all gallery captures; no masking or substituted UI. */
export async function settleGallery(page: Page): Promise<void> {
  await waitForNoVisibleLoading(page);
  await page.waitForLoadState('networkidle');
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page.locator('.error-banner, .arithmetic-mismatch-banner')).toHaveCount(0);
  await page.mouse.move(0, 0);
}
