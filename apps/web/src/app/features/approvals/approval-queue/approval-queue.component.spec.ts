import { HttpErrorResponse } from '@angular/common/http';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { PurchaseRequest } from '../../../core/api/models';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';
import { ApprovalsApiService } from '../approvals-api';
import { ApprovalQueueComponent } from './approval-queue.component';

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

  beforeEach(async () => {
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
      ],
    })
      .overrideComponent(ApprovalQueueComponent, {
        set: {
          providers: [
            { provide: MatDialog, useValue: dialogSpy },
            { provide: MatSnackBar, useValue: snackBarSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
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
    expect(compiled.textContent).toContain('2026-09-20');
    expect(compiled.textContent).toContain('SAR 1,250');

    expect(compiled.textContent).toContain('South Branch');
    expect(compiled.textContent).toContain('None (branch-level)');
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
    expect(compiled.textContent).toContain('Remaining: EGP 1,250.5');
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
    expect(snackBarSpy.open).toHaveBeenCalledWith('Request approved.', undefined, {
      duration: 3500,
    });
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
});
