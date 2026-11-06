import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import { createMember } from './support/api';

/**
 * P-159: axe on the populated RFQ compare page (two replies, landed totals, coverage), English
 * and Arabic (RTL). Mocked API, so no RFQ send or extraction pipeline is needed.
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const RFQ_ID = '00000000-0000-4000-8000-000000000f01';
const P1 = '00000000-0000-4000-8000-0000000000e1';
const P2 = '00000000-0000-4000-8000-0000000000e2';
const S1 = '00000000-0000-4000-8000-0000000000a1';
const S2 = '00000000-0000-4000-8000-0000000000a2';
const T = '00000000-0000-4000-8000-0000000000aa';
const M = '00000000-0000-4000-8000-0000000000ab';

const detail = {
  rfq: {
    id: RFQ_ID,
    tenant_id: T,
    created_by_membership_id: M,
    status: 'sent',
    needed_by_date: '2099-12-01',
    tenant_terms: null,
    idempotency_key: 'k-1',
    created_at: '2026-09-25T09:00:00Z',
  },
  lines: [
    { id: 'l1', tenant_id: T, rfq_id: RFQ_ID, workspace_product_id: P1, quantity: '10', position: 1, product_name: 'Olive oil 5L', created_at: '2026-09-25T09:00:00Z' },
    { id: 'l2', tenant_id: T, rfq_id: RFQ_ID, workspace_product_id: P2, quantity: '4', position: 2, product_name: 'Sugar 25kg', created_at: '2026-09-25T09:00:00Z' },
  ],
  recipients: [S1, S2].map((s, i) => ({
    id: `r${i}`, tenant_id: T, rfq_id: RFQ_ID, supplier_id: s, status: 'sent',
    outbound_message_id: null, sent_at: '2026-09-25T09:05:00Z', created_at: '2026-09-25T09:00:00Z',
  })),
};

const response = (id: string, supplier: string, name: string, prices: [string, string]) => ({
  id,
  rfq_id: RFQ_ID,
  supplier_id: supplier,
  supplier_name: name,
  quotation_id: `q-${id}`,
  quotation_status: 'reviewed',
  submitted_at: '2026-09-25T10:00:00Z',
  lines: [P1, P2].map((p, i) => ({
    workspace_product_id: p,
    original_text: i === 0 ? 'Olive oil 5L' : 'Sugar 25kg',
    quoted_quantity: i === 0 ? '10' : '4',
    quoted_unit_price_amount: prices[i],
    quoted_unit_price_currency: 'EGP',
    pending_match: false,
  })),
  guardrail_evaluations: [],
  rfq_landed_costs: [
    { workspace_product_id: P1, total: { amount: (Number(prices[0]) * 10).toFixed(4), currency: 'EGP' } },
    { workspace_product_id: P2, total: { amount: (Number(prices[1]) * 4).toFixed(4), currency: 'EGP' } },
  ],
});

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

async function json(page: Page, glob: string | RegExp, body: unknown): Promise<void> {
  await page.route(glob, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

test.describe('RFQ compare accessibility @a11y', () => {
  test.setTimeout(240_000);

  test('populated compare page (en + ar)', async ({ page }) => {
    const member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');

    await json(page, /\/api\/v1\/rfq\/guardrails/, []);
    await json(page, new RegExp(`/api/v1/rfq/${RFQ_ID}(\\?.*)?$`), detail);
    await json(page, new RegExp(`/api/v1/rfq/${RFQ_ID}/responses`), {
      items: [response('resp-1', S1, 'Delta Foods', ['100', '40']), response('resp-2', S2, 'Nile Traders', ['95', '44'])],
    });
    await json(page, '**/api/v1/suppliers*', {
      items: [{ id: S1, name: 'Delta Foods', status: 'active', created_at: '2026-08-01T00:00:00Z' }, { id: S2, name: 'Nile Traders', status: 'active', created_at: '2026-08-01T00:00:00Z' }],
      next_cursor: null,
    });
    await json(page, '**/api/v1/products*', {
      items: [
        { id: P1, tenant_name: 'Olive oil 5L', canonical_name: 'Olive oil', base_unit: 'litre', pack: { pack_count: 1, unit_size: '5' }, status: 'active', created_at: '2026-08-01T00:00:00Z' },
        { id: P2, tenant_name: 'Sugar 25kg', canonical_name: 'Sugar', base_unit: 'kilogram', pack: { pack_count: 1, unit_size: '25' }, status: 'active', created_at: '2026-08-01T00:00:00Z' },
      ],
      next_cursor: null,
    });
    await json(page, '**/api/v1/members*', { items: [], next_cursor: null });
    await json(page, '**/api/v1/branches*', { items: [], next_cursor: null });

    await page.goto(`/rfq/compare/${RFQ_ID}`);
    await expect(page.getByText('Delta Foods').first()).toBeVisible();
    expect(await scan(page)).toBe('');

    await useArabic(page);
    await expect(page.getByText('Delta Foods').first()).toBeVisible();
    expect(await scan(page)).toBe('');
  });
});
