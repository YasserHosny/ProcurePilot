import { test, expect, type Page } from '@playwright/test';

import { createMember } from './support/api';

/**
 * P-159: the resolve flow works from the keyboard alone, and the arrow keys follow the reading
 * direction (in Arabic the left arrow moves forward, as the next-row direction is mirrored).
 * Mocked API, so no extraction pipeline is needed.
 */

const LINE_ID = '00000000-0000-4000-8000-000000000b01';
const QUOTATION_ID = '00000000-0000-4000-8000-000000000b02';
const SUPPLIER_ID = '00000000-0000-4000-8000-000000000b04';
const CAND = [1, 2, 3].map((n) => `00000000-0000-4000-8000-0000000000c${n}`);

const candidate = (n: number, name: string, confidence: string) => ({
  id: CAND[n - 1],
  quotation_line_id: LINE_ID,
  candidate_product: {
    id: `00000000-0000-4000-8000-0000000000d${n}`,
    tenant_name: name,
    canonical_name: name,
    brand: null,
    variant: null,
    gtin: null,
    base_unit: 'litre',
    status: 'active',
  },
  confidence,
  reasons: { alias_hit: false, gtin_match: false, supplier_code_match: false },
  rank: n,
  scoring_version: 'v1.0',
  created_at: '2026-08-21T01:00:00Z',
});

const task = {
  id: '00000000-0000-4000-8000-000000000b03',
  quotation_id: QUOTATION_ID,
  quotation: {
    id: QUOTATION_ID,
    status: 'reviewed',
    source_filename: 'quotation.pdf',
    line_count: 1,
    open_match_task_count: 1,
    supplier_id: SUPPLIER_ID,
    supplier_name: 'Fresh Farms Dairy',
  },
  quotation_line: {
    id: LINE_ID,
    line_number: 1,
    original_text: 'Fresh Farm Whole Milk 2L',
    quantity: '10',
    pack: { pack_count: 1, unit_size: '2.0', unit: 'litre' },
    unit_price: { amount: '2.50', currency: 'GBP' },
    quoted_line_total: { amount: '25.0000', currency: 'GBP' },
  },
  status: 'open',
  priority: 'normal',
  // Close candidates: nothing is pre-selected, so the buyer must choose.
  reason: 'close_candidates',
  candidates: [
    candidate(1, 'Farm Whole Milk 2L', '0.8200'),
    candidate(2, 'Farm Semi-Skimmed Milk 2L', '0.8100'),
    candidate(3, 'Farm Skimmed Milk 2L', '0.7900'),
  ],
  created_at: '2026-08-21T01:00:00Z',
  supplier_name: 'Fresh Farms Dairy',
};

async function json(page: Page, glob: string, body: unknown, status = 200): Promise<void> {
  await page.route(glob, (route) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function useArabic(page: Page): Promise<void> {
  await page.click('.account-btn');
  await page.locator('button:has-text("العربية")').click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('.mat-mdc-menu-panel')).toHaveCount(0);
}

test.describe('Matching keyboard and RTL @a11y', () => {
  test.setTimeout(240_000);

  let resolveBodies: unknown[];

  test.beforeEach(async ({ page }) => {
    resolveBodies = [];
    const member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
    await json(page, '**/api/v1/reference/base-units*', {
      items: [{ code: 'litre', label_en: 'Litre (L)', label_ar: 'لتر (L)', dimension: 'volume' }],
    });
    await json(page, '**/api/v1/suppliers*', { items: [], next_cursor: null });
    await json(page, '**/api/v1/match-tasks/next*', { next_task_id: null, next_quotation_line_id: null });
    await json(page, `**/api/v1/quotation-lines/${LINE_ID}/match-task`, task);
    await json(page, `**/api/v1/quotation-lines/${LINE_ID}/landed-cost`, {}, 404);
    await page.route(`**/api/v1/quotation-lines/${LINE_ID}/match`, async (route) => {
      resolveBodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '00000000-0000-4000-8000-000000000e01',
          quotation_line_id: LINE_ID,
          matched_product: task.candidates[1].candidate_product,
          selected_match_candidate_id: CAND[1],
          outcome: 'same_product',
          is_automatic: false,
          decided_by: '00000000-0000-4000-8000-000000000e02',
          decided_at: '2026-08-21T02:00:00Z',
          confidence: '0.8100',
        }),
      });
    });
  });

  test('resolve a line with the keyboard only', async ({ page }) => {
    await page.goto(`/matching/${LINE_ID}?quotation_id=${QUOTATION_ID}`);
    await expect(page.locator('app-match-resolution-candidates')).toBeVisible();

    // Number key picks the second candidate; Ctrl+Enter confirms. No mouse involved.
    await page.locator('body').click({ position: { x: 1, y: 1 } });
    await page.keyboard.press('2');
    await expect(page.locator('input[type="radio"]:checked').first()).toHaveValue(CAND[1]);
    await page.keyboard.press('Control+Enter');
    await expect.poll(() => resolveBodies.length).toBe(1);
    expect(resolveBodies[0]).toMatchObject({
      outcome: 'same_product',
      selected_match_candidate_id: CAND[1],
    });
  });

  test('Enter on a focused link does not confirm the match', async ({ page }) => {
    await page.goto(`/matching/${LINE_ID}?quotation_id=${QUOTATION_ID}`);
    await expect(page.locator('app-match-resolution-candidates')).toBeVisible();
    await page.keyboard.press('2');
    await page.getByRole('link').first().focus();
    await page.keyboard.press('Enter');
    expect(resolveBodies.length).toBe(0);
  });

  test('arrow keys follow the reading direction (en: Right/Down forward; ar: Left forward)', async ({ page }) => {
    await page.goto(`/matching/${LINE_ID}?quotation_id=${QUOTATION_ID}`);
    await expect(page.locator('app-match-resolution-candidates')).toBeVisible();
    await page.locator('body').click({ position: { x: 1, y: 1 } });
    await page.keyboard.press('1');
    await expect(page.locator('input[type="radio"]:checked').first()).toHaveValue(CAND[0]);
    await page.keyboard.press('ArrowDown');
    await expect(page.locator('input[type="radio"]:checked').first()).toHaveValue(CAND[1]);
    await page.keyboard.press('ArrowUp');
    await expect(page.locator('input[type="radio"]:checked').first()).toHaveValue(CAND[0]);

    await useArabic(page);
    await page.locator('body').click({ position: { x: 1, y: 1 } });
    await page.keyboard.press('1');
    await expect(page.locator('input[type="radio"]:checked').first()).toHaveValue(CAND[0]);
    // In RTL the next candidate lies to the left.
    await page.keyboard.press('ArrowLeft');
    await expect(page.locator('input[type="radio"]:checked').first()).toHaveValue(CAND[1]);
    await page.keyboard.press('ArrowRight');
    await expect(page.locator('input[type="radio"]:checked').first()).toHaveValue(CAND[0]);
  });
});
