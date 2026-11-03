import type { Offer, OfferComparison, Recommendation } from '../offers-api';
import { projectComparison } from './compare-projection';

describe('projectComparison (P-157, PPS-201)', () => {
  const offer = (id: string, supplier: string, total: string, currency: string): Offer => ({
    id,
    workspace_product_id: 'prod-1',
    supplier_id: supplier,
    supplier_name: supplier,
    quotation_line_id: `ql-${id}`,
    match_decision_id: `md-${id}`,
    landed_cost: { amount: total, currency },
    normalised_unit_price: { amount: '1.0000', currency },
    requested_quantity: '10.000000',
    base_unit: 'kilogram',
    lead_time_days: 2,
    reliability_score: '0.900',
    stock_signal: null,
    match_confidence: '0.9500',
    valid_from: '2026-08-01T00:00:00Z',
    valid_to: null,
    is_expired: false,
    rule_version: 'landed-cost-v2',
    recorded_at: '2026-08-01T00:00:00Z',
  });

  const recommendation = (offerId: string, extraWeights: Record<string, string> = {}): Recommendation => ({
    recommended_offer_id: offerId,
    score: '0.9000',
    confidence: 'high',
    valid_from: '2026-08-01T00:00:00Z',
    valid_to: null,
    risk_notes: [],
    evidence: {
      weights: { cost: '0.55', match_confidence: '0.20', reliability: '0.15', lead_time: '0.10', ...extraWeights },
      components: { cost: '1.0000', match_confidence: '0.9500', reliability: '0.9000', lead_time: '0.9333' },
      winning_margin: '0.1000',
      tie_break: { applied: false, rule: [] },
    },
  });

  const comparison = (offers: Offer[], rec: Recommendation): OfferComparison => ({
    product: { id: 'prod-1', tenant_name: 'Rice' },
    requested_quantity: '10.000000',
    offers,
    recommendation: rec,
  });

  it('does not rank offers quoted in different currencies against each other', () => {
    // SAR 100 and USD 30 are not comparable; the server picked the SAR offer.
    const original = comparison(
      [offer('sar', 'supp-a', '100.0000', 'SAR'), offer('usd', 'supp-b', '30.0000', 'USD')],
      recommendation('sar'),
    );

    const projected = projectComparison(original, '20');

    expect(projected?.recommendation?.recommended_offer_id).toBe('sar');
    // The totals are still projected per offer.
    expect(projected?.offers.find((o) => o.id === 'usd')?.projected_landed_cost.amount).toBe('60.0000');
  });

  it('keeps the server recommendation when the server scored with Supplier IQ weights', () => {
    const original = comparison(
      [offer('a', 'supp-a', '100.0000', 'SAR'), offer('b', 'supp-b', '90.0000', 'SAR')],
      {
        ...recommendation('a', { supplier_risk: '0.15' }),
        evidence: {
          ...recommendation('a').evidence,
          weights: { cost: '0.45', match_confidence: '0.17', reliability: '0.13', lead_time: '0.10', supplier_risk: '0.15' },
          components: { cost: '0.9', match_confidence: '0.95', reliability: '0.9', lead_time: '0.93', supplier_risk: '0.2' },
        },
      },
    );

    const projected = projectComparison(original, '20');

    expect(projected?.recommendation).toEqual(original.recommendation);
  });

  it('still rescores same-currency offers scored without Supplier IQ', () => {
    const original = comparison(
      [offer('a', 'supp-a', '100.0000', 'SAR'), offer('b', 'supp-b', '90.0000', 'SAR')],
      recommendation('a'),
    );

    const projected = projectComparison(original, '20');

    expect(projected?.recommendation?.recommended_offer_id).toBe('b');
  });
});
