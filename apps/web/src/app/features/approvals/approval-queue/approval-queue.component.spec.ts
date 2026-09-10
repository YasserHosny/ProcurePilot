import { HttpErrorResponse } from '@angular/common/http';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { PurchaseRequest } from '../../../core/api/models';
import { RequestsApiService } from '../../requests/requests-api';
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
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  beforeEach(async () => {
    approvalsApi = jasmine.createSpyObj('ApprovalsApiService', ['listPendingApprovals']);
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'approveRequest',
      'rejectRequest',
    ]);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);

    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: mockPendingRequests, next_cursor: null }),
    );

    await TestBed.configureTestingModule({
      imports: [ApprovalQueueComponent, TranslateModule.forRoot()],
      providers: [
        { provide: ApprovalsApiService, useValue: approvalsApi },
        { provide: RequestsApiService, useValue: requestsApi },
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
    expect(component.pendingRequests().length).toBe(2);
    expect(component.isLoading()).toBeFalse();
  });

  it('should display rows with requester, branch, cost centre, required-by date, and total', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const rows = compiled.querySelectorAll('.request-row');
    expect(rows.length).toBe(2);

    expect(compiled.textContent).toContain('mem-requester-1');
    expect(compiled.textContent).toContain('branch-north');
    expect(compiled.textContent).toContain('cc-ops');
    expect(compiled.textContent).toContain('2026-09-20');
    expect(compiled.textContent).toContain('SAR 1250.00');

    expect(compiled.textContent).toContain('mem-requester-2');
    expect(compiled.textContent).toContain('branch-south');
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
    expect(warningRemaining?.textContent?.trim()).toBe('Remaining: SAR 100.00');
  });

  it('should render quiet remaining budget when within budget', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const budgetRemaining = compiled.querySelector('.budget-remaining');
    expect(budgetRemaining).toBeTruthy();
    expect(budgetRemaining?.textContent?.trim()).toBe('Remaining: SAR 5000.00');
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
    expect(compiled.textContent).toContain('prod-gloves');
    expect(compiled.textContent).toContain('prod-masks');
    expect(compiled.textContent).toContain('Latex-free boxes');

    component.toggleExpand('req-001');
    expect(component.isExpanded('req-001')).toBeFalse();
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

  it('should correctly format money and line prices', () => {
    expect(component.formatMoney(mockPendingRequests[0])).toBe('SAR 1250.00');
    expect(component.formatMoney(mockPendingRequests[1])).toBe('Not available');
    expect(component.formatLinePrice(mockPendingRequests[0].lines[0])).toBe('SAR 15.00');
    expect(
      component.formatLinePrice({
        id: 'l3',
        workspace_product_id: 'p3',
        quantity: '1',
      }),
    ).toBe('Not available');
  });
});
