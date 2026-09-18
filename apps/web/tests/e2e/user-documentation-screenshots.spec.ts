import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test, type Page } from '@playwright/test';

import type { MatchTask } from '../../src/app/core/api/models';
import {
  apiAsUser,
  createMember,
  createPendingInvitation,
  createTestProduct,
  createTestSupplier,
  credentials,
  findProductByName,
  setOwnerLocale,
  signInOwner,
  type Credentials,
} from './support/api';
import {
  confirmQuotation,
  resolveIssueDateFlag,
  correctStatedTotal,
  saveCorrections,
  selectReviewSupplier,
  uploadQuotationAndOpenReview,
} from './support/canonical-flow';

const RUN_CAPTURE = process.env['CAPTURE_USER_DOC_SCREENSHOTS'] === '1';
const REPO_ROOT = join(__dirname, '..', '..', '..', '..');
const SCREENSHOT_DIR = process.env['DOCS_SCREENSHOT_DIR']
  ? (process.env['DOCS_SCREENSHOT_DIR'].startsWith('/')
    ? process.env['DOCS_SCREENSHOT_DIR']
    : join(REPO_ROOT, process.env['DOCS_SCREENSHOT_DIR']))
  : join(REPO_ROOT, 'docs', 'user', 'screenshots');
const VIEWPORT = { width: 1440, height: 900 };
type ScreenshotTarget = 'auto' | 'dialog' | 'sidebar';

interface ScreenshotFixtures {
  ownerToken: string;
  ownerCreds: Credentials;
  product: { id: string; tenant_name: string };
  supplier: { id: string; name: string };
  workflowSupplier: { id: string; name: string };
  quotationId?: string;
  matchTaskId?: string;
  matchedProductId: string;
  savingId: string;
  approvalRequest: { branchName: string; requiredByDate: string };
}

test.describe('User documentation screenshots', () => {
  test.skip(!RUN_CAPTURE, 'Opt-in only: run `pnpm --filter web docs:screenshots`.');
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(240_000);

  let fixtures: ScreenshotFixtures | undefined;

  test.beforeAll(async () => {
    mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test('captures public onboarding and authentication pages', async ({ page }) => {
    await page.setViewportSize(VIEWPORT);

    const ownerToken = await signInOwner();
    const pendingInvitation = await createPendingInvitation('buyer', ownerToken);

    await captureRoute(page, '/auth/sign-in', '01-sign-in.jpg', async () => {
      await expect(page.locator('.card-title')).toContainText('Sign in');
    });

    await captureRoute(page, '/auth/password-reset', '01b-password-reset.jpg', async () => {
      await expect(page.locator('.card-title')).toContainText('Reset');
    });

    await captureRoute(page, '/onboarding/signup', '01c-workspace-signup.jpg', async () => {
      await expect(page.locator('.card-title')).toBeVisible();
      await expect(page.locator('input[formControlName="business_name"]')).toBeVisible();
    });

    await captureRoute(
      page,
      `/onboarding/accept-invitation?token=${encodeURIComponent(pendingInvitation.token)}`,
      '01d-accept-invitation.jpg',
      async () => {
        await expect(page.locator('.card-title')).toBeVisible();
        await expect(page.locator('input[formControlName="password"]')).toBeVisible();
      },
    );
  });

  test('captures authenticated catalogue, quotation, matching, compare, and savings pages', async ({
    page,
  }) => {
    await page.setViewportSize(VIEWPORT);
    fixtures = await buildCommercialFixtures(page);
    await signInAsOwner(page, fixtures.ownerCreds);

    await captureRoute(page, '/home', '02-dashboard.jpg', async () => {
      await expect(page.locator('.hero-title')).toBeVisible();
      await captureCurrentPage(page, '02b-sidebar-navigation.jpg', { target: 'sidebar' });
    });

    await captureRoute(page, '/products', '03-products-list.jpg', async () => {
      await expect(page.locator('tr[mat-row]', { hasText: fixtures.product.tenant_name })).toBeVisible();
    });

    await captureRoute(page, '/products/new', '04-product-form.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Create Product');
      await expect(page.locator('input[formControlName="tenant_name"]')).toBeVisible();
    });

    await captureRoute(page, '/suppliers', '05-suppliers-list.jpg', async () => {
      await expect(page.locator('tr[mat-row]', { hasText: fixtures.supplier.name })).toBeVisible();
    });

    await captureRoute(page, '/suppliers/new', '05b-supplier-form.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Create Supplier');
      await expect(page.locator('input[formControlName="name"]')).toBeVisible();
    });

    await captureRoute(page, '/import', '06-import-wizard.jpg', async () => {
      await expect(page.locator('.page-title')).toBeVisible();
      await expect(page.locator('input[type="file"]')).toBeAttached();
    });

    await captureRoute(page, '/quotations?status=all', '07-quotation-review-queue.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Quotation Review Queue');
      await expect(page.locator('.clickable-row, .empty-state')).toBeVisible();
    });

    await captureRoute(page, '/quotations/upload', '08-quotation-upload.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Upload Supplier Quotation');
      await expect(page.locator('input.file-input')).toBeAttached();
    });

    if (fixtures.quotationId) {
      await captureRoute(
        page,
        `/quotations/${fixtures.quotationId}/review`,
        '08b-quotation-review.jpg',
        async () => {
          await expect(page.locator('.page-title')).toContainText('Quotation Review');
          await expect(page.locator('.audit-trail-panel')).toBeVisible();
        },
      );

      await captureRoute(
        page,
        `/quotations/${fixtures.quotationId}/review`,
        '08c-quotation-review-lines.jpg',
        async () => {
          await expect(page.locator('.lines-card')).toBeVisible();
          await page.locator('.lines-card').first().scrollIntoViewIfNeeded();
        },
      );
    }

    await captureDocumentedMatchQueue(page);

    await captureRoute(page, `/offers/compare?product_id=${fixtures.matchedProductId}`, '10-smart-compare.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Smart Compare');
      await expect(page.locator('.recommendation-card, .empty-state-card')).toBeVisible();
    });

    await captureRoute(
      page,
      `/offers/product-intelligence?product_id=${fixtures.matchedProductId}`,
      '10b-product-intelligence.jpg',
      async () => {
        await expect(page.locator('.page-title')).toContainText('Product Price Intelligence');
        await expect(page.locator('.metrics-grid, .empty-state-card')).toBeVisible();
      },
    );

    await captureRoute(page, '/offers/basket-split', '11-basket-split.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Two-Supplier Basket Split');
      await expect(page.locator('.form-card, .result-summary-card, .infeasible-card')).toBeVisible();
    });

    await page.goto('/offers/basket-split');
    await expect(page.locator('.page-title')).toContainText('Two-Supplier Basket Split');
    await waitForNoVisibleLoading(page);
    const submitBasket = page.locator('.submit-btn');
    if ((await submitBasket.count()) > 0 && await submitBasket.isEnabled()) {
      await submitBasket.click();
      await expect(
        page.locator('.job-progress-card, .result-summary-card, .infeasible-card, .error-banner').first(),
      ).toBeVisible({ timeout: 15_000 });
    }
    await captureCurrentPage(page, '11b-basket-split-processing.jpg', {
      allowVisibleLoading: true,
    });

    await captureRoute(page, '/alerts', '12-alerts-inbox.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Actionable Alerts Inbox');
      await waitForNoVisibleLoading(page);
      await expect(page.locator('.alerts-list, .empty-state-card')).toBeVisible();
    });

    await captureRoute(page, '/savings', '13-savings-ledger.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Savings Ledger');
      await expect(page.locator('.savings-table, .empty-state')).toBeVisible();
    });

    await captureRoute(page, '/savings/outcome-capture', '13b-outcome-capture.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Record Purchase Outcome');
      await expect(page.locator('form')).toBeVisible();
    });

    await captureRoute(page, `/savings/${fixtures.savingId}/evidence`, '13c-saving-evidence.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Saving Evidence');
      await expect(page.locator('.summary-card, .pending-banner, .immutable-banner')).toBeVisible();
    });

    await captureRoute(page, '/savings/export', '14-export-savings.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Export Savings Ledger');
      await expect(page.locator('.export-form')).toBeVisible();
    });
  });

  test('captures request, approval, team, and organisation settings pages', async ({ page }) => {
    await page.setViewportSize(VIEWPORT);
    if (!fixtures) {
      throw new Error('Commercial fixtures were not created by the previous serial screenshot test.');
    }
    await signInAsOwner(page, fixtures.ownerCreds);

    await captureRoute(page, '/requests', '15-purchase-requests-empty.jpg', async () => {
      await expect(page.locator('.section-title')).toContainText('Purchase Requests');
      await expect(page.locator('.requests-table, .empty-state')).toBeVisible();
    });

    await captureRoute(page, '/requests/new', '16-request-form.jpg', async () => {
      await expect(page.locator('.form-title')).toContainText('New Purchase Request');
      await expect(page.locator('mat-select[formControlName="branch_id"]')).toBeVisible();
    });

    await captureRoute(page, '/approvals', '17-approval-queue.jpg', async () => {
      await expect(page.locator('.approval-queue-title')).toContainText('Approval Queue');
      await expect(page.locator('tr.request-row, .empty-state').first()).toBeVisible();
    });

    await captureRoute(page, '/team', '18-team-management.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Team Management');
      await expect(page.locator('.members-table, .empty-state')).toBeVisible();
    });

    await captureRoute(page, '/settings', '19-settings.jpg', async () => {
      await expect(page.locator('.settings-title')).toContainText('Organisation Settings');
      await expect(page.locator('app-branch-list tr[mat-row]', { hasText: fixtures.approvalRequest.branchName })).toBeVisible();
    });

    await page.goto('/settings');
    await waitForNoVisibleLoading(page);
    await page.locator('app-cost-centre-list .action-btn').click();
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    await captureCurrentPage(page, '19b-cost-centre-form.jpg', {
      allowVisibleLoading: false,
      target: 'dialog',
    });
    await page.keyboard.press('Escape');

    await page.locator('app-budget-list .action-btn').click();
    await expect(page.locator('mat-dialog-container')).toBeVisible();
    await captureCurrentPage(page, '19c-budget-form.jpg', {
      allowVisibleLoading: false,
      target: 'dialog',
    });
  });

  test('captures automated ingestion dashboard and email log pages', async ({ page }) => {
    await page.setViewportSize(VIEWPORT);
    if (!fixtures) {
      throw new Error('Commercial fixtures were not created by the previous serial screenshot test.');
    }
    await signInAsOwner(page, fixtures.ownerCreds);
    await seedIngestionData(page, fixtures);

    await page.setViewportSize({ width: 1440, height: 1250 });
    await captureRoute(page, '/ingestion', '26-ingestion-dashboard.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Ingestion Dashboard');
      await waitForNoVisibleLoading(page);
      await expect(page.locator('.recent-emails-table')).toBeVisible();
    });
    await page.setViewportSize(VIEWPORT);

    await captureRoute(page, '/ingestion/email-log', '28-email-ingestion-log.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Email Inbound Log');
      await waitForNoVisibleLoading(page);
      await expect(page.locator('.email-log-table')).toBeVisible();
    });
  });
});

async function buildCommercialFixtures(page: Page): Promise<ScreenshotFixtures> {
  const ownerToken = await signInOwner();
  const ownerCreds = credentials();
  await setOwnerLocale('en');

  const stamp = Date.now();
  const product = await createTestProduct(ownerToken, {
    tenant_name: `Docs Capture Copy Paper ${stamp}`,
    base_unit: 'each',
    pack_count: 5,
    unit_size: '80',
    brand: 'DocsCo',
  });
  const supplier = await createTestSupplier(ownerToken, `Docs Capture Supplier ${stamp}`);
  const workflowSupplier = await createTestSupplier(ownerToken, `Docs Capture Quote Supplier ${stamp}`);

  let quotationId: string | undefined;
  let matchTaskId: string | undefined;
  let matchedProductId = product.id;

  try {
    await signInAsOwner(page, ownerCreds);
    quotationId = await uploadQuotationAndOpenReview(page, `docs_capture_${stamp}.pdf`);
    await selectReviewSupplier(page, workflowSupplier.name);
    await correctStatedTotal(page);
    await resolveIssueDateFlag(page);
    await saveCorrections(page);
    const matchedProduct = await captureAndResolveMatchScreenshots(
      page,
      quotationId,
      `Docs Capture Tomatoes ${stamp}`,
    );
    matchedProductId = matchedProduct.id;
  } catch {
    const existingMatch = await discoverExistingMatchTask(ownerToken);
    matchTaskId = existingMatch?.id;
    quotationId = existingMatch?.quotationId ?? (await discoverExistingQuotationId(page));
    if (matchTaskId) {
      await captureExistingMatchScreenshots(page, matchTaskId);
    }
  }

  const purchase = await apiAsUser<{ saving_record: { id: string } }>(
    ownerToken,
    'POST',
    '/purchases',
    {
      workspace_product_id: matchedProductId,
      supplier_id: supplier.id,
      quantity: '10',
      base_unit: 'each',
      unit_price: { amount: '1.20', currency: 'GBP' },
      total_paid: { amount: '12.00', currency: 'GBP' },
      delivery_result: 'delivered',
      ordered_at: '2026-08-21T00:00:00Z',
      notes: 'Documentation screenshot fixture',
    },
  );

  const branch = await apiAsUser<{ id: string; name: string }>(ownerToken, 'POST', '/organisation/branches', {
    name: `Docs Capture Branch ${stamp}`,
    address: '42 Documentation Road',
    region: 'GB',
  });
  await apiAsUser(ownerToken, 'POST', '/organisation/cost-centres', {
    name: `Docs Capture Cost Centre ${stamp}`,
    code: `DOCS-${String(stamp).slice(-6)}`,
    branch_id: branch.id,
  });
  await apiAsUser(ownerToken, 'POST', '/organisation/budgets', {
    amount: '5000',
    currency: 'GBP',
    period: 'monthly',
    period_start: '2026-09-01',
    scope: 'branch',
    branch_id: branch.id,
  });
  const request = await apiAsUser<{ id: string }>(ownerToken, 'POST', '/requests', {
    branch_id: branch.id,
    required_by_date: '2026-10-15',
    lines: [{ workspace_product_id: product.id, quantity: '3' }],
  });
  await apiAsUser(ownerToken, 'POST', `/requests/${request.id}/submit`);

  await createMember('buyer', ownerToken);

  return {
    ownerToken,
    ownerCreds,
    product,
    supplier,
    workflowSupplier,
    quotationId,
    matchTaskId,
    matchedProductId,
    savingId: purchase.saving_record.id,
    approvalRequest: { branchName: branch.name, requiredByDate: '2026-10-15' },
  };
}

async function seedIngestionData(page: Page, fixtures: ScreenshotFixtures): Promise<void> {
  const { ownerToken, supplier, workflowSupplier, quotationId } = fixtures;

  try {
    await apiAsUser(ownerToken, 'POST', '/tenants/email-config/enable');
  } catch {
    // Ignore if enable already active
  }
  try {
    await apiAsUser(ownerToken, 'PUT', '/tenants/email-config', {
      enabled: true,
      domain_allowlist: ['acmefoods.co.uk', 'freshdirect.example.com'],
    });
  } catch {
    // Ignore if allowlist already active
  }

  // Real document capture upload
  try {
    await page.goto('/ingestion/capture');
    await expect(page.locator('.page-title')).toContainText('Quotation Capture');
    const pdfFixturePath = join(REPO_ROOT, 'apps', 'web', 'tests', 'e2e', 'fixtures', 'test-quotation.pdf');
    await page.locator('input.file-input').first().setInputFiles(pdfFixturePath);
    await expect(page.locator('.selected-file-card')).toBeVisible();
    await page.locator('button.submit-btn').click();
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 25_000 });
  } catch (e) {
    console.warn('Document capture upload failed:', e);
  }

  // Real catalogue import
  try {
    await page.goto('/ingestion/catalogue-import');
    await expect(page.locator('.page-title')).toContainText('Catalogue Import');
    await page.locator('mat-select').click();
    await page.locator('mat-option', { hasText: supplier.name }).click();
    const csvFixturePath = join(REPO_ROOT, 'apps', 'web', 'tests', 'e2e', 'fixtures', 'test-catalogue.csv');
    await page.locator('input.file-input').setInputFiles(csvFixturePath);
    await expect(page.locator('.selected-file-card')).toBeVisible();
    await page.locator('button.submit-btn').click();
    await expect(page.locator('.result-container.success')).toBeVisible({ timeout: 25_000 });
  } catch (e) {
    console.warn('Catalogue import failed:', e);
  }

  // Direct SQL seed for realistic email log entries
  const quoteSql = quotationId ? `'${quotationId}'::uuid` : 'null::uuid';
  const sql = `
    with owner as (
      select m.tenant_id
      from membership m
      where lower(m.email) = lower('${fixtures.ownerCreds.ownerEmail}') and m.status = 'active'
      limit 1
    )
    insert into ingestion_email_log (
      tenant_id, message_id, from_address, from_domain, subject,
      status, error_message, attachment_count, supplier_id, match_method,
      quotation_id, received_at, processed_at
    )
    select
      owner.tenant_id,
      v.message_id,
      v.from_address,
      v.from_domain,
      v.subject,
      v.status::ingestion_email_status,
      v.error_message,
      v.attachment_count,
      v.supplier_id,
      v.match_method,
      v.quotation_id,
      v.received_at,
      v.processed_at
    from owner, (values
      (
        '<quote-2026-0819@acmefoods.co.uk>',
        'orders@acmefoods.co.uk',
        'acmefoods.co.uk',
        'Quotation Q-2026-0819: Weekly Fresh Produce',
        'completed',
        null,
        2,
        '${workflowSupplier.id}'::uuid,
        'domain',
        ${quoteSql},
        now() - interval '45 minutes',
        now() - interval '44 minutes'
      ),
      (
        '<quotes-sep2026@freshdirect.example.com>',
        'quotes@freshdirect.example.com',
        'freshdirect.example.com',
        'Price List Update — Dairy & Ambient Goods Sep 2026',
        'completed',
        null,
        1,
        '${supplier.id}'::uuid,
        'domain',
        null::uuid,
        now() - interval '2 hours',
        now() - interval '1 hour 58 minutes'
      ),
      (
        '<promo-autumn@unapproved-vendor.com>',
        'sales@unapproved-vendor.com',
        'unapproved-vendor.com',
        'Special Wholesale Promotion Catalog',
        'rejected',
        'Domain "unapproved-vendor.com" is not on the workspace allowlist.',
        1,
        null::uuid,
        null,
        null::uuid,
        now() - interval '3 hours',
        now() - interval '3 hours'
      ),
      (
        '<err-98124@brightwell-electronics.co.uk>',
        'quotes@brightwell-electronics.co.uk',
        'brightwell-electronics.co.uk',
        'Office Equipment Quote Ref #98124',
        'failed',
        'Extraction failed: File is corrupted or password protected.',
        1,
        null::uuid,
        null,
        null::uuid,
        now() - interval '4 hours',
        now() - interval '3 hours 58 minutes'
      ),
      (
        '<logistics-2026@highland-transport.test>',
        'rates@highland-transport.test',
        'highland-transport.test',
        'Delivery Surcharges & Freight Schedule',
        'received',
        null,
        0,
        null::uuid,
        null,
        null::uuid,
        now() - interval '5 hours',
        null::timestamptz
      )
    ) as v(message_id, from_address, from_domain, subject, status, error_message, attachment_count, supplier_id, match_method, quotation_id, received_at, processed_at)
    on conflict do nothing;
  `;

  execFileSync(
    'docker',
    ['exec', 'supabase_db_ProcurePilot', 'psql', '-U', 'postgres', '-t', '-A', '-c', sql],
    { encoding: 'utf-8' },
  );
}

async function discoverExistingMatchTask(
  ownerToken: string,
): Promise<{ id: string; quotationId: string | null } | null> {
  const list = await apiAsUser<{
    items: { id: string; quotation_id: string | null; quotation_line?: { id: string } }[];
  }>(ownerToken, 'GET', '/match-tasks?status=all&limit=1');
  const task = list.items[0];
  return task ? { id: task.quotation_line?.id ?? task.id, quotationId: task.quotation_id } : null;
}

async function discoverExistingQuotationId(page: Page): Promise<string | undefined> {
  await page.goto('/quotations?status=all');
  await expect(page.locator('.page-title')).toContainText('Quotation Review Queue');
  await waitForNoVisibleLoading(page);
  await expect(page.locator('.clickable-row, .empty-state')).toBeVisible();

  const reviewLink = page.locator('.tasks-table a.action-btn').first();
  if ((await reviewLink.count()) === 0) {
    return undefined;
  }
  const reviewHref = await reviewLink.getAttribute('href');
  const match = reviewHref?.match(/\/quotations\/([^/]+)\/review/);
  if (!match?.[1]) {
    throw new Error('No existing quotation was available for documentation screenshots.');
  }
  return match[1];
}

async function captureDocumentedMatchQueue(page: Page): Promise<void> {
  await page.route('**/api/v1/match-tasks**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: documentationMatchTasks(),
        next_cursor: null,
      }),
    });
  });

  try {
    await captureRoute(page, '/matching?status=open', '09-match-resolution-queue.jpg', async () => {
      await expect(page.locator('.page-title')).toContainText('Match Resolution Queue');
      const quotationGroup = page.locator('.quotation-group', { hasText: 'Docs Capture Supplier' });
      await expect(quotationGroup).toBeVisible();
      await expect(quotationGroup.locator('.group-toggle')).toHaveAttribute('aria-expanded', 'true');
      await expect(quotationGroup.locator('.match-line')).toHaveCount(2);
    });
  } finally {
    await page.unroute('**/api/v1/match-tasks**');
  }
}

function documentationMatchTasks(): MatchTask[] {
  const quotation: MatchTask['quotation'] = {
    id: 'docs-quote-20260912',
    status: 'reviewed',
    source_filename: 'sample-quotation-al-faisal-trading.pdf',
    reviewed_by_email: 'buyer@example.com',
    reviewed_at: '2026-09-09T10:30:00Z',
    issue_date: '2026-08-28',
    line_count: 6,
    open_match_task_count: 2,
    supplier_name: 'Docs Capture Supplier',
  };
  const createdAt = '2026-09-09T11:00:00Z';
  const reasons: MatchTask['candidates'][number]['reasons'] = {
    alias_hit: false,
    gtin_match: false,
    supplier_code_match: false,
    lexical_similarity: '0.7200',
    semantic_similarity: '0.6500',
    feature_score: {
      brand_match: '0.0000',
      variant_match: '0.0000',
      pack_unit_match: '0.5000',
      pack_size_plausibility: '0.5000',
      price_plausibility: '0.7000',
    },
  };

  return [
    {
      id: 'docs-task-1',
      quotation_id: quotation.id,
      quotation,
      quotation_line: {
        id: 'docs-line-1',
        line_number: 1,
        original_text: 'A4 Copy Paper 80gsm (5-ream box)',
        quantity: '500',
        unit_price: { amount: '3.2500', currency: 'GBP' },
        quoted_line_total: { amount: '1950.0000', currency: 'GBP' },
      },
      status: 'open',
      priority: 'normal',
      reason: 'low_confidence',
      candidates: [
        {
          id: 'docs-candidate-1',
          quotation_line_id: 'docs-line-1',
          candidate_product: {
            id: 'docs-product-1',
            tenant_name: 'A4 Copy Paper 80gsm',
            canonical_name: 'A4 Copy Paper',
            brand: 'DocsCo',
            variant: '80gsm',
            base_unit: 'each',
            status: 'active',
          },
          confidence: '0.7800',
          reasons,
          rank: 1,
          scoring_version: 'matching-score-v1',
          created_at: createdAt,
        },
      ],
      created_at: createdAt,
      supplier_name: quotation.supplier_name,
    },
    {
      id: 'docs-task-2',
      quotation_id: quotation.id,
      quotation,
      quotation_line: {
        id: 'docs-line-2',
        line_number: 2,
        original_text: 'Desk Stapler Heavy Duty',
        quantity: '30',
        unit_price: { amount: '12.9900', currency: 'GBP' },
        quoted_line_total: { amount: '389.7000', currency: 'GBP' },
      },
      status: 'open',
      priority: 'normal',
      reason: 'no_candidate',
      candidates: [],
      created_at: createdAt,
      supplier_name: quotation.supplier_name,
    },
  ];
}

async function captureExistingMatchScreenshots(page: Page, matchTaskId: string): Promise<void> {
  await page.goto('/matching?status=all');
  await expect(page.locator('.page-title')).toContainText('Match Resolution Queue');
  await expect(page.locator('.quotation-group, .empty-state')).toBeVisible();
  await captureCurrentPage(page, '09-match-resolution-queue.jpg');

  await page.goto(`/matching/${matchTaskId}`);
  await expect(page.locator('.page-title')).toBeVisible();
  await expect(page.locator('.line-detail-card, .task-summary-card, .decision-card')).toBeVisible();
  await captureCurrentPage(page, '09b-match-resolution-detail.jpg');
  await page.locator('.outcomes-section, .decision-card').first().scrollIntoViewIfNeeded();
  await captureCurrentPage(page, '09c-match-resolution-outcomes.jpg');
}

async function captureAndResolveMatchScreenshots(
  page: Page,
  quotationId: string,
  productName: string,
): Promise<{ id: string; tenant_name: string; base_unit: string }> {
  await confirmQuotation(page);
  await page.goto(`/matching?quotation_id=${quotationId}`);
  await expect(page.locator('.quotation-group', { hasText: quotationId.slice(0, 8) })).toBeVisible({ timeout: 30_000 });
  await captureCurrentPage(page, '09-match-resolution-queue.jpg');
  await page.locator('.quotation-group', { hasText: quotationId.slice(0, 8) }).locator('.action-btn').first().click();
  await page.waitForURL('**/matching/**');
  await expect(page.locator('.page-title')).toContainText('Match Resolution');
  await captureCurrentPage(page, '09b-match-resolution-detail.jpg');
  await page.locator('mat-radio-button', { hasText: 'No Match — Create New Product' }).click();
  await expect(page.locator('.new-product-section')).toBeVisible();
  await captureCurrentPage(page, '09c-match-resolution-outcomes.jpg');
  await page.fill('input[formControlName="tenant_name"]', productName);
  await page.locator('mat-select[formControlName="base_unit"]').click();
  await page.locator('mat-option', { hasText: '(kilogram)' }).click();
  await page.locator('.confirm-resolution-btn.mat-mdc-unelevated-button').click();
  await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 15_000 });
  return findProductByName(await signInOwner(), productName);
}

async function signInAsOwner(page: Page, creds: Credentials): Promise<void> {
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', creds.ownerEmail);
  await page.fill('input[formControlName="password"]', creds.ownerPassword);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
  await waitForNoVisibleLoading(page);
}

async function captureRoute(
  page: Page,
  route: string,
  fileName: string,
  ready: () => Promise<void>,
): Promise<void> {
  await page.goto(route);
  await page.waitForLoadState('domcontentloaded');
  await ready();
  await captureCurrentPage(page, fileName);
}

async function captureCurrentPage(
  page: Page,
  fileName: string,
  options: { allowVisibleLoading?: boolean; target?: ScreenshotTarget } = {},
): Promise<void> {
  if (!options.allowVisibleLoading) {
    await waitForNoVisibleLoading(page);
  }
  await page.waitForTimeout(350);
  const path = join(SCREENSHOT_DIR, fileName);
  const target = options.target ?? 'auto';

  if (target === 'dialog') {
    await page.locator('mat-dialog-container').screenshot({
      path,
      type: 'jpeg',
      quality: 88,
    });
    return;
  }

  if (target === 'sidebar') {
    await page.locator('.shell-sidenav').screenshot({
      path,
      type: 'jpeg',
      quality: 88,
    });
    return;
  }

  const mainContent = page.locator('.main-content');
  if (await mainContent.count()) {
    await mainContent.screenshot({
      path,
      type: 'jpeg',
      quality: 88,
    });
    return;
  }

  await page.screenshot({
    path,
    fullPage: true,
    type: 'jpeg',
    quality: 88,
  });
}

async function waitForNoVisibleLoading(page: Page): Promise<void> {
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
          return (
            style.display === 'none' ||
            style.visibility === 'hidden' ||
            rect.width === 0 ||
            rect.height === 0
          );
        }),
      );
    },
    undefined,
    { timeout: 20_000 },
  );
}
