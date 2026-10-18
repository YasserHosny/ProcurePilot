import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import { createMember } from './support/api';
import type { OfferComparison } from '../../src/app/core/api/models';

/**
 * Matching trust signals (spec 004 follow-up, 2026-10-17 demo findings). Both screens are driven
 * by mocked API responses, so no extraction pipeline is needed to reach the states under test:
 *  - Smart Compare: a buyer-confirmed match is "Verified by buyer" (100%, no low-match risk note),
 *    the margin label has a single percent sign, and missing reliability/stock render "—".
 *  - Resolution queue: exact name matches get a one-click "confirm all" that calls the bulk
 *    endpoint (a human action — nothing is auto-accepted).
 * Each screen is scanned with axe in English and Arabic (RTL).
 */

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const PRODUCT_ID = '00000000-0000-4000-8000-0000000000aa';

const comparison: OfferComparison = {
  product: { id: PRODUCT_ID, tenant_name: 'Sugar 25kg' },
  requested_quantity: '10',
  offers: ['A', 'B'].map((tag, i) => ({
    id: `offer-${tag}`,
    workspace_product_id: PRODUCT_ID,
    supplier_id: `supplier-${tag}`,
    supplier_name: `Supplier ${tag}`,
    quotation_line_id: `qline-${tag}`,
    match_decision_id: `match-${tag}`,
    landed_cost: { amount: (100 + i * 4).toFixed(4), currency: 'EGP' },
    normalised_unit_price: { amount: (10 + i * 0.4).toFixed(4), currency: 'EGP' },
    requested_quantity: '10',
    base_unit: 'kg',
    lead_time_days: null,
    reliability_score: null,
    stock_signal: null,
    match_confidence: '1.0000',
    match_verified: true,
    valid_from: '2026-01-01T00:00:00Z',
    valid_to: null,
    is_expired: false,
    rule_version: 'v1',
    recorded_at: '2026-01-01T00:00:00Z',
  })),
  recommendation: {
    recommended_offer_id: 'offer-A',
    score: '0.9000',
    confidence: 'high',
    valid_from: '2026-01-01T00:00:00Z',
    valid_to: null,
    risk_notes: [],
    evidence: {
      weights: { cost: '0.55', match_confidence: '0.20', reliability: '0.15', lead_time: '0.10' },
      components: { cost: '1.0000', match_confidence: '1.0000', reliability: '0.5000', lead_time: '0.5000' },
      winning_margin: '0.0200',
      tie_break: { applied: false, rule: [] },
    },
  },
};

async function scan(page: Page): Promise<string> {
  const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

async function useArabic(page: Page): Promise<void> {
  await page.click('.account-btn');
  await page.locator('button:has-text("العربية")').click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('.mat-mdc-menu-panel')).toHaveCount(0);
}

test.describe('Matching trust signals @a11y', () => {
  // createMember + sign-in against the shared hosted DB is slow; give the two scans room.
  test.setTimeout(180_000);

  test.beforeEach(async ({ page }) => {
    const member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test('compare shows verified match, one percent sign and dash empty states (en + ar)', async ({ page }) => {
    await page.route('**/api/v1/offers/compare*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(comparison) }),
    );
    // The compare page now loads the selected product itself when it is not in the catalogue
    // list (it needs the pack size); mock that lookup for this synthetic product.
    await page.route(`**/api/v1/products/${PRODUCT_ID}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: PRODUCT_ID,
          tenant_name: 'Synthetic product',
          canonical_name: 'Synthetic product',
          base_unit: 'kilogram',
          pack: { pack_count: 1, unit_size: '1' },
          status: 'active',
          created_at: '2026-08-01T00:00:00Z',
        }),
      }),
    );

    await page.goto(`/offers/compare?product_id=${PRODUCT_ID}`);
    await expect(page.locator('.landed-cost-cell')).toHaveCount(2);

    const badges = page.locator('[data-testid="match-verified-badge"]');
    await expect(badges).toHaveCount(2);
    await expect(badges.first()).toContainText('Verified by buyer');
    const body = (await page.locator('body').innerText()) ?? '';
    expect(body).not.toContain('%%');
    expect(body).not.toContain('Low match');
    expect(body).not.toContain('below 85%');
    expect(body).not.toContain('No rating');
    await expect(page.locator('[aria-label="Not enough data"]').first()).toBeVisible();
    expect(await scan(page)).toBe('');

    await useArabic(page);
    await expect(page.locator('[data-testid="match-verified-badge"]').first()).toContainText('تم التحقق');
    expect(await scan(page)).toBe('');
  });

  test('queue bulk-confirms exact name matches with one human click (en + ar)', async ({ page }) => {
    let count = 2;
    let confirmCalls = 0;
    await page.route('**/api/v1/match-tasks/exact-matches', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ count }) }),
    );
    await page.route('**/api/v1/match-tasks/confirm-exact', (route) => {
      confirmCalls += 1;
      count = 0;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ confirmed: 2, skipped: 0 }),
      });
    });

    await page.goto('/matching');
    const banner = page.locator('[data-testid="exact-match-banner"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('2 exact name matches');
    expect(await scan(page)).toBe('');

    await useArabic(page);
    await expect(banner).toContainText('2');
    expect(await scan(page)).toBe('');

    await page.locator('[data-testid="confirm-exact-btn"]').click();
    await expect(page.locator('[data-testid="exact-match-result"]')).toBeVisible();
    await expect(banner).toHaveCount(0);
    expect(confirmCalls).toBe(1);
  });
});
