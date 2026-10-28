import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { Subject, of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { ApiService } from '../../../core/api/api.service';
import type { PurchaseRequest, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';
import { ApprovalsApiService } from '../approvals-api';
import {
  ApprovalDecisionDialogComponent,
  ApprovalQueueComponent,
  type ApprovalDecisionDialogData,
} from './approval-queue.component';

const mockPendingRequests: PurchaseRequest[] = [
  {
    id: 'req-001',
    branch_id: 'branch-north',
    cost_centre_id: 'cc-ops',
    requested_by_membership_id: 'mem-requester-1',
    required_by_date: '2026-09-20',
    status: 'submitted',
    has_incomplete_estimate: false,
    estimated_total: { amount: '1250.00', currency: 'SAR' },
    budget_status: {
      remaining_amount: { amount: '5000.00', currency: 'SAR' },
      exceeds: false,
    },
    lines: [
      {
        id: 'line-1',
        workspace_product_id: 'prod-gloves',
        quantity: '50',
        estimated_unit_price: { amount: '15.00', currency: 'SAR' },
        note: 'Latex-free boxes',
      },
      {
        id: 'line-2',
        workspace_product_id: 'prod-masks',
        quantity: '100',
        estimated_unit_price: { amount: '5.00', currency: 'SAR' },
        note: null,
      },
    ],
    created_at: '2026-09-10T10:00:00Z',
    submitted_at: '2026-09-10T10:05:00Z',
  },
  {
    id: 'req-002',
    branch_id: 'branch-south',
    cost_centre_id: null,
    requested_by_membership_id: 'mem-requester-2',
    required_by_date: '2026-09-25',
    status: 'submitted',
    has_incomplete_estimate: true,
    estimated_total: null,
    budget_status: {
      remaining_amount: { amount: '100.00', currency: 'SAR' },
      exceeds: true,
    },
    lines: [],
    created_at: '2026-09-10T11:00:00Z',
    submitted_at: '2026-09-10T11:10:00Z',
  },
];

describe('ApprovalQueueComponent', () => {
  let component: ApprovalQueueComponent;
  let fixture: ComponentFixture<ApprovalQueueComponent>;
  let approvalsApi: jasmine.SpyObj<ApprovalsApiService>;
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;
  const role = signal<Role | null>('buyer');
  let sessionSpy: { hasRole: jasmine.Spy; role: typeof role };

  beforeEach(async () => {
    role.set('buyer');
    sessionSpy = {
      hasRole: jasmine.createSpy('hasRole').and.callFake((...roles: readonly Role[]) => {
        const current = role();
        return current ? roles.includes(current) : false;
      }),
      role,
    };
    approvalsApi = jasmine.createSpyObj('ApprovalsApiService', ['listPendingApprovals']);
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'approveRequest',
      'rejectRequest',
    ]);
    organisationApi = jasmine.createSpyObj('OrganisationApiService', [
      'listBranches',
      'listCostCentres',
    ]);
    api = jasmine.createSpyObj('ApiService', ['products']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);
    snackBarSpy.open.and.returnValue({
      onAction: () => of(undefined),
    } as unknown as ReturnType<MatSnackBar['open']>);

    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: mockPendingRequests, next_cursor: null }),
    );
    organisationApi.listBranches.and.returnValue(
      of({
        items: [
          { id: 'branch-north', name: 'North Branch', is_active: true, created_at: '2026-01-01T00:00:00Z' },
          { id: 'branch-south', name: 'South Branch', is_active: true, created_at: '2026-01-01T00:00:00Z' },
        ],
        next_cursor: null,
      }),
    );
    organisationApi.listCostCentres.and.returnValue(
      of({
        items: [
          {
            id: 'cc-ops',
            name: 'Operations CC',
            code: 'OPS-01',
            branch_id: 'branch-north',
            is_orphaned: false,
            is_archived: false,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );
    api.products.and.returnValue(
      of({
        items: [
          {
            id: 'prod-gloves',
            tenant_name: 'Latex Gloves',
            canonical_name: 'Gloves',
            base_unit: 'each',
            pack: { pack_count: 1, unit_size: '1.000000' },
            status: 'active',
            created_at: '2026-01-01T00:00:00Z',
          },
          {
            id: 'prod-masks',
            tenant_name: 'Surgical Masks',
            canonical_name: 'Masks',
            base_unit: 'each',
            pack: { pack_count: 1, unit_size: '1.000000' },
            status: 'active',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );

    await TestBed.configureTestingModule({
      imports: [ApprovalQueueComponent],
      providers: [
        provideTranslateService(),
        { provide: ApprovalsApiService, useValue: approvalsApi },
        { provide: RequestsApiService, useValue: requestsApi },
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: api },
        { provide: SessionService, useValue: sessionSpy },
        { provide: Router, useValue: routerSpy },
      ],
    })
      .overrideComponent(ApprovalQueueComponent, {
        set: {
          providers: [
            { provide: MatDialog, useValue: dialogSpy },
            { provide: MatSnackBar, useValue: snackBarSpy },
            { provide: SessionService, useValue: sessionSpy },
            { provide: Router, useValue: routerSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(ApprovalQueueComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load pending approvals with limit 50 on init', () => {
    expect(approvalsApi.listPendingApprovals).toHaveBeenCalledWith({ limit: 50 });
    expect(organisationApi.listBranches).toHaveBeenCalledWith({ limit: 100 });
    expect(organisationApi.listCostCentres).toHaveBeenCalledWith({ limit: 100 });
    expect(api.products).toHaveBeenCalledWith({ status: 'all', limit: 100 });
    expect(component.pendingRequests().length).toBe(2);
    expect(component.isLoading()).toBeFalse();
  });

  it('should display rows with requester short id fallback, branch, cost centre name/none, required-by date, and formatted total', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const rows = compiled.querySelectorAll('.request-row');
    expect(rows.length).toBe(2);

    expect(compiled.textContent).toContain('mem-requ');
    expect(compiled.textContent).toContain('North Branch');
    expect(compiled.textContent).toContain('Operations CC');
    expect(compiled.textContent).toContain('Sep 20, 2026');
    expect(compiled.textContent).toContain('SAR 1,250');

    expect(compiled.textContent).toContain('South Branch');
    expect(compiled.textContent).toContain('None (branch-level)');
  });

  it('displays the supplier name above/next to the estimated total when source.supplier_name is set', () => {
    approvalsApi.listPendingApprovals.and.returnValue(
      of({
        items: [
          {
            ...mockPendingRequests[0],
            source: {
              rfq_id: 'rfq-1',
              rfq_response_id: 'resp-1',
              quotation_id: 'q-1',
              supplier_id: 's-1',
              supplier_name: 'الوفرة للمواد الغذائية',
            },
          },
        ],
        next_cursor: null,
      }),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    const supplierEl = (fixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="approval-supplier"]',
    );
    expect(supplierEl).toBeTruthy();
    expect(supplierEl?.textContent?.trim()).toBe('الوفرة للمواد الغذائية');
    expect(supplierEl?.getAttribute('dir')).toBe('auto');
  });

  it('shows "Create purchase order" snackbar action on approve for owner/buyer and navigates to orders/new', () => {
    role.set('buyer');
    const actionSubject = new Subject<void>();
    snackBarSpy.open.and.returnValue({
      onAction: () => actionSubject.asObservable(),
    } as unknown as ReturnType<MatSnackBar['open']>);

    requestsApi.approveRequest.and.returnValue(
      of({ ...mockPendingRequests[0], status: 'approved' } as PurchaseRequest),
    );

    component.submitDecision('req-001', 'approve');

    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Request approved.',
      'Create purchase order',
      { duration: 6000 },
    );

    actionSubject.next();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/orders/new'], {
      queryParams: { source_request_id: 'req-001' },
    });
  });

  it('does not offer "Create purchase order" action to non-buyer non-owner roles on approve', () => {
    role.set('approver');
    requestsApi.approveRequest.and.returnValue(
      of({ ...mockPendingRequests[0], status: 'approved' } as PurchaseRequest),
    );

    component.submitDecision('req-001', 'approve');

    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Request approved.',
      undefined,
      { duration: 3500 },
    );
    expect(routerSpy.navigate).not.toHaveBeenCalled();
  });

  it('should prefer requester_name over requester_email and fall back to short id only when both are null', () => {
    const requestsWithRequesterInfo: PurchaseRequest[] = [
      {
        ...mockPendingRequests[0],
        id: 'req-name',
        requester_name: 'Nadia Mansour',
        requester_email: 'nadia@example.com',
      },
      {
        ...mockPendingRequests[0],
        id: 'req-email',
        requester_name: null,
        requester_email: 'buyer@example.com',
      },
      {
        ...mockPendingRequests[0],
        id: 'req-fallback',
        requester_name: null,
        requester_email: null,
        requested_by_membership_id: 'abcdef12-3456-7890-abcd-ef1234567890',
      },
    ];
    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: requestsWithRequesterInfo, next_cursor: null }),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    const cells = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('.requester-cell'),
    ).map((el) => el.textContent?.trim());
    expect(cells).toEqual(['Nadia Mansour', 'buyer@example.com', 'abcdef12']);
  });

  it('should render incomplete estimate badge and budget warning when applicable', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const badge = compiled.querySelector('.incomplete-badge');
    expect(badge).toBeTruthy();
    expect(badge?.textContent?.trim()).toBe('Estimate incomplete');

    const budgetWarning = compiled.querySelector('.budget-warning-badge');
    expect(budgetWarning).toBeTruthy();
    expect(budgetWarning?.textContent?.trim()).toContain('Exceeds budget');

    const warningRemaining = compiled.querySelector('.budget-remaining-subtext');
    expect(warningRemaining).toBeTruthy();
    expect(warningRemaining?.textContent?.trim()).toBe('Remaining: SAR 100');
  });

  it('should render within budget badge and formatted remaining budget when within budget', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const withinBadge = compiled.querySelector('.budget-within-badge');
    expect(withinBadge?.textContent?.trim()).toBe('Within budget');
    const budgetRemaining = compiled.querySelector('.budget-remaining');
    expect(budgetRemaining).toBeTruthy();
    expect(budgetRemaining?.textContent?.trim()).toBe('Remaining: SAR 5,000');
  });

  it('should render near, over, and no_budget statuses with i18n reason_code messages', () => {
    const requestsWithStatuses: PurchaseRequest[] = [
      {
        ...mockPendingRequests[0],
        id: 'req-near',
        budget_status: {
          status: 'near',
          remaining_amount: { amount: '1250.5', currency: 'EGP' },
          exceeds: false,
          reason_code: null,
        },
      },
      {
        ...mockPendingRequests[0],
        id: 'req-nobudget-branch',
        cost_centre_id: null,
        budget_status: {
          status: 'no_budget',
          remaining_amount: null,
          exceeds: false,
          reason_code: 'no_budget_for_branch',
        },
      },
      {
        ...mockPendingRequests[0],
        id: 'req-nobudget-cc',
        budget_status: {
          status: 'no_budget',
          remaining_amount: null,
          exceeds: false,
          reason_code: 'no_budget_at_cost_centre_level',
        },
      },
    ];
    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: requestsWithStatuses, next_cursor: null }),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-near-badge')?.textContent?.trim()).toBe(
      'Near budget limit',
    );
    expect(compiled.textContent).toContain('Remaining: EGP 1,250.50');
    expect(compiled.querySelector('.budget-no-budget-badge')?.textContent?.trim()).toBe(
      'No budget configured',
    );
    const reasons = Array.from(compiled.querySelectorAll('.budget-reason-subtext')).map((el) =>
      el.textContent?.trim(),
    );
    expect(reasons).toEqual([
      'No budget set for this branch',
      'No budget at cost-centre level',
    ]);
  });

  it('should display not available when budget_status is absent or null', () => {
    const requestWithoutBudget: PurchaseRequest = {
      ...mockPendingRequests[0],
      id: 'req-003',
      budget_status: null,
    };
    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: [requestWithoutBudget], next_cursor: null }),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-warning-badge')).toBeNull();
    expect(compiled.querySelector('.budget-remaining')).toBeNull();
    const budgetCell = compiled.querySelector('.budget-cell');
    expect(budgetCell?.textContent?.trim()).toBe('Not available');
  });

  it('should keep approve and reject buttons enabled when request exceeds budget', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const rows = compiled.querySelectorAll('.request-row');
    const exceedingRow = rows[1];
    const approveBtn = exceedingRow.querySelector<HTMLButtonElement>('.approve-btn');
    const rejectBtn = exceedingRow.querySelector<HTMLButtonElement>('.reject-btn');

    expect(approveBtn).toBeTruthy();
    expect(approveBtn?.disabled).toBeFalse();
    expect(rejectBtn).toBeTruthy();
    expect(rejectBtn?.disabled).toBeFalse();
  });

  it('should show empty state when there are no pending requests', () => {
    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: [], next_cursor: null }),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.empty-state')).toBeTruthy();
    expect(compiled.querySelector('.approvals-table')).toBeNull();
  });

  it('should toggle line expansion when expand button is clicked', () => {
    expect(component.isExpanded('req-001')).toBeFalse();
    component.toggleExpand('req-001');
    expect(component.isExpanded('req-001')).toBeTrue();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Latex Gloves');
    expect(compiled.textContent).toContain('Surgical Masks');
    expect(compiled.textContent).not.toContain('prod-gloves');
    expect(compiled.textContent).not.toContain('prod-masks');
    expect(compiled.textContent).toContain('Latex-free boxes');

    component.toggleExpand('req-001');
    expect(component.isExpanded('req-001')).toBeFalse();
  });

  it('should fall back to raw IDs when lookup data is missing', () => {
    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    api.products.and.returnValue(of({ items: [], next_cursor: null }));

    component.loadPendingApprovals();
    component.toggleExpand('req-001');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('branch-north');
    expect(compiled.textContent).toContain('cc-ops');
    expect(compiled.textContent).toContain('prod-gloves');
  });

  it('should open decision dialog for approve and call approveRequest on confirm', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ confirmed: true, comment: 'Budget approved' }),
    } as MatDialogRef<unknown, unknown>);

    requestsApi.approveRequest.and.returnValue(
      of({ ...mockPendingRequests[0], status: 'approved' } as PurchaseRequest),
    );

    component.openDecisionDialog(mockPendingRequests[0], 'approve');

    expect(dialogSpy.open).toHaveBeenCalledTimes(1);
    expect(requestsApi.approveRequest).toHaveBeenCalledWith('req-001', {
      comment: 'Budget approved',
    });
    expect(approvalsApi.listPendingApprovals).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Request approved.',
      'Create purchase order',
      { duration: 6000 },
    );
  });

  it('should open decision dialog for reject and call rejectRequest on confirm', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ confirmed: true, comment: 'Too expensive' }),
    } as MatDialogRef<unknown, unknown>);

    requestsApi.rejectRequest.and.returnValue(
      of({ ...mockPendingRequests[0], status: 'rejected' } as PurchaseRequest),
    );

    component.openDecisionDialog(mockPendingRequests[0], 'reject');

    expect(dialogSpy.open).toHaveBeenCalledTimes(1);
    expect(requestsApi.rejectRequest).toHaveBeenCalledWith('req-001', {
      comment: 'Too expensive',
    });
    expect(approvalsApi.listPendingApprovals).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith('Request rejected.', undefined, {
      duration: 3500,
    });
  });

  it('should not call approveRequest or rejectRequest when dialog is cancelled', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ confirmed: false }),
    } as MatDialogRef<unknown, unknown>);

    component.openDecisionDialog(mockPendingRequests[0], 'approve');

    expect(dialogSpy.open).toHaveBeenCalledTimes(1);
    expect(requestsApi.approveRequest).not.toHaveBeenCalled();
    expect(requestsApi.rejectRequest).not.toHaveBeenCalled();
  });

  it('should display error message and trace ID on API error', () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'server_error', message: 'Internal error', trace_id: 'tr_appr_123' },
    });
    approvalsApi.listPendingApprovals.and.returnValue(throwError(() => error500));

    component.loadPendingApprovals();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('Internal error');
    expect(component.errorTraceId()).toBe('tr_appr_123');
  });

  it('should correctly format money and line prices via FormatService', () => {
    expect(component.formatMoney(mockPendingRequests[0])).toBe('SAR 1,250');
    expect(component.formatMoney(mockPendingRequests[1])).toBe('Not available');
    expect(component.formatLinePrice(mockPendingRequests[0].lines[0])).toBe('SAR 15');
    expect(
      component.formatLinePrice({
        id: 'l3',
        workspace_product_id: 'p3',
        quantity: '1',
      }),
    ).toBe('Not available');
  });

  it('should format line item quantity without trailing zeros in en and with Arabic-Indic digits in ar', () => {
    const testRequest: PurchaseRequest = {
      ...mockPendingRequests[0],
      id: 'req-pps43',
      lines: [
        {
          id: 'line-pps43',
          workspace_product_id: 'prod-gloves',
          quantity: '20.000000',
          estimated_unit_price: { amount: '15.00', currency: 'SAR' },
          note: null,
        },
      ],
    };
    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: [testRequest], next_cursor: null }),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    component.toggleExpand('req-pps43');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const quantityCell = compiled.querySelector('.quantity-col');
    expect(quantityCell?.textContent?.trim()).toBe('20');

    TestBed.inject(TranslateService).use('ar');
    component.toggleExpand('req-pps43');
    fixture.detectChanges();
    component.toggleExpand('req-pps43');
    fixture.detectChanges();

    expect(compiled.querySelector('.quantity-col')?.textContent?.trim()).toBe('٢٠');
  });

  it('should format required-by dates, line count labels, and numbers via helper methods', () => {
    expect(component.formatRequiredBy('2026-09-20')).toBe('Sep 20, 2026');
    expect(component.formatRequiredBy(null)).toBe('—');
    expect(component.formatRequiredBy(undefined)).toBe('—');
    expect(component.formatRequiredBy('invalid')).toBe('—');

    expect(component.lineCountLabel(0)).toBe('0 lines');
    expect(component.lineCountLabel(1)).toBe('1 line');
    expect(component.lineCountLabel(2)).toBe('2 lines');
    expect(component.lineCountLabel(5)).toBe('5 lines');

    expect(component.formatNumber(2)).toBe('2');

    TestBed.inject(TranslateService).use('ar');

    expect(component.formatRequiredBy('2026-09-20')).toContain('٢٠');
    expect(component.lineCountLabel(0)).toBe('لا توجد بنود');
    expect(component.lineCountLabel(1)).toBe('بند واحد');
    expect(component.lineCountLabel(2)).toBe('بندان');
    expect(component.lineCountLabel(3)).toBe('٣ بنود');
    expect(component.lineCountLabel(11)).toBe('١١ بندًا');
    expect(component.lineCountLabel(100)).toBe('١٠٠ بند');
    expect(component.formatNumber(2)).toBe('٢');
  });

  it('should format required-by date, line count labels, and line items title in en and ar (PPS-48)', () => {
    const testRequests: PurchaseRequest[] = [
      {
        ...mockPendingRequests[0],
        id: 'req-2-lines',
        required_by_date: '2026-09-20',
        lines: [mockPendingRequests[0].lines[0], mockPendingRequests[0].lines[1]],
      },
      {
        ...mockPendingRequests[0],
        id: 'req-1-line',
        required_by_date: '2026-09-20',
        lines: [mockPendingRequests[0].lines[0]],
      },
      {
        ...mockPendingRequests[0],
        id: 'req-3-lines',
        required_by_date: '2026-09-20',
        lines: [
          mockPendingRequests[0].lines[0],
          mockPendingRequests[0].lines[1],
          { ...mockPendingRequests[0].lines[0], id: 'line-3' },
        ],
      },
    ];

    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: testRequests, next_cursor: null }),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    component.toggleExpand('req-2-lines');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const dateCells = compiled.querySelectorAll('.date-cell');
    expect(dateCells[0]?.textContent?.trim()).toBe('Sep 20, 2026');

    const lineCountSpans = compiled.querySelectorAll('.lines-count');
    expect(lineCountSpans[0]?.textContent?.trim()).toBe('2 lines');
    expect(lineCountSpans[1]?.textContent?.trim()).toBe('1 line');

    const titleEl = compiled.querySelector('.line-details-title');
    expect(titleEl?.textContent?.trim()).toBe('Line Items (2)');

    // Switch to Arabic and verify locale-aware formatting and plural categories
    TestBed.inject(TranslateService).use('ar');
    fixture.detectChanges();

    expect(dateCells[0]?.textContent).toContain('٢٠');
    expect(lineCountSpans[0]?.textContent?.trim()).toBe('بندان');
    expect(lineCountSpans[1]?.textContent?.trim()).toBe('بند واحد');
    expect(lineCountSpans[2]?.textContent?.trim()).toBe('٣ بنود');
    expect(compiled.querySelector('.line-details-title')?.textContent?.trim()).toContain('(٢)');
  });

  // Guards PPS-60: in Arabic, the Required By date suffered a sub-pixel overflow
  // under Material's table ellipsis. Setting overflow: visible prevents the clip
  // without distorting column widths. The clip itself depends on real font metrics
  // and is verified by the landing-gallery capture.
  it('prevents clipping on the Required By cell via date-cell styling', () => {
    const cell = fixture.nativeElement.querySelector('td.mat-column-requiredByDate') as HTMLElement;
    expect(cell).toBeTruthy();
    expect(cell.classList.contains('date-cell')).toBeTrue();
    expect(getComputedStyle(cell).overflow).toBe('visible');
  });

  it('renders approve and reject buttons inside the actions cell and lines toggle in lines cell', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const actionsCell = compiled.querySelector('td.mat-column-actions');
    expect(actionsCell).not.toBeNull();
    expect(actionsCell?.querySelector('.approve-btn')).not.toBeNull();
    expect(actionsCell?.querySelector('.reject-btn')).not.toBeNull();

    const linesCell = compiled.querySelector('td.mat-column-lines');
    expect(linesCell).not.toBeNull();
    expect(linesCell?.querySelector('.approve-btn')).toBeNull();
    expect(linesCell?.querySelector('.reject-btn')).toBeNull();
  });

  it('makes the whole N lines control one clickable button without tooltip whose accessible name contains visible text and flips aria-expanded', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const linesCell = compiled.querySelector('td.mat-column-lines');
    const toggleBtn = linesCell?.querySelector<HTMLButtonElement>('.lines-toggle-btn');
    expect(toggleBtn).not.toBeNull();
    const visibleText = toggleBtn?.querySelector('.lines-count')?.textContent?.trim() ?? '';
    expect(visibleText).toBe('2 lines');
    expect(toggleBtn?.textContent).toContain(visibleText);
    expect(toggleBtn?.getAttribute('aria-label')).toBeNull();
    expect(toggleBtn?.getAttribute('aria-expanded')).toBe('false');
    expect(toggleBtn?.hasAttribute('matTooltip')).toBeFalse();
    expect(toggleBtn?.getAttribute('ng-reflect-message')).toBeNull();

    // Clicking the toggle button expands lines
    toggleBtn?.click();
    fixture.detectChanges();
    expect(component.isExpanded('req-001')).toBeTrue();
    expect(toggleBtn?.getAttribute('aria-expanded')).toBe('true');

    // Clicking again collapses lines
    toggleBtn?.click();
    fixture.detectChanges();
    expect(component.isExpanded('req-001')).toBeFalse();
    expect(toggleBtn?.getAttribute('aria-expanded')).toBe('false');
  });

  it('renders "—" for empty optional line note instead of "Not available"', () => {
    component.toggleExpand('req-001');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const noteCols = compiled.querySelectorAll('.note-col');
    expect(noteCols.length).toBe(2);
    expect(noteCols[0].textContent?.trim()).toBe('Latex-free boxes');
    // Line 2 has note: null -> should be "—"
    expect(noteCols[1].textContent?.trim()).toBe('—');
  });

  it('passes amount and branch name to decision dialog and restates what is approved in title', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ confirmed: false }),
    } as MatDialogRef<unknown, unknown>);

    component.openDecisionDialog(mockPendingRequests[0], 'approve');

    expect(dialogSpy.open).toHaveBeenCalledWith(
      jasmine.anything(),
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          action: 'approve',
          requestId: 'req-001',
          amount: 'SAR 1,250',
          branchName: 'North Branch',
        }),
      }),
    );
  });

  it('omits amount when estimated_total is null so branch-only title can take over', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ confirmed: false }),
    } as MatDialogRef<unknown, unknown>);

    const reqWithoutTotal = {
      ...mockPendingRequests[0],
      estimated_total: null,
    };

    component.openDecisionDialog(reqWithoutTotal, 'approve');

    const dialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as ApprovalDecisionDialogData;
    expect(dialogData.amount).toBeUndefined();
  });

  it('omits branchName when branch id is not in branchNameById so default title takes over', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ confirmed: false }),
    } as MatDialogRef<unknown, unknown>);

    const reqWithUnknownBranch = {
      ...mockPendingRequests[0],
      branch_id: 'unknown-branch-uuid',
    };

    component.openDecisionDialog(reqWithUnknownBranch, 'approve');

    const dialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as ApprovalDecisionDialogData;
    expect(dialogData.branchName).toBeUndefined();
  });
});

describe('ApprovalDecisionDialogComponent', () => {
  let dialogFixture: ComponentFixture<ApprovalDecisionDialogComponent>;

  it('restates what is approved in the dialog title with amount and branch name in en and ar', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ApprovalDecisionDialogComponent],
      providers: [
        provideTranslateService(),
        {
          provide: MAT_DIALOG_DATA,
          useValue: {
            action: 'approve',
            requestId: 'req-001',
            amount: 'SAR 4,137',
            branchName: 'فرع العليا',
          },
        },
        {
          provide: MatDialogRef,
          useValue: jasmine.createSpyObj('MatDialogRef', ['close']),
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');

    dialogFixture = TestBed.createComponent(ApprovalDecisionDialogComponent);
    dialogFixture.detectChanges();

    const titleEl = dialogFixture.nativeElement.querySelector('[mat-dialog-title]');
    expect(titleEl?.textContent?.trim()).toBe('Approve SAR 4,137 for فرع العليا?');

    translate.use('ar');
    dialogFixture.detectChanges();
    expect(titleEl?.textContent?.trim()).toBe('اعتماد SAR 4,137 لـ فرع العليا؟');
  });

  it('shows branch-only title when amount is missing (estimated_total was null) in en and ar', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ApprovalDecisionDialogComponent],
      providers: [
        provideTranslateService(),
        {
          provide: MAT_DIALOG_DATA,
          useValue: {
            action: 'approve',
            requestId: 'req-001',
            branchName: 'North Branch',
          },
        },
        {
          provide: MatDialogRef,
          useValue: jasmine.createSpyObj('MatDialogRef', ['close']),
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');

    dialogFixture = TestBed.createComponent(ApprovalDecisionDialogComponent);
    dialogFixture.detectChanges();

    const titleEl = dialogFixture.nativeElement.querySelector('[mat-dialog-title]');
    expect(titleEl?.textContent?.trim()).toBe('Approve the request for North Branch?');

    translate.use('ar');
    dialogFixture.detectChanges();
    expect(titleEl?.textContent?.trim()).toBe('اعتماد الطلب لـ North Branch؟');
  });

  it('shows default title when branchName is missing (unknown branch) in en and ar', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ApprovalDecisionDialogComponent],
      providers: [
        provideTranslateService(),
        {
          provide: MAT_DIALOG_DATA,
          useValue: {
            action: 'approve',
            requestId: 'req-001',
            amount: 'SAR 1,250',
          },
        },
        {
          provide: MatDialogRef,
          useValue: jasmine.createSpyObj('MatDialogRef', ['close']),
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');

    dialogFixture = TestBed.createComponent(ApprovalDecisionDialogComponent);
    dialogFixture.detectChanges();

    const titleEl = dialogFixture.nativeElement.querySelector('[mat-dialog-title]');
    expect(titleEl?.textContent?.trim()).toBe('Approve Purchase Request');

    translate.use('ar');
    dialogFixture.detectChanges();
    expect(titleEl?.textContent?.trim()).toBe('اعتماد طلب الشراء');
  });

  it('shows default title when neither amount nor branchName is present in en and ar', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ApprovalDecisionDialogComponent],
      providers: [
        provideTranslateService(),
        {
          provide: MAT_DIALOG_DATA,
          useValue: {
            action: 'approve',
            requestId: 'req-001',
          },
        },
        {
          provide: MatDialogRef,
          useValue: jasmine.createSpyObj('MatDialogRef', ['close']),
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');

    dialogFixture = TestBed.createComponent(ApprovalDecisionDialogComponent);
    dialogFixture.detectChanges();

    const titleEl = dialogFixture.nativeElement.querySelector('[mat-dialog-title]');
    expect(titleEl?.textContent?.trim()).toBe('Approve Purchase Request');

    translate.use('ar');
    dialogFixture.detectChanges();
    expect(titleEl?.textContent?.trim()).toBe('اعتماد طلب الشراء');
  });
});
