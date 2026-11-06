import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import { createMember } from './support/api';

/**
 * P-159: axe on the Matching screens in a populated state, English and Arabic (RTL). The existing
 * matching-a11y spec only reaches the empty queue and an error state; these drive the real
 * screens with mocked API responses (no extraction pipeline needed):
 *  - the resolution page with candidates and the catalogue picker (P-151) showing results,
 *  - the Correct-match dialog on a decided line,
 *  - the queue with an open task.
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const LINE_ID = '00000000-0000-4000-8000-000000000a01';
const QUOTATION_ID = '00000000-0000-4000-8000-000000000a02';
const TASK_ID = '00000000-0000-4000-8000-000000000a03';
const SUPPLIER_ID = '00000000-0000-4000-8000-000000000a04';

const product = (id: string, name: string) => ({
  id,
  tenant_name: name,
  canonical_name: name,
  brand: null,
  variant: null,
  gtin: null,
  base_unit: 'litre',
  status: 'active',
});

const candidate = (n: number, name: string, confidence: string) => ({
  id: `00000000-0000-4000-8000-0000000000c${n}`,
  quotation_line_id: LINE_ID,
  candidate_product: product(`00000000-0000-4000-8000-0000000000b${n}`, name),
  confidence,
  reasons: {
    alias_hit: false,
    gtin_match: false,
    supplier_code_match: false,
    lexical_similarity: '0.8800',
    semantic_similarity: '0.8000',
  },
  rank: n,
  scoring_version: 'v1.0',
  created_at: '2026-08-21T01:00:00Z',
});

const candidates = [candidate(1, 'Farm Whole Milk 2L', '0.8200'), candidate(2, 'Farm Semi-Skimmed Milk 2L', '0.7400')];

const quotation = {
  id: QUOTATION_ID,
  status: 'reviewed',
  source_filename: 'quotation.pdf',
  line_count: 1,
  open_match_task_count: 1,
  supplier_id: SUPPLIER_ID,
  supplier_name: 'Fresh Farms Dairy',
};

const line = {
  id: LINE_ID,
  line_number: 1,
  original_text: 'Fresh Farm Whole Milk 2L',
  quantity: '10',
  pack: { pack_count: 1, unit_size: '2.0', unit: 'litre' },
  unit_price: { amount: '2.50', currency: 'GBP' },
  quoted_line_total: { amount: '25.0000', currency: 'GBP' },
};

const openTask = {
  id: TASK_ID,
  quotation_id: QUOTATION_ID,
  quotation,
  quotation_line: line,
  status: 'open',
  priority: 'normal',
  reason: 'low_confidence',
  candidates,
  created_at: '2026-08-21T01:00:00Z',
  supplier_name: 'Fresh Farms Dairy',
};

const decision = {
  id: '00000000-0000-4000-8000-000000000d01',
  quotation_line_id: LINE_ID,
  matched_product: candidates[0].candidate_product,
  selected_match_candidate_id: candidates[0].id,
  outcome: 'same_product',
  is_automatic: false,
  decided_by: '00000000-0000-4000-8000-000000000e01',
  decided_at: '2026-08-21T02:00:00Z',
  confidence: '0.8200',
};

const decidedTask = { ...openTask, status: 'resolved', decision, matched_product: decision.matched_product };

async function scan(page: Page): Promise<string> {
  const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA).exclude('.nav-item.disabled').analyze();
  return results.violations.map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`).join('\n');
}

async function useArabic(page: Page): Promise<void> {
  await page.click('.account-btn');
  await page.locator('button:has-text("العربية")').click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('.mat-mdc-menu-panel')).toHaveCount(0);
}

async function json(page: Page, glob: string, body: unknown): Promise<void> {
  await page.route(glob, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

test.describe('Matching populated screens @a11y', () => {
  test.setTimeout(240_000);

  test.beforeEach(async ({ page }) => {
    const member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
    await json(page, '**/api/v1/reference/base-units*', {
      items: [{ code: 'litre', label_en: 'Litre (L)', label_ar: 'لتر (L)', dimension: 'volume' }],
    });
    await json(page, '**/api/v1/suppliers*', {
      items: [{ id: SUPPLIER_ID, name: 'Fresh Farms Dairy', status: 'active', created_at: '2026-08-01T00:00:00Z' }],
      next_cursor: null,
    });
    await json(page, '**/api/v1/match-tasks/next*', { next_task_id: null, next_quotation_line_id: null });
    await json(page, '**/api/v1/match-tasks/exact-matches', { count: 0 });
  });

  test('resolution page with candidates and picker results (en + ar)', async ({ page }) => {
    await json(page, `**/api/v1/quotation-lines/${LINE_ID}/match-task`, openTask);
    await json(page, '**/api/v1/products?*', {
      items: [
        { ...product('00000000-0000-4000-8000-0000000000b9', 'Organic Milk 1L'), pack: { pack_count: 1, unit_size: '1' }, created_at: '2026-08-01T00:00:00Z' },
      ],
      next_cursor: null,
    });
    await page.goto(`/matching/${LINE_ID}?quotation_id=${QUOTATION_ID}`);
    await expect(page.locator('app-match-resolution-candidates')).toBeVisible();
    await page.locator('app-product-picker input').fill('milk');
    await expect(page.locator('[data-testid="picker-result"]')).toHaveCount(1);
    expect(await scan(page)).toBe('');

    await useArabic(page);
    await expect(page.locator('[data-testid="picker-result"]')).toHaveCount(1);
    expect(await scan(page)).toBe('');
  });

  test('Correct-match dialog on a decided line (en + ar)', async ({ page }) => {
    await json(page, `**/api/v1/quotation-lines/${LINE_ID}/match-task`, decidedTask);
    await page.goto(`/matching/${LINE_ID}?quotation_id=${QUOTATION_ID}`);
    await page.locator('.correct-match-btn').click();
    await expect(page.locator('app-correct-match-dialog')).toBeVisible();
    expect(await scan(page)).toBe('');
    await page.keyboard.press('Escape');
    await expect(page.locator('app-correct-match-dialog')).toHaveCount(0);

    await useArabic(page);
    await page.locator('.correct-match-btn').click();
    await expect(page.locator('app-correct-match-dialog')).toBeVisible();
    expect(await scan(page)).toBe('');
  });

  test('queue with an open task (en + ar)', async ({ page }) => {
    await json(page, '**/api/v1/match-tasks?*', { items: [openTask], next_cursor: null });
    await page.goto('/matching');
    await expect(page.locator('.queue-result-summary, [data-testid="queue-result-summary"]').first()).toBeVisible();
    expect(await scan(page)).toBe('');

    await useArabic(page);
    expect(await scan(page)).toBe('');
  });
});
