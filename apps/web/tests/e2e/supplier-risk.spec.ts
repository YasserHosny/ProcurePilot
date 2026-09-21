import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { credentials, setOwnerLocale } from './support/api';

const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const VALID_UNTIL = '2099-09-21T12:00:00Z';

const riskSnapshot = {
  id: 'snapshot-001',
  supplier_id: 'supplier-001',
  supplier_name: 'Alfaisal Trade',
  window_start: '2026-03-24',
  window_end: '2026-09-20',
  state: 'ready',
  confidence: 'high',
  release_posture: 'g3_unmet',
  valid_from: '2026-09-20T12:00:00Z',
  valid_until: VALID_UNTIL,
  source_fingerprint: 'fingerprint-001',
  observed_history_days: 180,
  risk_score: {
    total: '0.7200',
    components: {
      concentration: '0.7200',
      price_drift: '0.4100',
      reliability: '0.2500',
      single_source: '0.6000',
    },
    weights: {
      concentration: '0.3000',
      price_drift: '0.2500',
      reliability: '0.3000',
      single_source: '0.1500',
    },
  },
  risk_level: 'high',
  computed_at: '2026-09-20T12:00:00Z',
};

const component = (risk: string, sourceKind = 'purchase_order') => ({
  value: risk,
  risk,
  sample_count: 8,
  product_count: 2,
  confidence: 'medium',
  insufficient_evidence: false,
  excluded_counts: { cancelled: 1 },
  source_ids: ['order-001'],
  source_refs: [{ source_id: 'order-001', source_kind: sourceKind }],
  window_start: '2026-03-24',
  split_date: '2026-06-22',
  window_end: '2026-09-20',
  calculation_version: 'supplier-risk-v2',
  currency_buckets: [],
  price_comparisons: [],
  baseline_count: 4,
  current_count: 4,
  baseline_reliability: null,
  current_reliability: null,
  numerator: '2.0000',
  denominator: '8.0000',
});

const scorecard = {
  supplier_id: 'supplier-001',
  window_start: '2026-03-24',
  window_end: '2026-09-20',
  metrics: {},
  risk_score: {
    total: '0.4200',
    confidence: 'medium',
    sub_scores: [],
    rule_version: 'supplier-risk-v1',
  },
  source_counts: {},
  confidence: 'medium',
  insufficient_evidence: false,
  computed_at: '2026-09-20T12:00:00Z',
  rule_version: 'supplier-scorecard-v1',
  snapshot_id: 'snapshot-001',
  state: 'ready',
  risk_level: 'medium',
  release_posture: 'g3_unmet',
  valid_from: '2026-09-20T12:00:00Z',
  valid_until: VALID_UNTIL,
  observed_history_days: 180,
  v2_risk_score: '0.4200',
  v2_weights: {
    concentration: '0.3000',
    price_drift: '0.2500',
    reliability: '0.2500',
    single_source: '0.2000',
  },
  v2_components: {
    concentration: {
      ...component('0.5000'),
      currency_buckets: [
        {
          currency: 'GBP',
          supplier_spend: '420.0000',
          tenant_spend: '1000.0000',
          sample_count: 3,
          share: '0.4200',
          source_ids: ['order-001'],
        },
      ],
    },
    price_drift: component('0.3000', 'landed_cost'),
    reliability: component('0.2500'),
    single_source: component('0.6000', 'workspace_product'),
  },
  source_fingerprint: 'fingerprint-001',
};

const brief = {
  id: 'brief-001',
  supplier_id: 'supplier-001',
  snapshot_id: 'snapshot-001',
  brief_version: 'negotiation-brief-v1',
  source_fingerprint: 'fingerprint-001',
  release_posture: 'g3_unmet',
  valid_from: '2026-09-20T12:00:00Z',
  valid_until: VALID_UNTIL,
  status: 'prepared',
  items: [
    {
      kind: 'concentration_volume',
      rank: 1,
      value: '0.4200',
      amount: { amount: '420.0000', currency: 'GBP' },
      confidence: 'medium',
      risk: '0.4200',
      valid_from: '2026-03-24',
      valid_until: '2099-09-21',
      question_i18n_key: 'negotiationBrief.concentrationVolume.question',
      calculation_version: 'negotiation-brief-v1',
      metric_id: 'metric-001',
      evidence_ids: ['evidence-001'],
      evidence: [
        {
          evidence_id: 'evidence-001',
          source_kind: 'purchase_order',
          source_id: 'order-001',
        },
      ],
    },
  ],
};

function flattenKeys(value: unknown, prefix: string): string[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  );
}

async function signIn(page: Page): Promise<void> {
  const account = credentials();
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', account.ownerEmail);
  await page.fill('input[formControlName="password"]', account.ownerPassword);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

async function installMocks(page: Page): Promise<void> {
  await page.route('**/api/v1/supplier-iq/risks?*', (route) =>
    route.fulfill({ json: { items: [riskSnapshot], next_cursor: null } }),
  );
  await page.route(/\/api\/v1\/suppliers\/supplier-001$/, (route) =>
    route.fulfill({ json: { id: 'supplier-001', name: 'Alfaisal Trade' } }),
  );
  await page.route('**/api/v1/suppliers/supplier-001/scorecard?*', (route) =>
    route.fulfill({ json: scorecard }),
  );
  await page.route('**/api/v1/suppliers/supplier-001/negotiation-briefs', (route) =>
    route.fulfill({ json: brief }),
  );
  await page.route('**/api/v1/negotiation-briefs/brief-001', (route) =>
    route.fulfill({ json: brief }),
  );
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
  expect(
    results.violations,
    results.violations.map((violation) => `${violation.id}: ${violation.help}`).join('\n'),
  ).toEqual([]);
}

async function expectNoPageOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
}

test.describe('Supplier risk accessibility, RTL, and journey @a11y', () => {
  test.beforeEach(async ({ page }) => {
    await setOwnerLocale('en');
    await signIn(page);
    await installMocks(page);
  });

  test('keeps English and Arabic supplier-risk catalogues in exact parity', () => {
    const root = join(__dirname, '..', '..', '..', '..');
    const en = JSON.parse(readFileSync(join(root, 'packages/i18n/en.json'), 'utf8')) as Record<string, unknown>;
    const ar = JSON.parse(readFileSync(join(root, 'packages/i18n/ar.json'), 'utf8')) as Record<string, unknown>;

    for (const namespace of ['supplierRisk', 'negotiationBrief']) {
      expect(flattenKeys(ar[namespace], namespace).sort()).toEqual(
        flattenKeys(en[namespace], namespace).sort(),
      );
    }
  });

  test('navigates queue to scorecard to brief by keyboard with zero axe violations', async ({ page }) => {
    await page.goto('/supplier-risk');
    await expect(page.getByRole('heading', { name: 'Supplier Risk' })).toBeVisible();
    await expectNoAxeViolations(page);

    await page.getByTestId('recompute-risks').focus();
    await page.keyboard.press('Tab');
    await expect(page.locator('.supplier-name')).toBeFocused();
    await page.keyboard.press('Enter');

    await expect(page).toHaveURL(/\/suppliers\/supplier-001\/scorecard/);
    await expect(page.getByRole('heading', { name: 'Supplier Risk Evidence' })).toBeVisible();
    await expectNoAxeViolations(page);

    await page.getByTestId('prepare-brief').focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/negotiation-briefs\/brief-001/);
    await expect(page.getByRole('heading', { name: 'Negotiation Brief', level: 1 })).toBeVisible();
    await expect(page.getByRole('link', { name: /Purchase order.*order-001/ })).toBeVisible();
    await expectNoAxeViolations(page);
  });

  test('renders the queue and brief in Arabic without viewport overlap', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.account-btn').click();
    await page.getByRole('menuitem', { name: /العربية/ }).click();

    await page.goto('/supplier-risk');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByRole('heading', { name: 'مخاطر الموردين' })).toBeVisible();
    await expectNoPageOverflow(page);
    await expectNoAxeViolations(page);

    await page.goto('/negotiation-briefs/brief-001');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByRole('heading', { name: 'موجز التفاوض', level: 1 })).toBeVisible();
    await expectNoPageOverflow(page);
    await expectNoAxeViolations(page);
  });
});
