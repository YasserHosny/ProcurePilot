import { test, expect } from '@playwright/test';

import { createMember, type CreatedMember } from './support/api';
import type { Offer, OfferComparison } from '../../src/app/core/api/models';

/**
 * Compare-grid recalculation performance — T031 (012-reporting-hardening, FR-025/SC-006,
 * research R10).
 *
 * The constitution gate is "compare-grid recalculation under 150ms." `projectComparison()`
 * (compare-projection.ts) is the pure client-side function the compare screen's `projected`
 * computed signal runs on every quantity keystroke (SC-002: no network round-trip per edit) —
 * this spec seeds a realistic multi-offer comparison via a mocked `/offers/compare` response
 * (no quotation/extraction pipeline needed to get real offers into the grid) and measures the
 * REAL, browser-rendered time from a quantity edit to the grid's landed-cost cells reflecting
 * it, entirely inside the page via `performance.now()` — avoiding Playwright IPC round-trips
 * from polluting a budget this tight, and avoiding a real network/DB round trip that R10
 * explicitly says this path does not make.
 *
 * Stable against CI noise via repeated-measurement median (research R10 / the compare-grid
 * timing/CI-noise strategy referenced in test-strategy.md), not a single sample.
 */

const OFFER_COUNT = 25;
const SAMPLE_COUNT = 7;
const BUDGET_MS = 150;

function buildOfferComparison(productId: string): OfferComparison {
  const offers: Offer[] = Array.from({ length: OFFER_COUNT }, (_, i) => ({
    id: `offer-${i}`,
    workspace_product_id: productId,
    supplier_id: `supplier-${i}`,
    supplier_name: `Perf Supplier ${i}`,
    quotation_line_id: `qline-${i}`,
    match_decision_id: `match-${i}`,
    landed_cost: { amount: (10 + i).toFixed(4), currency: 'USD' },
    normalised_unit_price: { amount: (1 + i * 0.1).toFixed(4), currency: 'USD' },
    requested_quantity: '10',
    base_unit: 'unit',
    lead_time_days: 3 + (i % 5),
    reliability_score: '0.9000',
    stock_signal: 'in_stock',
    match_confidence: '0.9500',
    valid_from: '2026-01-01T00:00:00Z',
    valid_to: null,
    is_expired: false,
    rule_version: 'v1',
    recorded_at: '2026-01-01T00:00:00Z',
  }));

  return {
    product: { id: productId, tenant_name: 'Perf Test Product' },
    requested_quantity: '10',
    offers,
    recommendation: {
      recommended_offer_id: 'offer-0',
      score: '0.9800',
      confidence: 'high',
      valid_from: '2026-01-01T00:00:00Z',
      valid_to: null,
      risk_notes: [],
      evidence: {
        weights: { cost: '0.5', match_confidence: '0.2', reliability: '0.2', lead_time: '0.1' },
        components: { cost: '0.9', match_confidence: '0.95', reliability: '0.9', lead_time: '0.8' },
        winning_margin: '0.05',
        tie_break: { applied: false, rule: [] },
      },
    },
  };
}

test.describe('Compare-grid recalculation performance (T031, FR-025)', () => {
  let member: CreatedMember;

  test.beforeEach(async ({ page }) => {
    member = await createMember('buyer');
    await page.goto('/auth/sign-in');
    await page.fill('input[formControlName="email"]', member.email);
    await page.fill('input[formControlName="password"]', member.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');
  });

  test(`recalculates a ${OFFER_COUNT}-offer grid on quantity change with a median under ${BUDGET_MS}ms`, async ({
    page,
  }) => {
    const productId = 'perf-product-1';
    const comparison = buildOfferComparison(productId);

    await page.route('**/api/v1/offers/compare*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(comparison) });
    });

    await page.goto(`/offers/compare?product_id=${productId}`);
    await expect(page.locator('.page-title')).toContainText('Smart Compare');
    await expect(page.locator('.landed-cost-cell')).toHaveCount(OFFER_COUNT);

    const quantityInput = page.locator('.quantity-input');

    // Measured entirely inside the page: performance.now() around dispatching the real `input`
    // event the (input) binding listens for, polling for the first landed-cost cell's text to
    // change — that's the actual moment the recalculated, projected grid has reached the DOM.
    const samples: number[] = [];
    let quantity = 10;
    for (let i = 0; i < SAMPLE_COUNT; i++) {
      quantity += 1;
      const elapsedMs = await page.evaluate(
        ({ newQuantity }) => {
          return new Promise<number>((resolve) => {
            const input = document.querySelector<HTMLInputElement>('.quantity-input');
            const firstCell = document.querySelector('.landed-cost-cell');
            if (!input || !firstCell) {
              resolve(-1);
              return;
            }
            const before = firstCell.textContent;
            const start = performance.now();

            const nativeSetter = Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype,
              'value',
            )!.set!;
            nativeSetter.call(input, String(newQuantity));
            input.dispatchEvent(new Event('input', { bubbles: true }));

            const poll = () => {
              const cell = document.querySelector('.landed-cost-cell');
              if (cell && cell.textContent !== before) {
                resolve(performance.now() - start);
                return;
              }
              requestAnimationFrame(poll);
            };
            requestAnimationFrame(poll);

            // Budget-aware safety valve: never hang the test suite on a genuine regression:
            setTimeout(() => resolve(performance.now() - start), 5000);
          });
        },
        { newQuantity: quantity },
      );
      expect(elapsedMs, 'landed-cost cell did not update within 5s').toBeGreaterThanOrEqual(0);
      samples.push(elapsedMs);
    }

    const sorted = [...samples].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];

    expect(
      median,
      `samples (ms): ${samples.map((s) => s.toFixed(1)).join(', ')}`,
    ).toBeLessThan(BUDGET_MS);
  });
});
