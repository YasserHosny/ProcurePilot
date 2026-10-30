import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, Subject } from 'rxjs';

import ar from '../../../../../../../packages/i18n/ar.json';
import en from '../../../../../../../packages/i18n/en.json';
import type { Product, PurchaseRequest, Role, Supplier } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { RfqApi, type RfqDetail } from '../../rfq/rfq-api';
import type { BasketSplitJob } from '../offers-api';
import { BasketSplitResultsComponent } from './basket-split-results.component';
import { PrepareSplitRequestsDialogComponent } from './prepare-split-requests-dialog.component';
import { isUserFacingConstraint } from './constraint-text';

const money = (amount: string) => ({ amount, currency: 'EGP' });

const rice = {
  id: 'p-rice',
  tenant_name: 'Rice',
  base_unit: 'kilogram',
  pack: { pack_count: 1, unit_size: '25', base_quantity: '25' },
} as unknown as Product;
const loose = {
  id: 'p-loose',
  tenant_name: 'Loose',
  base_unit: 'kilogram',
  pack: { pack_count: 1, unit_size: '1', base_quantity: '1' },
} as unknown as Product;
const supplier = { id: 's1', name: 'Al Nour' } as unknown as Supplier;

const job = {
  id: 'j1',
  supplier_ids: ['s1'],
  items: [],
  status: 'completed',
  result_url: '/x',
  created_at: '2026-10-18T00:00:00Z',
  result: {
    feasible: true,
    allocation: [
      {
        supplier_id: 's1',
        total_landed_cost: money('100.0000'),
        lines: [
          {
            workspace_product_id: 'p-rice',
            quantity: '500',
            offer_id: 'o1',
            landed_cost: money('60.0000'),
          },
          {
            workspace_product_id: 'p-loose',
            quantity: '12',
            offer_id: 'o2',
            landed_cost: money('40.0000'),
          },
        ],
      },
    ],
    total_landed_cost: money('100.0000'),
    infeasible_items: [],
    computed_at: '2026-10-18T00:00:00Z',
  },
} as unknown as BasketSplitJob;

describe('BasketSplitResultsComponent — packs and constraint copy', () => {
  let fixture: ComponentFixture<BasketSplitResultsComponent>;
  let translate: TranslateService;

  function render(
    applied: unknown[],
    violated: unknown[] = [],
    currentJob: BasketSplitJob = job,
    products: Product[] = [rice, loose],
  ): HTMLElement {
    fixture.componentRef.setInput('currentJob', currentJob);
    fixture.componentRef.setInput('suppliers', [supplier]);
    fixture.componentRef.setInput('products', products);
    fixture.componentRef.setInput('solverConfidence', 'high');
    fixture.componentRef.setInput('validUntil', null);
    fixture.componentRef.setInput('appliedConstraints', applied);
    fixture.componentRef.setInput('violatedConstraints', violated);
    fixture.componentRef.setInput('riskNotes', []);
    fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  let mockSession: {
    hasRole: jasmine.Spy;
    role: ReturnType<typeof signal<Role | null>>;
    currentMember: ReturnType<typeof signal<null>>;
    isAuthenticated: ReturnType<typeof signal<boolean>>;
    tenant: ReturnType<typeof signal<{ id: string; name: string } | null>>;
    activeLocale: ReturnType<typeof signal<string>>;
  };
  let mockRfqApi: jasmine.SpyObj<RfqApi>;
  let mockDialogRef: { close: jasmine.Spy };

  beforeEach(() => {
    mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal({ id: 'tenant-1', name: 'Tenant' }),
      activeLocale: signal('en'),
    };
    mockRfqApi = jasmine.createSpyObj('RfqApi', ['getRfq', 'splitRfq']);
    mockRfqApi.getRfq.and.returnValue(
      of({ rfq: { needed_by_date: '2026-11-20' }, lines: [], recipients: [] } as unknown as RfqDetail),
    );
    mockRfqApi.splitRfq.and.returnValue(of({ id: 'new-job-123' } as unknown as BasketSplitJob));
    mockDialogRef = { close: jasmine.createSpy('close') };

    TestBed.configureTestingModule({
      imports: [BasketSplitResultsComponent],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: SessionService, useValue: mockSession },
        { provide: RfqApi, useValue: mockRfqApi },
        {
          provide: MAT_DIALOG_DATA,
          useValue: {
            basketId: 'j1',
            rfqId: 'rfq-abcdef12-3456',
            rfqNeededByDate: '2026-11-20',
            suppliers: [supplier],
          },
        },
        { provide: MatDialogRef, useValue: mockDialogRef },
      ],
    });
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', en);
    translate.setTranslation('ar', ar);
    translate.use('en');
    fixture = TestBed.createComponent(BasketSplitResultsComponent);
  });

  it('shows allocated quantity in packs with the base total secondary (ADR-020)', () => {
    const el = render([]);
    const cells = el.querySelectorAll('.alloc-table tbody tr td:nth-child(2)');
    expect(cells[0].querySelector('.qty-primary')?.textContent?.trim()).toBe('20 × 25 kg');
    expect(cells[0].querySelector('.qty-secondary')?.textContent).toContain('500 kg');
    // loose goods (pack of 1) keep the plain base quantity
    expect(cells[1].querySelector('.qty-primary')?.textContent?.trim()).toBe('12 kg');
    expect(cells[1].querySelector('.qty-secondary')).toBeNull();
  });

  it('hides the solver tie-break and never renders solver free text', () => {
    const el = render([
      {
        kind: 'urgency',
        description: 'deterministic tie-break by supplier_id, then offer_id',
        source_ids: [],
      },
      { kind: 'supplier_exclusion', supplier_id: 's1', description: 'supplier excluded by requester' },
      { kind: 'delivery_fee', supplier_id: 's1', description: 'delivery fee applied below free-delivery threshold' },
    ]);
    const text = el.querySelector('.applied-constraints')?.textContent ?? '';
    expect(text).not.toContain('tie-break');
    expect(text).not.toContain('supplier excluded by requester');
    expect(text).toContain('Al Nour excluded as requested');
    expect(text).toContain('Delivery fee applied for Al Nour');
  });

  it('localises constraint sentences in Arabic', () => {
    translate.use('ar');
    const el = render([{ kind: 'supplier_exclusion', supplier_id: 's1', description: 'x' }]);
    const text = el.querySelector('.applied-constraints')?.textContent ?? '';
    expect(text).toContain('Al Nour');
    expect(text).toContain('تم استبعاد');
  });

  it('treats a pack smaller than one base unit as a pack, not loose goods', () => {
    const halfKg = {
      ...rice,
      pack: { pack_count: 1, unit_size: '0.5', base_quantity: '0.5' },
    } as unknown as Product;
    const el = render([], [], job, [halfKg, loose]);
    const primary = el.querySelector('.alloc-table tbody tr td:nth-child(2) .qty-primary');
    expect(primary?.textContent?.trim()).toBe('1,000 × 0.5 kg');
  });

  it("renders historical results with the pack captured at submission, not today's catalogue", () => {
    const snapshotJob = {
      ...job,
      pack_snapshot: { 'p-rice': { base_quantity: '10', base_unit: 'kilogram' } },
    } as unknown as BasketSplitJob;
    const el = render([], [], snapshotJob);
    const primary = el.querySelector('.alloc-table tbody tr td:nth-child(2) .qty-primary');
    expect(primary?.textContent?.trim()).toBe('50 × 10 kg');
  });

  it('words a violated constraint as a failure, not as the applied rule', () => {
    const el = render(
      [{ kind: 'minimum_order_value', supplier_id: 's1', description: 'x' }],
      [{ kind: 'minimum_order_value', supplier_id: 's1', description: 'x', reason: 'x' }],
    );
    expect(el.querySelector('.applied-constraints')?.textContent).toContain(
      'Minimum order value checked for Al Nour',
    );
    const violated = el.querySelector('.violated-constraints')?.textContent ?? '';
    expect(violated).toContain('Al Nour does not meet its minimum order value');
    expect(violated).not.toContain('checked');
  });

  it('has Arabic violation copy', () => {
    translate.use('ar');
    const el = render([], [{ kind: 'no_eligible_supplier', description: 'x', reason: 'x' }]);
    expect(el.querySelector('.violated-constraints')?.textContent).toContain('لا يوجد مورّد مؤهل');
  });

  it('flags only the tie-break as internal', () => {
    expect(isUserFacingConstraint({ kind: 'urgency', description: 'deterministic tie-break by x' })).toBeFalse();
    expect(isUserFacingConstraint({ kind: 'urgency', description: 'Requested basket urgency.' })).toBeTrue();
    expect(isUserFacingConstraint({ kind: 'delivery_fee', description: 'tie-break' })).toBeTrue();
  });

  describe('RFQ mode (T016)', () => {
    const rfqJob: BasketSplitJob = {
      ...job,
      rfq_id: 'rfq-abcdef12-3456',
      result: {
        ...job.result!,
        total_landed_cost: { amount: '4063.00', currency: 'SAR' },
        single_supplier_baselines: [
          {
            supplier_id: 's1',
            feasible: true,
            total_landed_cost: { amount: '4137.00', currency: 'SAR' },
          },
          {
            supplier_id: 's2',
            feasible: true,
            total_landed_cost: { amount: '4500.00', currency: 'SAR' },
          },
        ],
      },
    };

    const s2 = { id: 's2', name: 'Al Wafra' } as unknown as Supplier;

    it('shows split total, each single-supplier total, and saving with currency in RFQ mode', () => {
      fixture.componentRef.setInput('currentJob', rfqJob);
      fixture.componentRef.setInput('suppliers', [supplier, s2]);
      fixture.componentRef.setInput('products', [rice, loose]);
      fixture.componentRef.setInput('solverConfidence', 'high');
      fixture.componentRef.setInput('validUntil', null);
      fixture.componentRef.setInput('appliedConstraints', []);
      fixture.componentRef.setInput('violatedConstraints', []);
      fixture.componentRef.setInput('riskNotes', []);
      fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });
      fixture.detectChanges();

      const el = fixture.nativeElement as HTMLElement;
      const rfqSummary = el.querySelector('[data-testid="rfq-savings-summary"]');
      expect(rfqSummary).not.toBeNull();
      const text = rfqSummary?.textContent ?? '';

      // Split total: SAR 4,063
      expect(text).toContain('SAR 4,063');
      // Single supplier totals: Al Nour (4,137) and Al Wafra (4,500)
      expect(text).toContain('Al Nour');
      expect(text).toContain('SAR 4,137');
      expect(text).toContain('Al Wafra');
      expect(text).toContain('SAR 4,500');
      // Saving: 4,137 - 4,063 = 74
      expect(text).toContain('SAR 74');
    });

    it('does NOT render RFQ summary when job has no rfq_id', () => {
      const el = render([]);
      expect(el.querySelector('[data-testid="rfq-savings-summary"]')).toBeNull();
    });
  });

  describe('Prepare N requests from RFQ split (T022)', () => {
    const s2 = { id: 's2', name: 'Al Wafra' } as unknown as Supplier;
    const rfqCompletedJob: BasketSplitJob = {
      ...job,
      rfq_id: 'rfq-abcdef12-3456',
      status: 'completed',
      result: {
        ...job.result!,
        allocation: [
          {
            supplier_id: 's1',
            total_landed_cost: money('2773.00'),
            lines: [
              {
                workspace_product_id: 'p-rice',
                quantity: '500',
                offer_id: 'o1',
                landed_cost: money('2773.00'),
              },
            ],
          },
          {
            supplier_id: 's2',
            total_landed_cost: money('1290.00'),
            lines: [
              {
                workspace_product_id: 'p-loose',
                quantity: '12',
                offer_id: 'o2',
                landed_cost: money('1290.00'),
              },
            ],
          },
        ],
        total_landed_cost: { amount: '4063.00', currency: 'SAR' },
        single_supplier_baselines: [
          {
            supplier_id: 's1',
            feasible: true,
            total_landed_cost: { amount: '4137.00', currency: 'SAR' },
          },
          {
            supplier_id: 's2',
            feasible: true,
            total_landed_cost: { amount: '4500.00', currency: 'SAR' },
          },
        ],
      },
    };

    it('the button shows only for a completed RFQ job', () => {
      mockSession.hasRole.and.returnValue(true);
      fixture.componentRef.setInput('currentJob', rfqCompletedJob);
      fixture.componentRef.setInput('suppliers', [supplier, s2]);
      fixture.componentRef.setInput('products', [rice, loose]);
      fixture.componentRef.setInput('solverConfidence', 'high');
      fixture.componentRef.setInput('validUntil', null);
      fixture.componentRef.setInput('appliedConstraints', []);
      fixture.componentRef.setInput('violatedConstraints', []);
      fixture.componentRef.setInput('riskNotes', []);
      fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });
      fixture.detectChanges();

      const btn = (fixture.nativeElement as HTMLElement).querySelector(
        '[data-testid="prepare-requests-button"]',
      );
      expect(btn).not.toBeNull();
      expect(btn?.textContent).toContain('Prepare 2 requests');

      // Not shown if user is viewer (not owner/buyer)
      mockSession.hasRole.and.returnValue(false);
      fixture.detectChanges();
      expect(
        (fixture.nativeElement as HTMLElement).querySelector(
          '[data-testid="prepare-requests-button"]',
        ),
      ).toBeNull();

      // Not shown if job status is running
      mockSession.hasRole.and.returnValue(true);
      const runningJob = { ...rfqCompletedJob, status: 'running' as const };
      fixture.componentRef.setInput('currentJob', runningJob);
      fixture.detectChanges();
      expect(
        (fixture.nativeElement as HTMLElement).querySelector(
          '[data-testid="prepare-requests-button"]',
        ),
      ).toBeNull();
    });

    it('a standalone (non-RFQ) job shows no button', () => {
      mockSession.hasRole.and.returnValue(true);
      const standaloneJob = { ...job, rfq_id: null };
      const el = render([], [], standaloneJob);
      expect(el.querySelector('[data-testid="prepare-requests-button"]')).toBeNull();
    });

    it("the dialog defaults required-by to the RFQ's date", () => {
      const dialogFixture = TestBed.createComponent(PrepareSplitRequestsDialogComponent);
      const dialogComp = dialogFixture.componentInstance;
      expect(dialogComp.form.get('required_by_date')?.value).toBe('2026-11-20');
    });

    it('POST sends the body and reuses the key on retry', () => {
      const httpTesting = TestBed.inject(HttpTestingController);
      const dialogFixture = TestBed.createComponent(PrepareSplitRequestsDialogComponent);
      const dialogComp = dialogFixture.componentInstance;
      dialogFixture.detectChanges();

      const branchReq = httpTesting.expectOne('/api/v1/organisation/branches?is_active=true&limit=100');
      branchReq.flush({ items: [{ id: 'branch-1', name: 'Branch 1', is_active: true }], next_cursor: null });
      const ccReq = httpTesting.expectOne('/api/v1/organisation/cost-centres?is_archived=false&limit=100');
      ccReq.flush({ items: [{ id: 'cc-1', code: 'CC1', name: 'Cost Centre 1' }], next_cursor: null });

      dialogComp.form.patchValue({
        branch_id: 'branch-1',
        required_by_date: '2026-11-20',
        cost_centre_id: 'cc-1',
      });

      // First submit attempt
      dialogComp.onSubmit();

      const req1 = httpTesting.expectOne('/api/v1/baskets/j1/prepare-requests');
      expect(req1.request.method).toBe('POST');
      expect(req1.request.body).toEqual({
        branch_id: 'branch-1',
        required_by_date: '2026-11-20',
        cost_centre_id: 'cc-1',
        confirm_expired_quotation_ids: [],
      });
      const key1 = req1.request.headers.get('Idempotency-Key');
      expect(key1).toBeTruthy();

      // 409 expired_quotation_unconfirmed response
      req1.flush(
        {
          code: 409,
          message: 'Quotation expired',
          details: {
            reason: 'expired_quotation_unconfirmed',
            quotation_ids: ['quote-exp-1'],
          },
        },
        { status: 409, statusText: 'Conflict' },
      );
      dialogFixture.detectChanges();

      // Expired quotes displayed for confirmation
      expect(dialogComp.expiredQuotations().length).toBe(1);
      dialogComp.expiredQuotations.update((list) =>
        list.map((item) => ({ ...item, confirmed: true })),
      );

      // Retry submission
      dialogComp.onSubmit();

      const req2 = httpTesting.expectOne('/api/v1/baskets/j1/prepare-requests');
      expect(req2.request.method).toBe('POST');
      expect(req2.request.body).toEqual({
        branch_id: 'branch-1',
        required_by_date: '2026-11-20',
        cost_centre_id: 'cc-1',
        confirm_expired_quotation_ids: ['quote-exp-1'],
      });
      // MUST reuse the exact same Idempotency-Key
      expect(req2.request.headers.get('Idempotency-Key')).toBe(key1);

      req2.flush({
        request_group_id: 'grp-1',
        purchase_request_ids: ['pr-1', 'pr-2'],
      });

      // Fetches both requests
      const prReq1 = httpTesting.expectOne('/api/v1/requests/pr-1');
      prReq1.flush({ id: 'pr-1', status: 'draft', branch_id: 'branch-1' });
      const prReq2 = httpTesting.expectOne('/api/v1/requests/pr-2');
      prReq2.flush({ id: 'pr-2', status: 'draft', branch_id: 'branch-1' });

      httpTesting.verify();
    });

    it('success lists the requests', () => {
      fixture.componentRef.setInput('currentJob', rfqCompletedJob);
      fixture.componentRef.setInput('suppliers', [supplier, s2]);
      fixture.componentRef.setInput('products', [rice, loose]);
      fixture.componentRef.setInput('solverConfidence', 'high');
      fixture.componentRef.setInput('validUntil', null);
      fixture.componentRef.setInput('appliedConstraints', []);
      fixture.componentRef.setInput('violatedConstraints', []);
      fixture.componentRef.setInput('riskNotes', []);
      fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });

      const mockRequests: PurchaseRequest[] = [
        {
          id: 'pr-1',
          branch_id: 'branch-1',
          required_by_date: '2026-11-20',
          status: 'draft',
          lines: [],
          requested_by_membership_id: 'm1',
          created_at: '2026-10-30T00:00:00Z',
          has_incomplete_estimate: false,
          estimated_total: { amount: '2773.00', currency: 'SAR' },
          source: {
            rfq_id: 'rfq-abcdef12-3456',
            rfq_response_id: 'resp-1',
            quotation_id: 'q-1',
            supplier_id: 's1',
            supplier_name: 'Al Nour',
          },
          budget_status: { exceeds: false, status: 'within' },
        },
        {
          id: 'pr-2',
          branch_id: 'branch-1',
          required_by_date: '2026-11-20',
          status: 'draft',
          lines: [],
          requested_by_membership_id: 'm1',
          created_at: '2026-10-30T00:00:00Z',
          has_incomplete_estimate: false,
          estimated_total: { amount: '1290.00', currency: 'SAR' },
          source: {
            rfq_id: 'rfq-abcdef12-3456',
            rfq_response_id: 'resp-2',
            quotation_id: 'q-2',
            supplier_id: 's2',
            supplier_name: 'Al Wafra',
          },
          budget_status: { exceeds: true, status: 'over' },
        },
      ];

      fixture.componentInstance.preparedRequests.set(mockRequests);
      fixture.detectChanges();

      const el = fixture.nativeElement as HTMLElement;
      const summary = el.querySelector('[data-testid="prepared-requests-summary"]');
      expect(summary).not.toBeNull();

      const items = el.querySelectorAll('[data-testid="prepared-request-item"]');
      expect(items.length).toBe(2);

      // Item 1
      expect(items[0].textContent).toContain('Al Nour');
      expect(items[0].textContent).toContain('SAR 2,773');
      expect(items[0].textContent).toContain('Within budget');
      const link1 = items[0].querySelector('a[data-testid="view-request-link"]');
      expect(link1?.getAttribute('href')).toBe('/requests/pr-1');

      // Item 2
      expect(items[1].textContent).toContain('Al Wafra');
      expect(items[1].textContent).toContain('SAR 1,290');
      expect(items[1].textContent).toContain('Exceeds budget');
      const link2 = items[1].querySelector('a[data-testid="view-request-link"]');
      expect(link2?.getAttribute('href')).toBe('/requests/pr-2');
    });

    it('split_stale shows Rerun split', () => {
      const router = TestBed.inject(Router);
      spyOn(router, 'navigate');

      fixture.componentRef.setInput('currentJob', rfqCompletedJob);
      fixture.componentRef.setInput('suppliers', [supplier, s2]);
      fixture.componentRef.setInput('products', [rice, loose]);
      fixture.componentRef.setInput('solverConfidence', 'high');
      fixture.componentRef.setInput('validUntil', null);
      fixture.componentRef.setInput('appliedConstraints', []);
      fixture.componentRef.setInput('violatedConstraints', []);
      fixture.componentRef.setInput('riskNotes', []);
      fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });

      fixture.componentInstance.staleError.set(true);
      fixture.detectChanges();

      const el = fixture.nativeElement as HTMLElement;
      const banner = el.querySelector('[data-testid="split-stale-banner"]');
      expect(banner).not.toBeNull();
      expect(banner?.textContent).toContain('split is stale');

      const rerunBtn = el.querySelector(
        '[data-testid="rerun-split-button"]',
      ) as HTMLButtonElement | null;
      expect(rerunBtn).not.toBeNull();

      rerunBtn?.click();
      expect(mockRfqApi.splitRfq).toHaveBeenCalledWith('rfq-abcdef12-3456', jasmine.any(String));
      expect(router.navigate).toHaveBeenCalledWith(['/offers/basket-split', 'new-job-123']);
    });

    it('rerun split: rapid double click sends one call, retry after error reuses the key', () => {
      const router = TestBed.inject(Router);
      spyOn(router, 'navigate');

      const inFlight = new Subject<BasketSplitJob>();
      mockRfqApi.splitRfq.and.returnValue(inFlight.asObservable());

      fixture.componentRef.setInput('currentJob', rfqCompletedJob);
      fixture.componentRef.setInput('suppliers', [supplier, s2]);
      fixture.componentRef.setInput('products', [rice, loose]);
      fixture.componentRef.setInput('solverConfidence', 'high');
      fixture.componentRef.setInput('validUntil', null);
      fixture.componentRef.setInput('appliedConstraints', []);
      fixture.componentRef.setInput('violatedConstraints', []);
      fixture.componentRef.setInput('riskNotes', []);
      fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });

      fixture.componentInstance.staleError.set(true);
      fixture.detectChanges();

      const el = fixture.nativeElement as HTMLElement;
      const rerunBtn = el.querySelector('[data-testid="rerun-split-button"]') as HTMLButtonElement;
      expect(rerunBtn).not.toBeNull();

      // Two rapid clicks while the request is in flight -> exactly one API call
      rerunBtn.click();
      rerunBtn.click();
      fixture.detectChanges();
      expect(mockRfqApi.splitRfq).toHaveBeenCalledTimes(1);
      const [rfqId, firstKey] = mockRfqApi.splitRfq.calls.mostRecent().args;
      expect(rfqId).toBe('rfq-abcdef12-3456');
      expect(firstKey).toBeTruthy();
      expect(rerunBtn.disabled).toBeTrue();

      // Error -> button re-enabled and the key is kept for the retry
      inFlight.error(new Error('boom'));
      fixture.detectChanges();
      expect(rerunBtn.disabled).toBeFalse();

      rerunBtn.click();
      expect(mockRfqApi.splitRfq).toHaveBeenCalledTimes(2);
      expect(mockRfqApi.splitRfq.calls.mostRecent().args[1]).toBe(firstKey);

      // Success -> navigation to the new job
      mockRfqApi.splitRfq.and.returnValue(of({ id: 'new-job-123' } as unknown as BasketSplitJob));
      rerunBtn.click();
      expect(router.navigate).toHaveBeenCalledWith(['/offers/basket-split', 'new-job-123']);
    });

    it('renders plural-aware button label in Arabic', () => {
      translate.use('ar');
      mockSession.hasRole.and.returnValue(true);
      fixture.componentRef.setInput('currentJob', rfqCompletedJob);
      fixture.componentRef.setInput('suppliers', [supplier, s2]);
      fixture.componentRef.setInput('products', [rice, loose]);
      fixture.componentRef.setInput('solverConfidence', 'high');
      fixture.componentRef.setInput('validUntil', null);
      fixture.componentRef.setInput('appliedConstraints', []);
      fixture.componentRef.setInput('violatedConstraints', []);
      fixture.componentRef.setInput('riskNotes', []);
      fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });
      fixture.detectChanges();

      const btn = (fixture.nativeElement as HTMLElement).querySelector(
        '[data-testid="prepare-requests-button"]',
      );
      expect(btn?.textContent).toContain('إعداد طلبين');
    });

    it('remembers and saves branch in localStorage for tenant', () => {
      const storageKey = 'pp.rfq.lastBranchId.tenant-1';
      localStorage.setItem(storageKey, 'branch-saved');

      const httpTesting = TestBed.inject(HttpTestingController);
      const dialogFixture = TestBed.createComponent(PrepareSplitRequestsDialogComponent);
      const dialogComp = dialogFixture.componentInstance;
      dialogFixture.detectChanges();

      const branchReq = httpTesting.expectOne('/api/v1/organisation/branches?is_active=true&limit=100');
      branchReq.flush({
        items: [
          { id: 'branch-other', name: 'Other Branch', is_active: true },
          { id: 'branch-saved', name: 'Saved Branch', is_active: true },
        ],
        next_cursor: null,
      });
      const ccReq = httpTesting.expectOne('/api/v1/organisation/cost-centres?is_archived=false&limit=100');
      ccReq.flush({ items: [], next_cursor: null });

      expect(dialogComp.form.get('branch_id')?.value).toBe('branch-saved');

      dialogComp.onBranchChange('branch-other');
      expect(localStorage.getItem(storageKey)).toBe('branch-other');

      localStorage.removeItem(storageKey);
    });

    it('rfq_already_converted shows links to the existing requests', () => {
      fixture.componentRef.setInput('currentJob', rfqCompletedJob);
      fixture.componentRef.setInput('suppliers', [supplier, s2]);
      fixture.componentRef.setInput('products', [rice, loose]);
      fixture.componentRef.setInput('solverConfidence', 'high');
      fixture.componentRef.setInput('validUntil', null);
      fixture.componentRef.setInput('appliedConstraints', []);
      fixture.componentRef.setInput('violatedConstraints', []);
      fixture.componentRef.setInput('riskNotes', []);
      fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });

      fixture.componentInstance.convertedRequestIds.set(['pr-exist-1', 'pr-exist-2']);
      fixture.detectChanges();

      const el = fixture.nativeElement as HTMLElement;
      const banner = el.querySelector('[data-testid="already-converted-banner"]');
      expect(banner).not.toBeNull();
      expect(banner?.textContent).toContain('already been converted');

      const links = el.querySelectorAll('a[data-testid="converted-request-link"]');
      expect(links.length).toBe(2);
      expect(links[0].getAttribute('href')).toBe('/requests/pr-exist-1');
      expect(links[1].getAttribute('href')).toBe('/requests/pr-exist-2');
    });
  });
});
