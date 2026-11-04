import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, convertToParamMap, type ParamMap } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { ApiService } from '../../../core/api/api.service';
import type { PendingApprovalList, PurchaseRequest, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';
import { ApprovalsApiService } from '../approvals-api';
import {
  ApprovalDecisionDialogComponent,
  ApprovalQueueComponent,
  type ApprovalDecisionDialogData,
  type GroupQueueItem,
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
        quoted_prices_include_vat: false,
        quoted_vat_rate: null,
        quoted_net_unit_price: null,
        id: 'line-1',
        workspace_product_id: 'prod-gloves',
        quantity: '50',
        estimated_unit_price: { amount: '15.00', currency: 'SAR' },
        note: 'Latex-free boxes',
      },
      {
        quoted_prices_include_vat: false,
        quoted_vat_rate: null,
        quoted_net_unit_price: null,
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
  let queryParamMapSubject: BehaviorSubject<ParamMap>;
  const role = signal<Role | null>('buyer');
  let sessionSpy: { hasRole: jasmine.Spy; role: typeof role; currentMember: jasmine.Spy };

  async function configureQueue(initialParams: Record<string, string> = {}): Promise<void> {
    queryParamMapSubject = new BehaviorSubject<ParamMap>(convertToParamMap(initialParams));

    await TestBed.configureTestingModule({
      imports: [ApprovalQueueComponent],
      providers: [
        provideTranslateService(),
        {
          provide: ActivatedRoute,
          useValue: {
            queryParamMap: queryParamMapSubject.asObservable(),
            snapshot: {
              get queryParamMap() {
                return queryParamMapSubject.value;
              },
            },
          },
        },
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
  }

  beforeEach(async () => {
    role.set('buyer');
    sessionSpy = {
      currentMember: jasmine.createSpy('currentMember').and.returnValue({ membership_id: 'mem-requester-1' }),
      hasRole: jasmine.createSpy('hasRole').and.callFake((...roles: readonly Role[]) => {
        const current = role();
        return current ? roles.includes(current) : false;
      }),
      role,
    };
    approvalsApi = jasmine.createSpyObj('ApprovalsApiService', [
      'listPendingApprovals',
      'approveGroup',
      'rejectGroup',
    ]);
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'approveRequest',
      'rejectRequest',
      'getRequest',
    ]);
    requestsApi.getRequest.and.returnValue(of(mockPendingRequests[0]));
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
      of({ items: mockPendingRequests, next_cursor: null, total: mockPendingRequests.length }),
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

    await configureQueue();
  });

  describe('PPS-167 self approval', () => {
    function markedRequest(flag: boolean | undefined): PurchaseRequest {
      const step = {
        id: 'step-own', assigned_membership_id: 'mem-requester-1',
        source: 'owner_fallback' as const, status: 'pending' as const,
        ...(flag === undefined ? {} : { self_approval: flag }),
      };
      return { ...mockPendingRequests[0], approval_step: step };
    }

    for (const split of [false, true]) {
      for (const viewer of ['another-member', null]) {
        it(`hides a colleague's self-approval badge: split=${split}, viewer=${viewer}`, () => {
          sessionSpy.currentMember.and.returnValue(viewer ? { membership_id: viewer } : null);
          const request = markedRequest(true);
          component.pendingRequests.set(split ? [{
            ...request,
            request_group: {
              id: 'group-own', rfq_id: 'rfq-own', position: 1, size: 1,
              combined_total: { amount: '1250', currency: 'SAR' },
              best_single_total: null, saving: null, sibling_request_ids: [],
            },
          }] : [request]);
          fixture.detectChanges();
          expect((fixture.nativeElement as HTMLElement).querySelector('.own-request-badge')).toBeNull();
        });
      }
    }

    for (const locale of ['en', 'ar']) {
      for (const flag of [true, false, undefined]) {
        for (const split of [false, true]) {
          it(`renders own-request badge only for true: ${locale}, ${flag}, split=${split}`, () => {
            TestBed.inject(TranslateService).use(locale);
            const marked = markedRequest(flag);
            const requests = split
              ? [{ ...markedRequest(true), requested_by_membership_id: 'another-member' }, { ...marked, id: 'req-other' }].map((request, i) => ({
                  ...request,
                  request_group: {
                    id: 'group-own', rfq_id: 'rfq-own', position: i + 1, size: 2,
                    combined_total: { amount: '2500', currency: 'SAR' },
                    best_single_total: null, saving: null, sibling_request_ids: [],
                  },
                }))
              : [marked];
            component.pendingRequests.set(requests);
            fixture.detectChanges();
            const badges = (fixture.nativeElement as HTMLElement).querySelectorAll('.own-request-badge');
            expect(badges.length).toBe(flag === true ? 1 : 0);
            if (flag === true) {
              expect(badges[0]?.textContent?.trim()).toBe(locale === 'ar' ? 'طلبك أنت' : 'Your own request');
            }
          });
        }
      }
      for (const action of ['approve', 'reject'] as const) {
        for (const split of [false, true]) {
          it(`localizes refused ${action}, reloads stale rows: ${locale}, split=${split}`, () => {
            TestBed.inject(TranslateService).use(locale);
            const failure = throwError(() => new HttpErrorResponse({
              status: 403, error: { message: 'Generic refusal', details: { reason: 'self_decision_not_allowed' } },
            }));
            requestsApi.approveRequest.and.returnValue(failure);
            requestsApi.rejectRequest.and.returnValue(failure);
            approvalsApi.approveGroup.and.returnValue(failure);
            approvalsApi.rejectGroup.and.returnValue(failure);
            approvalsApi.listPendingApprovals.and.returnValue(of({ items: [], next_cursor: null , total: 0}));
            const before = approvalsApi.listPendingApprovals.calls.count();
            if (split) component.submitGroupDecision('group-own', action);
            else component.submitDecision('req-001', action);
            fixture.detectChanges();
            const message = locale === 'ar'
              ? 'لا يمكنك اعتماد أو رفض طلب قدّمته بنفسك. يجب أن يتخذ القرار مالك آخر أو مسؤول اعتماد.'
              : "You can't decide a request you submitted. Another owner or approver needs to decide it.";
            expect(component.errorMessage()).toBe(message);
            expect((fixture.nativeElement as HTMLElement).textContent).toContain(message);
            expect(approvalsApi.listPendingApprovals.calls.count()).toBe(before + 1);
            expect(component.pendingRequests()).toEqual([]);
          });
        }
      }
    }

    for (const reason of ['another_reason', undefined]) {
      it(`preserves other 403 behaviour: ${reason}`, () => {
        const before = approvalsApi.listPendingApprovals.calls.count();
        requestsApi.approveRequest.and.returnValue(throwError(() => new HttpErrorResponse({
          status: 403, error: { message: 'Existing refusal', trace_id: 'trace-own', details: { reason } },
        })));
        component.submitDecision('req-001', 'approve');
        expect(component.errorMessage()).toBe('Existing refusal');
        expect(component.errorTraceId()).toBe('trace-own');
        expect(approvalsApi.listPendingApprovals.calls.count()).toBe(before);
      });
    }
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
        next_cursor: null, total: 0,
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
      {
        ...mockPendingRequests[0],
        id: 'req-plus-email',
        requester_name: null,
        requester_email: 'someone+pp-sa-owner@gmail.com',
      },
    ];
    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: requestsWithRequesterInfo, next_cursor: null , total: 0}),
    );
    component.loadPendingApprovals();
    fixture.detectChanges();

    const cellElements = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('.requester-cell'),
    );
    const cells = cellElements.map((el) => el.textContent?.trim());
    expect(cells).toEqual(['Nadia Mansour', 'buyer', 'abcdef12', 'someone+pp-sa-owner']);

    // Name present has no tooltip or aria-label with email
    const nameEl = cellElements[0].querySelector('[matTooltip], [title], [aria-label]');
    expect(nameEl).toBeNull();

    // Plus-address renders local part in an element whose tooltip and aria-label is the full address
    const plusEl = cellElements[3].querySelector('[matTooltip], [title], [aria-label]');
    expect(plusEl).toBeTruthy();
    expect(plusEl?.textContent?.trim()).toBe('someone+pp-sa-owner');
    expect(plusEl?.getAttribute('aria-label')).toBe('someone+pp-sa-owner@gmail.com');
    expect(plusEl?.getAttribute('title')).toBe('someone+pp-sa-owner@gmail.com');
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
      of({ items: requestsWithStatuses, next_cursor: null , total: 0}),
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
      of({ items: [requestWithoutBudget], next_cursor: null , total: 0}),
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
      of({ items: [], next_cursor: null , total: 0}),
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
        quoted_prices_include_vat: false,
        quoted_vat_rate: null,
        quoted_net_unit_price: null,
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
          quoted_prices_include_vat: false,
          quoted_vat_rate: null,
          quoted_net_unit_price: null,
          id: 'line-pps43',
          workspace_product_id: 'prod-gloves',
          quantity: '20.000000',
          estimated_unit_price: { amount: '15.00', currency: 'SAR' },
          note: null,
        },
      ],
    };
    approvalsApi.listPendingApprovals.and.returnValue(
      of({ items: [testRequest], next_cursor: null , total: 0}),
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
      of({ items: testRequests, next_cursor: null , total: 0}),
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
    const actionsCell = compiled.querySelector('td.mat-column-actions') as HTMLTableCellElement | null;
    expect(actionsCell).not.toBeNull();
    expect(actionsCell?.querySelector('.approve-btn')).not.toBeNull();
    expect(actionsCell?.querySelector('.reject-btn')).not.toBeNull();

    const linesCell = compiled.querySelector('td.mat-column-lines') as HTMLTableCellElement | null;
    expect(linesCell).not.toBeNull();
    expect(linesCell?.querySelector('.approve-btn')).toBeNull();
    expect(linesCell?.querySelector('.reject-btn')).toBeNull();

    const approveBtn = compiled.querySelector('.approve-btn') as HTMLButtonElement | null;
    expect(approveBtn).not.toBeNull();
    expect(approveBtn?.closest('td')).toBe(actionsCell);
    expect(approveBtn?.closest('td')).not.toBe(linesCell);

    if (linesCell && actionsCell) {
      expect(getComputedStyle(linesCell).display).toBe('table-cell');
      expect(getComputedStyle(actionsCell).display).toBe('table-cell');
    }
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

  describe('Spec 024 User Story 3 (T029) — Split approval queue', () => {
    const mockGroupedRequests: PurchaseRequest[] = [
      {
        id: 'req-group-1',
        branch_id: 'branch-north',
        cost_centre_id: 'cc-ops',
        requested_by_membership_id: 'mem-requester-1',
        required_by_date: '2026-09-20',
        status: 'submitted',
        has_incomplete_estimate: false,
        estimated_total: { amount: '2773.00', currency: 'SAR' },
        source: {
          rfq_id: 'rfq-split-001',
          rfq_response_id: 'resp-1',
          quotation_id: 'q-1',
          supplier_id: 'sup-1',
          supplier_name: 'الذهبي',
        },
        request_group: {
          id: 'grp-001',
          rfq_id: 'rfq-split-001',
          position: 1,
          size: 2,
          combined_total: { amount: '4063.00', currency: 'SAR' },
          best_single_total: { amount: '4137.00', currency: 'SAR' },
          saving: { amount: '74.00', currency: 'SAR' },
          sibling_request_ids: ['req-group-2'],
        },
        budget_status: {
          remaining_amount: { amount: '5000.00', currency: 'SAR' },
          exceeds: false,
          status: 'within',
        },
        lines: [
          {
            quoted_prices_include_vat: false,
            quoted_vat_rate: null,
            quoted_net_unit_price: null,
            id: 'line-g1',
            workspace_product_id: 'prod-gloves',
            quantity: '50',
            estimated_unit_price: { amount: '15.00', currency: 'SAR' },
            note: 'Rice & flour',
          },
        ],
        created_at: '2026-09-10T10:00:00Z',
        submitted_at: '2026-09-10T10:05:00Z',
      },
      {
        id: 'req-group-2',
        branch_id: 'branch-north',
        cost_centre_id: 'cc-ops',
        requested_by_membership_id: 'mem-requester-1',
        required_by_date: '2026-09-20',
        status: 'submitted',
        has_incomplete_estimate: false,
        estimated_total: { amount: '1290.00', currency: 'SAR' },
        source: {
          rfq_id: 'rfq-split-001',
          rfq_response_id: 'resp-2',
          quotation_id: 'q-2',
          supplier_id: 'sup-2',
          supplier_name: 'الوفرة',
        },
        request_group: {
          id: 'grp-001',
          rfq_id: 'rfq-split-001',
          position: 2,
          size: 2,
          combined_total: { amount: '4063.00', currency: 'SAR' },
          best_single_total: { amount: '4137.00', currency: 'SAR' },
          saving: { amount: '74.00', currency: 'SAR' },
          sibling_request_ids: ['req-group-1'],
        },
        budget_status: {
          remaining_amount: { amount: '3710.00', currency: 'SAR' },
          exceeds: false,
          status: 'within',
        },
        lines: [
          {
            quoted_prices_include_vat: false,
            quoted_vat_rate: null,
            quoted_net_unit_price: null,
            id: 'line-g2',
            workspace_product_id: 'prod-masks',
            quantity: '100',
            estimated_unit_price: { amount: '5.00', currency: 'SAR' },
            note: 'Oil & sugar',
          },
        ],
        created_at: '2026-09-10T10:01:00Z',
        submitted_at: '2026-09-10T10:05:00Z',
      },
    ];

    it('two pending requests in one group render as one row with the combined total and the saving', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockGroupedRequests, next_cursor: null , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      const rows = fixture.nativeElement.querySelectorAll('tr.request-row');
      expect(rows.length).toBe(1);

      const rowText = rows[0].textContent;
      expect(rowText).toContain('4,063');
      expect(rowText).toContain('74');
      expect(rowText).toContain('Split from RFQ');
      expect(rowText).toContain('2 requests');
    });

    it('Approve calls /request-groups/{id}/approve once (not two single approves)', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockGroupedRequests, next_cursor: null , total: 0}),
      );
      approvalsApi.approveGroup.and.returnValue(of(mockGroupedRequests));
      dialogSpy.open.and.returnValue({
        afterClosed: () => of({ confirmed: true, comment: 'Looks good' }),
      } as unknown as ReturnType<MatDialog['open']>);

      component.loadPendingApprovals();
      fixture.detectChanges();

      const approveBtn = fixture.nativeElement.querySelector('.approve-btn');
      expect(approveBtn).toBeTruthy();
      approveBtn.click();
      fixture.detectChanges();

      expect(dialogSpy.open).toHaveBeenCalled();
      const dialogConfig = dialogSpy.open.calls.mostRecent().args[1] as {
        data: { action: string; amount?: string; branchName?: string; requestId: string };
      };
      expect(dialogConfig.data.action).toBe('approve');
      expect(dialogConfig.data.amount).toContain('4,063');
      expect(dialogConfig.data.branchName).toBe('North Branch');

      expect(approvalsApi.approveGroup).toHaveBeenCalledTimes(1);
      const approveCallArgs = approvalsApi.approveGroup.calls.mostRecent().args;
      expect(approveCallArgs[0]).toBe('grp-001');
      expect(approveCallArgs[1]?.comment).toBe('Looks good');
      expect(approveCallArgs[2]).toBeTruthy(); // idempotency key

      expect(requestsApi.approveRequest).not.toHaveBeenCalled();
    });

    it('an ungrouped request is unchanged', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [mockPendingRequests[0]], next_cursor: null , total: 0}),
      );
      requestsApi.approveRequest.and.returnValue(of(mockPendingRequests[0]));
      dialogSpy.open.and.returnValue({
        afterClosed: () => of({ confirmed: true }),
      } as unknown as ReturnType<MatDialog['open']>);

      component.loadPendingApprovals();
      fixture.detectChanges();

      const rows = fixture.nativeElement.querySelectorAll('tr.request-row');
      expect(rows.length).toBe(1);
      expect(rows[0].textContent).toContain('1,250');
      expect(rows[0].textContent).not.toContain('Split from RFQ');

      const approveBtn = fixture.nativeElement.querySelector('.approve-btn');
      approveBtn.click();
      fixture.detectChanges();

      expect(requestsApi.approveRequest).toHaveBeenCalledTimes(1);
      expect(requestsApi.approveRequest.calls.mostRecent().args[0]).toBe('req-001');
      expect(approvalsApi.approveGroup).not.toHaveBeenCalled();
    });

    it('Reject calls /request-groups/{id}/reject once with comment', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockGroupedRequests, next_cursor: null , total: 0}),
      );
      approvalsApi.rejectGroup.and.returnValue(of(mockGroupedRequests));
      dialogSpy.open.and.returnValue({
        afterClosed: () => of({ confirmed: true, comment: 'Over budget' }),
      } as unknown as ReturnType<MatDialog['open']>);

      component.loadPendingApprovals();
      fixture.detectChanges();

      const rejectBtn = fixture.nativeElement.querySelector('.reject-btn');
      expect(rejectBtn).toBeTruthy();
      rejectBtn.click();
      fixture.detectChanges();

      expect(dialogSpy.open).toHaveBeenCalled();
      expect(approvalsApi.rejectGroup).toHaveBeenCalledTimes(1);
      expect(approvalsApi.rejectGroup.calls.mostRecent().args[0]).toBe('grp-001');
      expect(approvalsApi.rejectGroup.calls.mostRecent().args[1]).toEqual({ comment: 'Over budget' });
      expect(approvalsApi.rejectGroup.calls.mostRecent().args[2]).toBeTruthy(); // idempotency key

      expect(requestsApi.rejectRequest).not.toHaveBeenCalled();
    });

    it('expanding group row shows each request supplier, lines and total', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockGroupedRequests, next_cursor: null , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      const toggleBtn = fixture.nativeElement.querySelector('.lines-toggle-btn');
      expect(toggleBtn).toBeTruthy();
      toggleBtn.click();
      fixture.detectChanges();

      expect(component.isExpanded('grp-001')).toBeTrue();
      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.textContent).toContain('الذهبي');
      expect(compiled.textContent).toContain('الوفرة');
      expect(compiled.textContent).toContain('2,773');
      expect(compiled.textContent).toContain('1,290');
    });

    it('part_of_split shows the message pointing to the group action', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [mockPendingRequests[0]], next_cursor: null , total: 0}),
      );
      const errorResp = new HttpErrorResponse({
        error: { code: 'conflict', message: 'Conflict', details: { reason: 'part_of_split' } },
        status: 409,
        statusText: 'Conflict',
      });
      requestsApi.approveRequest.and.returnValue(throwError(() => errorResp));
      dialogSpy.open.and.returnValue({
        afterClosed: () => of({ confirmed: true }),
      } as unknown as ReturnType<MatDialog['open']>);

      component.loadPendingApprovals();
      fixture.detectChanges();

      const approveBtn = fixture.nativeElement.querySelector('.approve-btn');
      approveBtn.click();
      fixture.detectChanges();

      expect(component.errorMessage()).toBeTruthy();
      expect(component.errorMessage()?.toLowerCase()).toContain('split');
    });
  });

  describe('P-170 (PPS-164) — Pagination and Group Completeness Gate', () => {
    it('pagination: appends next page and de-duplicates by request id', () => {
      const page1Item1 = { ...mockPendingRequests[0], id: 'req-p1-1' };
      const page1Item2 = { ...mockPendingRequests[1], id: 'req-p1-2' };
      const page2Item1 = { ...mockPendingRequests[0], id: 'req-p1-2' }; // duplicate
      const page2Item2 = { ...mockPendingRequests[0], id: 'req-p2-1' }; // new

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [page1Item1, page1Item2], next_cursor: 'cursor-page-2' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(component.pendingRequests().length).toBe(2);
      expect(component.nextCursor()).toBe('cursor-page-2');

      const loadMoreBtn = fixture.nativeElement.querySelector('[data-testid="load-more-btn"]');
      expect(loadMoreBtn).toBeTruthy();

      const statusEl = fixture.nativeElement.querySelector('[data-testid="pagination-status"]');
      expect(statusEl?.textContent).toContain('Showing 2 requests, more available');

      // Next page returns page2Item1 (duplicate) and page2Item2 (new), with next_cursor: null
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [page2Item1, page2Item2], next_cursor: null , total: 0}),
      );

      loadMoreBtn.click();
      fixture.detectChanges();

      expect(approvalsApi.listPendingApprovals).toHaveBeenCalledWith({
        cursor: 'cursor-page-2',
        limit: 50,
      });
      // Deduplicated: 2 original + 1 new = 3
      expect(component.pendingRequests().length).toBe(3);
      expect(component.pendingRequests().map((r) => r.id)).toEqual(['req-p1-1', 'req-p1-2', 'req-p2-1']);
      expect(component.nextCursor()).toBeNull();

      // Button hidden when no cursor
      const loadMoreBtnAfter = fixture.nativeElement.querySelector('[data-testid="load-more-btn"]');
      expect(loadMoreBtnAfter).toBeNull();

      // Status updated
      expect(statusEl?.textContent).toContain('Showing 3 requests');
      expect(statusEl?.textContent).not.toContain('more available');
    });

    it('pagination: button hidden when no cursor on initial load', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: null , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(component.nextCursor()).toBeNull();
      const loadMoreBtn = fixture.nativeElement.querySelector('[data-testid="load-more-btn"]');
      expect(loadMoreBtn).toBeNull();

      const statusEl = fixture.nativeElement.querySelector('[data-testid="pagination-status"]');
      expect(statusEl?.textContent).toContain('Showing 2 requests');
      expect(statusEl?.textContent).not.toContain('more available');
    });

    it('pagination: failure keeps loaded rows, shows error banner and keeps load more available to retry', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: 'cursor-retry' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(component.pendingRequests().length).toBe(2);

      // Trigger error on load more
      approvalsApi.listPendingApprovals.and.returnValue(
        throwError(() => new Error('Server unavailable')),
      );

      const loadMoreBtn = fixture.nativeElement.querySelector('[data-testid="load-more-btn"]');
      loadMoreBtn.click();
      fixture.detectChanges();

      // Rows kept
      expect(component.pendingRequests().length).toBe(2);
      // Next cursor preserved
      expect(component.nextCursor()).toBe('cursor-retry');
      // Error banner visible
      expect(component.errorMessage()).toBeTruthy();
      const errorBanner = fixture.nativeElement.querySelector('.error-banner');
      expect(errorBanner).toBeTruthy();

      // Load more button remains available to retry
      const retryBtn = fixture.nativeElement.querySelector('[data-testid="load-more-btn"]');
      expect(retryBtn).toBeTruthy();
      expect(retryBtn.disabled).toBeFalse();
    });

    it('pagination: plain new Error from listPendingApprovals during loadMore shows localized loadError text, not raw message', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: 'cursor-retry' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      approvalsApi.listPendingApprovals.and.returnValue(
        throwError(() => new Error('boom')),
      );

      component.loadMore();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Unable to load more requests. Please try again.');
      expect(component.errorMessage()).not.toContain('boom');
    });

    it('pagination: loadMore failure shows translated loadError for non-envelope HttpErrorResponse and envelope message for real API errors', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: 'cursor-retry' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      const expectedLoadError = 'Unable to load more requests. Please try again.';

      // Case 1: status 0 with ProgressEvent (network drop / aborted)
      approvalsApi.listPendingApprovals.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 0,
              error: new ProgressEvent('error'),
              url: '/api/v1/approvals/pending',
            }),
        ),
      );
      component.loadMore();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe(expectedLoadError);
      expect(component.errorMessage()).not.toContain('Http failure response');

      // Case 2: status 502 with HTML bad gateway string
      approvalsApi.listPendingApprovals.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 502,
              error: '<html>Bad Gateway</html>',
              url: '/api/v1/approvals/pending',
            }),
        ),
      );
      component.loadMore();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe(expectedLoadError);
      expect(component.errorMessage()).not.toContain('Bad Gateway');
      expect(component.errorMessage()).not.toContain('Http failure response');

      // Case 3: status 409 with real ProcurePilot error envelope {code, message}
      approvalsApi.listPendingApprovals.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 409,
              error: {
                code: 'CONFLICT',
                message: 'Approval cursor expired. Please refresh the queue.',
                trace_id: 'trace-409',
              },
            }),
        ),
      );
      component.loadMore();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Approval cursor expired. Please refresh the queue.');
      expect(component.errorTraceId()).toBe('trace-409');

      // Case 4: status 500 with real ProcurePilot error envelope {code, message}
      approvalsApi.listPendingApprovals.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 500,
              error: {
                code: 'DATABASE_ERROR',
                message: 'Database query timed out.',
                trace_id: 'trace-500',
              },
            }),
        ),
      );
      component.loadMore();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Database query timed out.');
      expect(component.errorTraceId()).toBe('trace-500');
    });

    it('pagination: double click does not fire two requests and shows loading spinner', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: 'cursor-slow' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      const pendingSubject = new Subject<PendingApprovalList>();
      approvalsApi.listPendingApprovals.calls.reset();
      approvalsApi.listPendingApprovals.and.returnValue(pendingSubject);

      const loadMoreBtn = fixture.nativeElement.querySelector('[data-testid="load-more-btn"]');
      loadMoreBtn.click();
      fixture.detectChanges();

      // Button is disabled and loading
      expect(component.isLoadingMore()).toBeTrue();
      expect(loadMoreBtn.disabled).toBeTrue();

      // Second click while in-flight
      loadMoreBtn.click();
      fixture.detectChanges();

      // Still only called once with cursor
      expect(approvalsApi.listPendingApprovals).toHaveBeenCalledTimes(1);
      expect(approvalsApi.listPendingApprovals).toHaveBeenCalledWith({
        cursor: 'cursor-slow',
        limit: 50,
      });

      // Complete in-flight
      pendingSubject.next({ items: [], next_cursor: null, total: 0 });
      pendingSubject.complete();
      fixture.detectChanges();

      expect(component.isLoadingMore()).toBeFalse();
    });

    it('stale loadMore in flight during loadPendingApprovals does not leave isLoadingMore stuck true', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: 'cursor-1' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(component.nextCursor()).toBe('cursor-1');
      expect(component.isLoadingMore()).toBeFalse();

      // Start loadMore with pending observable
      const pendingLoadMore$ = new Subject<PendingApprovalList>();
      approvalsApi.listPendingApprovals.calls.reset();
      approvalsApi.listPendingApprovals.and.returnValue(pendingLoadMore$);

      component.loadMore();
      fixture.detectChanges();

      expect(component.isLoadingMore()).toBeTrue();

      // While loadMore is in flight, a decision or reload triggers loadPendingApprovals()
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: 'cursor-2' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      // Old loadMore resolves now (stale response)
      pendingLoadMore$.next({ items: [], next_cursor: null, total: 0 });
      pendingLoadMore$.complete();
      fixture.detectChanges();

      // Assert isLoadingMore is false
      expect(component.isLoadingMore()).toBeFalse();

      // Assert a new loadMore works once reload returned cursor-2
      approvalsApi.listPendingApprovals.calls.reset();
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [], next_cursor: null , total: 0}),
      );
      component.loadMore();
      fixture.detectChanges();

      expect(approvalsApi.listPendingApprovals).toHaveBeenCalledWith({
        cursor: 'cursor-2',
        limit: 50,
      });
      expect(component.isLoadingMore()).toBeFalse();
    });

    it('decisions reload first page and reset cursor clearing accumulated rows', () => {
      const page1Item = { ...mockPendingRequests[0], id: 'req-single' };
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [page1Item], next_cursor: 'cur-page-2' , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      // Load page 2
      const page2Item = { ...mockPendingRequests[1], id: 'req-page-2' };
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [page2Item], next_cursor: 'cur-page-3' , total: 0}),
      );
      component.loadMore();
      fixture.detectChanges();
      expect(component.pendingRequests().length).toBe(2);

      // Now approve req-single
      requestsApi.approveRequest.and.returnValue(of(page1Item));
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [page2Item], next_cursor: null , total: 0}),
      );

      component.submitDecision('req-single', 'approve');
      fixture.detectChanges();

      // Reloaded page 1: extra pages and old cursor are cleared
      expect(component.pendingRequests().length).toBe(1);
      expect(component.nextCursor()).toBeNull();
    });

    it('group with size 2 but only one request in page: disabled, fetches missing sibling, enables when resolved, includes sibling in detail and totals', () => {
      const partialGroupReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-split-1',
        estimated_total: { amount: '1000.00', currency: 'SAR' },
        lines: [
          {
            id: 'line-s1',
            workspace_product_id: 'prod-gloves',
            quantity: '10',
            estimated_unit_price: { amount: '100.00', currency: 'SAR' },
            note: 'First split',
            quoted_prices_include_vat: false,
            quoted_vat_rate: null,
            quoted_net_unit_price: null,
          },
        ],
        source: {
          rfq_id: 'rfq-split-1',
          rfq_response_id: 'resp-1',
          quotation_id: 'q-1',
          supplier_id: 'sup-1',
          supplier_name: 'Supplier A',
        },
        request_group: {
          id: 'grp-split-1',
          rfq_id: 'rfq-split-1',
          position: 1,
          size: 2,
          combined_total: { amount: '2500.00', currency: 'SAR' },
          saving: { amount: '500.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-1', 'req-split-2'],
        },
      };

      const siblingReq2: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-split-2',
        estimated_total: { amount: '1500.00', currency: 'SAR' },
        lines: [
          {
            id: 'line-s2',
            workspace_product_id: 'prod-masks',
            quantity: '50',
            estimated_unit_price: { amount: '30.00', currency: 'SAR' },
            note: 'Second split',
            quoted_prices_include_vat: false,
            quoted_vat_rate: null,
            quoted_net_unit_price: null,
          },
        ],
        source: {
          rfq_id: 'rfq-split-1',
          rfq_response_id: 'resp-2',
          quotation_id: 'q-2',
          supplier_id: 'sup-2',
          supplier_name: 'Supplier B',
        },
        request_group: {
          id: 'grp-split-1',
          rfq_id: 'rfq-split-1',
          position: 2,
          size: 2,
          combined_total: { amount: '2500.00', currency: 'SAR' },
          saving: { amount: '500.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-1', 'req-split-2'],
        },
      };

      const siblingSubject = new Subject<PurchaseRequest>();
      requestsApi.getRequest.and.returnValue(siblingSubject);

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [partialGroupReq1], next_cursor: null , total: 0}),
      );

      component.loadPendingApprovals();
      fixture.detectChanges();

      // getRequest was called for the missing sibling id
      expect(requestsApi.getRequest).toHaveBeenCalledWith('req-split-2');

      // Row's Approve and Reject buttons are disabled
      const approveBtn = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtn = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtn.disabled).toBeTrue();
      expect(rejectBtn.disabled).toBeTrue();

      // Row shows loading hint
      const loadingHint = fixture.nativeElement.querySelector('[data-testid="split-group-loading"]');
      expect(loadingHint).toBeTruthy();
      expect(loadingHint.textContent).toContain('Loading the rest of this split');

      // Now resolve sibling fetch
      siblingSubject.next(siblingReq2);
      siblingSubject.complete();
      fixture.detectChanges();

      // Enabled after resolve
      const approveBtnAfter = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtnAfter = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtnAfter.disabled).toBeFalse();
      expect(rejectBtnAfter.disabled).toBeFalse();
      expect(fixture.nativeElement.querySelector('[data-testid="split-group-loading"]')).toBeNull();

      // Totals / expanded detail include sibling
      const groupItem = component.queueItems()[0];
      expect(groupItem.kind).toBe('group');
      if (groupItem.kind === 'group') {
        expect(groupItem.requests.length).toBe(2);
        expect(groupItem.linesCount).toBe(2);
      }

      // Expand group row
      component.toggleExpand('grp-split-1');
      fixture.detectChanges();

      const expandedText = fixture.nativeElement.textContent;
      expect(expandedText).toContain('Supplier A');
      expect(expandedText).toContain('Supplier B');
      expect(expandedText).toContain('SAR 1,000');
      expect(expandedText).toContain('SAR 1,500');
    });

    it('group with size 2: failing sibling fetch keeps buttons disabled and shows retry', () => {
      const partialGroupReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-split-1',
        request_group: {
          id: 'grp-split-1',
          rfq_id: 'rfq-split-1',
          position: 1,
          size: 2,
          combined_total: { amount: '2500.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-1', 'req-split-2'],
        },
      };

      requestsApi.getRequest.and.returnValue(throwError(() => new Error('Fetch failed')));

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [partialGroupReq1], next_cursor: null , total: 0}),
      );

      component.loadPendingApprovals();
      fixture.detectChanges();

      const approveBtn = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtn = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtn.disabled).toBeTrue();
      expect(rejectBtn.disabled).toBeTrue();

      // Error hint and retry button visible
      const errorHint = fixture.nativeElement.querySelector('[data-testid="split-group-error"]');
      expect(errorHint).toBeTruthy();
      expect(errorHint.textContent).toContain('Failed to load the rest of this split');

      const retryBtn = fixture.nativeElement.querySelector('[data-testid="split-group-retry"]') as HTMLButtonElement;
      expect(retryBtn).toBeTruthy();

      // Click retry
      requestsApi.getRequest.calls.reset();
      requestsApi.getRequest.and.returnValue(of({
        ...partialGroupReq1,
        id: 'req-split-2',
      }));

      retryBtn.click();
      fixture.detectChanges();

      expect(requestsApi.getRequest).toHaveBeenCalledWith('req-split-2');
      const approveBtnAfter = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtnAfter = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtnAfter.disabled).toBeFalse();
      expect(rejectBtnAfter.disabled).toBeFalse();
    });

    it('failed sibling fetch: then loadMore returns the sibling: banner and Retry gone, buttons enabled; and Retry with everything known clears the failure', () => {
      const splitReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-split-f1',
        request_group: {
          id: 'grp-split-f1',
          rfq_id: 'rfq-split-f1',
          position: 1,
          size: 2,
          combined_total: { amount: '2500.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-f1', 'req-split-f2'],
        },
      };
      const splitReq2: PurchaseRequest = {
        ...mockPendingRequests[1],
        id: 'req-split-f2',
        request_group: {
          id: 'grp-split-f1',
          rfq_id: 'rfq-split-f1',
          position: 2,
          size: 2,
          combined_total: { amount: '2500.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-f1', 'req-split-f2'],
        },
      };

      // Initial load: page 1 has splitReq1 only, with next_cursor available.
      // Sibling fetch fails.
      requestsApi.getRequest.and.returnValue(throwError(() => new Error('Fetch failed')));
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [splitReq1], next_cursor: 'cursor-page-2' , total: 0}),
      );

      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(component.groupStatus().get('grp-split-f1')).toBe('failed');
      const approveBtn = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtn = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtn.disabled).toBeTrue();
      expect(rejectBtn.disabled).toBeTrue();

      let errorHint = fixture.nativeElement.querySelector('[data-testid="split-group-error"]');
      let retryBtn = fixture.nativeElement.querySelector('[data-testid="split-group-retry"]');
      expect(errorHint).toBeTruthy();
      expect(retryBtn).toBeTruthy();

      // User clicks Load more: next page brings in splitReq2!
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [splitReq2], next_cursor: null , total: 0}),
      );
      const loadMoreBtn = fixture.nativeElement.querySelector('[data-testid="load-more-btn"]');
      loadMoreBtn.click();
      fixture.detectChanges();

      // Banner and Retry gone, buttons enabled, status marked complete
      errorHint = fixture.nativeElement.querySelector('[data-testid="split-group-error"]');
      retryBtn = fixture.nativeElement.querySelector('[data-testid="split-group-retry"]');
      expect(errorHint).toBeNull();
      expect(retryBtn).toBeNull();

      const approveBtnAfter = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtnAfter = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtnAfter.disabled).toBeFalse();
      expect(rejectBtnAfter.disabled).toBeFalse();
      expect(component.groupStatus().get('grp-split-f1')).toBe('complete');

      // Now verify: Retry with everything known clears the failure
      component.groupStatus.set(new Map([['grp-split-f1', 'failed']]));
      fixture.detectChanges();
      errorHint = fixture.nativeElement.querySelector('[data-testid="split-group-error"]');
      expect(errorHint).toBeTruthy();

      const groupItem = component.queueItems().find((i) => i.id === 'grp-split-f1');
      expect(groupItem).toBeTruthy();
      component.retryLoadGroup(groupItem as GroupQueueItem);
      fixture.detectChanges();

      expect(component.groupStatus().get('grp-split-f1')).toBe('complete');
      errorHint = fixture.nativeElement.querySelector('[data-testid="split-group-error"]');
      expect(errorHint).toBeNull();
    });

    it('group with size 2: sibling whose group id differs is rejected as invalid', () => {
      const partialGroupReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-split-1',
        request_group: {
          id: 'grp-split-1',
          rfq_id: 'rfq-split-1',
          position: 1,
          size: 2,
          combined_total: { amount: '2500.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-1', 'req-split-2'],
        },
      };

      const invalidSiblingReq2: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-split-2',
        request_group: {
          id: 'grp-DIFFERENT',
          rfq_id: 'rfq-split-1',
          position: 2,
          size: 2,
          combined_total: { amount: '2500.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-1', 'req-split-2'],
        },
      };

      requestsApi.getRequest.and.returnValue(of(invalidSiblingReq2));

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [partialGroupReq1], next_cursor: null , total: 0}),
      );

      component.loadPendingApprovals();
      fixture.detectChanges();

      // Buttons stay disabled
      const approveBtn = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtn = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtn.disabled).toBeTrue();
      expect(rejectBtn.disabled).toBeTrue();

      // Shows error and retry
      const errorHint = fixture.nativeElement.querySelector('[data-testid="split-group-error"]');
      expect(errorHint).toBeTruthy();
    });

    it('a complete group on one page is enabled immediately without extra calls', () => {
      requestsApi.getRequest.calls.reset();

      const completeGroupReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-c-1',
        request_group: {
          id: 'grp-complete',
          rfq_id: 'rfq-c',
          position: 1,
          size: 2,
          combined_total: { amount: '2000.00', currency: 'SAR' },
          sibling_request_ids: ['req-c-1', 'req-c-2'],
        },
      };
      const completeGroupReq2: PurchaseRequest = {
        ...mockPendingRequests[1],
        id: 'req-c-2',
        request_group: {
          id: 'grp-complete',
          rfq_id: 'rfq-c',
          position: 2,
          size: 2,
          combined_total: { amount: '2000.00', currency: 'SAR' },
          sibling_request_ids: ['req-c-1', 'req-c-2'],
        },
      };

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [completeGroupReq1, completeGroupReq2], next_cursor: null , total: 0}),
      );

      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(requestsApi.getRequest).not.toHaveBeenCalled();

      const approveBtn = fixture.nativeElement.querySelector('.approve-btn') as HTMLButtonElement;
      const rejectBtn = fixture.nativeElement.querySelector('.reject-btn') as HTMLButtonElement;
      expect(approveBtn.disabled).toBeFalse();
      expect(rejectBtn.disabled).toBeFalse();
      expect(fixture.nativeElement.querySelector('[data-testid="split-group-loading"]')).toBeNull();
      expect(fixture.nativeElement.querySelector('[data-testid="split-group-error"]')).toBeNull();
    });

    it('stale responses: sibling fetch result is ignored if loadPendingApprovals reloaded while fetch was pending', () => {
      const partialGroupReq: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-split-gen1',
        request_group: {
          id: 'grp-gen',
          rfq_id: 'rfq-gen',
          position: 1,
          size: 2,
          combined_total: { amount: '2000.00', currency: 'SAR' },
          sibling_request_ids: ['req-split-gen1', 'req-split-gen2'],
        },
      };

      const pendingSiblingSubject = new Subject<PurchaseRequest>();
      requestsApi.getRequest.and.returnValue(pendingSiblingSubject);

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [partialGroupReq], next_cursor: null , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(requestsApi.getRequest).toHaveBeenCalledWith('req-split-gen2');
      expect(component.groupStatus().get('grp-gen')).toBe('loading');

      // Reload while fetch is pending
      const freshReq: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-fresh-1',
        request_group: null,
      };
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [freshReq], next_cursor: null , total: 0}),
      );
      component.loadPendingApprovals();
      fixture.detectChanges();

      // State is reset for new load
      expect(component.groupSiblings().has('grp-gen')).toBeFalse();

      // Old fetch resolves now (late response)
      pendingSiblingSubject.next({
        ...partialGroupReq,
        id: 'req-split-gen2',
      });
      pendingSiblingSubject.complete();
      fixture.detectChanges();

      // Old late response must be ignored
      expect(component.groupSiblings().has('grp-gen')).toBeFalse();
      expect(component.groupStatus().get('grp-gen')).toBeUndefined();
    });

    it('split-group completeness does not overwrite loading status for pending sibling fetch when complete group is loaded first', () => {
      requestsApi.getRequest.calls.reset();

      const completeReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-c-1',
        request_group: {
          id: 'grp-complete',
          rfq_id: 'rfq-c',
          position: 1,
          size: 2,
          combined_total: { amount: '2000.00', currency: 'SAR' },
          sibling_request_ids: ['req-c-1', 'req-c-2'],
        },
      };
      const completeReq2: PurchaseRequest = {
        ...mockPendingRequests[1],
        id: 'req-c-2',
        request_group: {
          id: 'grp-complete',
          rfq_id: 'rfq-c',
          position: 2,
          size: 2,
          combined_total: { amount: '2000.00', currency: 'SAR' },
          sibling_request_ids: ['req-c-1', 'req-c-2'],
        },
      };
      const incompleteReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-inc-1',
        request_group: {
          id: 'grp-incomplete',
          rfq_id: 'rfq-inc',
          position: 1,
          size: 2,
          combined_total: { amount: '1500.00', currency: 'SAR' },
          sibling_request_ids: ['req-inc-1', 'req-inc-2'],
        },
      };
      const siblingReq2: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-inc-2',
        request_group: {
          id: 'grp-incomplete',
          rfq_id: 'rfq-inc',
          position: 2,
          size: 2,
          combined_total: { amount: '1500.00', currency: 'SAR' },
          sibling_request_ids: ['req-inc-1', 'req-inc-2'],
        },
      };

      const siblingSubject = new Subject<PurchaseRequest>();
      requestsApi.getRequest.and.returnValue(siblingSubject);

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [completeReq1, completeReq2, incompleteReq1], next_cursor: 'cur-page2' , total: 0}),
      );

      component.loadPendingApprovals();
      fixture.detectChanges();

      const rows = fixture.nativeElement.querySelectorAll('tr.request-row');
      expect(rows.length).toBe(2);

      const completeRow = rows[0];
      const completeApproveBtn = completeRow.querySelector('.approve-btn') as HTMLButtonElement;
      const completeRejectBtn = completeRow.querySelector('.reject-btn') as HTMLButtonElement;
      expect(completeApproveBtn.disabled).toBeFalse();
      expect(completeRejectBtn.disabled).toBeFalse();
      expect(completeRow.querySelector('[data-testid="split-group-loading"]')).toBeNull();

      const incompleteRow = rows[1];
      const incApproveBtn = incompleteRow.querySelector('.approve-btn') as HTMLButtonElement;
      const incRejectBtn = incompleteRow.querySelector('.reject-btn') as HTMLButtonElement;
      expect(incApproveBtn.disabled).toBeTrue();
      expect(incRejectBtn.disabled).toBeTrue();
      const loadingHint = incompleteRow.querySelector('[data-testid="split-group-loading"]');
      expect(loadingHint).not.toBeNull();
      expect(component.groupStatus().get('grp-incomplete')).toBe('loading');

      expect(requestsApi.getRequest).toHaveBeenCalledTimes(1);
      expect(requestsApi.getRequest).toHaveBeenCalledWith('req-inc-2');

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [], next_cursor: null , total: 0}),
      );
      component.loadMore();
      fixture.detectChanges();

      expect(requestsApi.getRequest).toHaveBeenCalledTimes(1);

      siblingSubject.next(siblingReq2);
      siblingSubject.complete();
      fixture.detectChanges();

      expect(component.groupStatus().get('grp-incomplete')).toBe('complete');
      const updatedRows = fixture.nativeElement.querySelectorAll('tr.request-row');
      const updatedIncompleteRow = updatedRows[1];
      const updatedIncApproveBtn = updatedIncompleteRow.querySelector('.approve-btn') as HTMLButtonElement;
      const updatedIncRejectBtn = updatedIncompleteRow.querySelector('.reject-btn') as HTMLButtonElement;
      expect(updatedIncApproveBtn.disabled).toBeFalse();
      expect(updatedIncRejectBtn.disabled).toBeFalse();
      expect(fixture.nativeElement.querySelector('[data-testid="split-group-loading"]')).toBeNull();
    });

    it('split-group completeness does not overwrite loading status for pending sibling fetch when incomplete group is loaded first', () => {
      requestsApi.getRequest.calls.reset();

      const incompleteReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-inc-1',
        request_group: {
          id: 'grp-incomplete',
          rfq_id: 'rfq-inc',
          position: 1,
          size: 2,
          combined_total: { amount: '1500.00', currency: 'SAR' },
          sibling_request_ids: ['req-inc-1', 'req-inc-2'],
        },
      };
      const completeReq1: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-c-1',
        request_group: {
          id: 'grp-complete',
          rfq_id: 'rfq-c',
          position: 1,
          size: 2,
          combined_total: { amount: '2000.00', currency: 'SAR' },
          sibling_request_ids: ['req-c-1', 'req-c-2'],
        },
      };
      const completeReq2: PurchaseRequest = {
        ...mockPendingRequests[1],
        id: 'req-c-2',
        request_group: {
          id: 'grp-complete',
          rfq_id: 'rfq-c',
          position: 2,
          size: 2,
          combined_total: { amount: '2000.00', currency: 'SAR' },
          sibling_request_ids: ['req-c-1', 'req-c-2'],
        },
      };
      const siblingReq2: PurchaseRequest = {
        ...mockPendingRequests[0],
        id: 'req-inc-2',
        request_group: {
          id: 'grp-incomplete',
          rfq_id: 'rfq-inc',
          position: 2,
          size: 2,
          combined_total: { amount: '1500.00', currency: 'SAR' },
          sibling_request_ids: ['req-inc-1', 'req-inc-2'],
        },
      };

      const siblingSubject = new Subject<PurchaseRequest>();
      requestsApi.getRequest.and.returnValue(siblingSubject);

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [incompleteReq1, completeReq1, completeReq2], next_cursor: 'cur-page2' , total: 0}),
      );

      component.loadPendingApprovals();
      fixture.detectChanges();

      const rows = fixture.nativeElement.querySelectorAll('tr.request-row');
      expect(rows.length).toBe(2);

      const incompleteRow = rows[0];
      const incApproveBtn = incompleteRow.querySelector('.approve-btn') as HTMLButtonElement;
      const incRejectBtn = incompleteRow.querySelector('.reject-btn') as HTMLButtonElement;
      expect(incApproveBtn.disabled).toBeTrue();
      expect(incRejectBtn.disabled).toBeTrue();
      const loadingHint = incompleteRow.querySelector('[data-testid="split-group-loading"]');
      expect(loadingHint).not.toBeNull();
      expect(component.groupStatus().get('grp-incomplete')).toBe('loading');

      const completeRow = rows[1];
      const completeApproveBtn = completeRow.querySelector('.approve-btn') as HTMLButtonElement;
      const completeRejectBtn = completeRow.querySelector('.reject-btn') as HTMLButtonElement;
      expect(completeApproveBtn.disabled).toBeFalse();
      expect(completeRejectBtn.disabled).toBeFalse();
      expect(completeRow.querySelector('[data-testid="split-group-loading"]')).toBeNull();

      expect(requestsApi.getRequest).toHaveBeenCalledTimes(1);
      expect(requestsApi.getRequest).toHaveBeenCalledWith('req-inc-2');

      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: [], next_cursor: null , total: 0}),
      );
      component.loadMore();
      fixture.detectChanges();

      expect(requestsApi.getRequest).toHaveBeenCalledTimes(1);

      siblingSubject.next(siblingReq2);
      siblingSubject.complete();
      fixture.detectChanges();

      expect(component.groupStatus().get('grp-incomplete')).toBe('complete');
      const updatedRows = fixture.nativeElement.querySelectorAll('tr.request-row');
      const updatedIncompleteRow = updatedRows[0];
      const updatedIncApproveBtn = updatedIncompleteRow.querySelector('.approve-btn') as HTMLButtonElement;
      const updatedIncRejectBtn = updatedIncompleteRow.querySelector('.reject-btn') as HTMLButtonElement;
      expect(updatedIncApproveBtn.disabled).toBeFalse();
      expect(updatedIncRejectBtn.disabled).toBeFalse();
      expect(fixture.nativeElement.querySelector('[data-testid="split-group-loading"]')).toBeNull();
    });

    it('renders cleanly in RTL direction', () => {
      approvalsApi.listPendingApprovals.and.returnValue(
        of({ items: mockPendingRequests, next_cursor: 'cur-ar' , total: 0}),
      );
      component.loadPendingApprovals();

      document.documentElement.setAttribute('dir', 'rtl');
      const translate = TestBed.inject(TranslateService);
      translate.use('ar');
      fixture.detectChanges();

      const container = fixture.nativeElement.querySelector('.approval-queue-container');
      expect(container).not.toBeNull();
      const statusEl = fixture.nativeElement.querySelector('[data-testid="pagination-status"]');
      expect(statusEl?.textContent).toContain('عرض طلبين، ويتوفر المزيد');

      document.documentElement.setAttribute('dir', 'ltr');
      translate.use('en');
      fixture.detectChanges();
    });
  });

  describe('P-177 (PPS-171) queue sort, branch filter and result count', () => {
    const list = (
      items: readonly PurchaseRequest[],
      next_cursor: string | null = null,
      total = items.length,
    ): PendingApprovalList => ({ items, next_cursor, total });

    describe('initial URL state', () => {
      beforeEach(async () => {
        TestBed.resetTestingModule();
        approvalsApi.listPendingApprovals.calls.reset();
        organisationApi.listBranches.calls.reset();
        routerSpy.navigate.calls.reset();
        await configureQueue({ sort: 'required_by_asc', branch: 'branch-north' });
      });

      it('restores a valid sort and branch from the URL and loads with them', () => {
        expect(component.sortOption()).toBe('required_by_asc');
        expect(component.branchFilter()).toBe('branch-north');
        expect(approvalsApi.listPendingApprovals).toHaveBeenCalledWith({
          sort: 'required_by_asc',
          branch_id: 'branch-north',
          limit: 50,
        });
      });
    });

    describe('invalid URL state', () => {
      beforeEach(async () => {
        TestBed.resetTestingModule();
        approvalsApi.listPendingApprovals.calls.reset();
        organisationApi.listBranches.calls.reset();
        routerSpy.navigate.calls.reset();
        await configureQueue({ sort: 'bogus', branch: 'branch-unknown' });
      });

      it('falls back to the default sort silently and drops an unknown branch', () => {
        expect(component.sortOption()).toBe('submitted_desc');
        expect(component.branchFilter()).toBe('');
        const last = approvalsApi.listPendingApprovals.calls.mostRecent().args[0];
        expect(last?.sort).toBeUndefined();
        expect(last?.branch_id).toBeUndefined();
        expect(routerSpy.navigate).toHaveBeenCalledWith([], {
          queryParams: { sort: null, branch: null },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      });
    });

    it('changing sort resets rows, cursor and groups, writes the URL and reloads without a cursor', () => {
      component.pendingRequests.set([...mockPendingRequests]);
      component.nextCursor.set('old-cursor');
      component.groupSiblings.set(new Map([['grp', [...mockPendingRequests]]]));
      component.groupStatus.set(new Map([['grp', 'complete']]));
      approvalsApi.listPendingApprovals.calls.reset();
      approvalsApi.listPendingApprovals.and.returnValue(new Subject<PendingApprovalList>());

      component.onSortChange('submitted_asc');

      expect(component.pendingRequests()).toEqual([]);
      expect(component.nextCursor()).toBeNull();
      expect(component.groupSiblings().size).toBe(0);
      expect(component.groupStatus().size).toBe(0);
      const params = approvalsApi.listPendingApprovals.calls.mostRecent().args[0];
      expect(params?.sort).toBe('submitted_asc');
      expect(params?.cursor).toBeUndefined();
      expect(routerSpy.navigate).toHaveBeenCalledWith([], {
        queryParams: { sort: 'submitted_asc', branch: null },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
    });

    it('changing branch resets and reloads page 1 with the branch and current sort', () => {
      component.sortOption.set('total_desc');
      approvalsApi.listPendingApprovals.calls.reset();
      approvalsApi.listPendingApprovals.and.returnValue(new Subject<PendingApprovalList>());

      component.onBranchChange('branch-south');

      expect(component.branchFilter()).toBe('branch-south');
      expect(approvalsApi.listPendingApprovals.calls.mostRecent().args[0]).toEqual({
        sort: 'total_desc',
        branch_id: 'branch-south',
        limit: 50,
      });
      expect(routerSpy.navigate).toHaveBeenCalledWith([], {
        queryParams: { sort: 'total_desc', branch: 'branch-south' },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
    });

    it('Load more sends the same sort and branch with the cursor', () => {
      component.sortOption.set('required_by_asc');
      component.branchFilter.set('branch-north');
      component.nextCursor.set('cursor-2');
      approvalsApi.listPendingApprovals.calls.reset();
      approvalsApi.listPendingApprovals.and.returnValue(of(list([], null, 120)));

      component.loadMore();

      expect(approvalsApi.listPendingApprovals).toHaveBeenCalledWith({
        sort: 'required_by_asc',
        branch_id: 'branch-north',
        cursor: 'cursor-2',
        limit: 50,
      });
    });

    it('ignores a late response from the previous query after a sort change', () => {
      const first = new Subject<PendingApprovalList>();
      approvalsApi.listPendingApprovals.and.returnValue(first);
      component.onSortChange('submitted_asc');

      const second = new Subject<PendingApprovalList>();
      approvalsApi.listPendingApprovals.and.returnValue(second);
      component.onSortChange('total_desc');

      second.next(list([mockPendingRequests[1]], null, 1));
      second.complete();
      fixture.detectChanges();
      expect(component.pendingRequests().map((r) => r.id)).toEqual(['req-002']);
      expect(component.totalCount()).toBe(1);

      first.next(list([mockPendingRequests[0]], null, 99));
      first.complete();
      fixture.detectChanges();
      expect(component.pendingRequests().map((r) => r.id)).toEqual(['req-002']);
      expect(component.totalCount()).toBe(1);
    });

    it('Clear resets sort and branch, removes the chips and writes defaults out of the URL', () => {
      component.onSortChange('submitted_asc');
      component.onBranchChange('branch-north');
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelectorAll('.filter-chip').length).toBe(2);

      const clear = fixture.nativeElement.querySelector(
        '[data-testid="clear-filters-btn"]',
      ) as HTMLButtonElement;
      expect(clear).toBeTruthy();
      clear.click();
      fixture.detectChanges();

      expect(component.sortOption()).toBe('submitted_desc');
      expect(component.branchFilter()).toBe('');
      expect(fixture.nativeElement.querySelectorAll('.filter-chip').length).toBe(0);
      expect(routerSpy.navigate).toHaveBeenCalledWith([], {
        queryParams: { sort: null, branch: null },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
    });

    it('renders a chip per active filter whose remove button names what it removes', () => {
      component.onSortChange('required_by_asc');
      component.onBranchChange('branch-north');
      fixture.detectChanges();

      const chips = Array.from(
        fixture.nativeElement.querySelectorAll('.filter-chip'),
      ) as HTMLElement[];
      expect(chips.length).toBe(2);
      const buttons = chips.map(
        (chip) => chip.querySelector('.chip-remove') as HTMLButtonElement,
      );
      expect(buttons[0].getAttribute('aria-label')).toContain('Required by (soonest)');
      expect(buttons[1].getAttribute('aria-label')).toContain('North Branch');

      buttons[1].click();
      fixture.detectChanges();
      expect(component.branchFilter()).toBe('');
      expect(component.sortOption()).toBe('required_by_asc');
      expect(fixture.nativeElement.querySelectorAll('.filter-chip').length).toBe(1);

      const remainingRemove = fixture.nativeElement.querySelector(
        '.chip-remove',
      ) as HTMLButtonElement;
      remainingRemove.click();
      fixture.detectChanges();
      expect(component.sortOption()).toBe('submitted_desc');
      expect(fixture.nativeElement.querySelectorAll('.filter-chip').length).toBe(0);
    });

    it('formats the pending decision count for singular, plural and zero in English', () => {
      component.totalCount.set(1);
      expect(component.totalCountLabel()).toBe('1 pending decision');
      component.totalCount.set(12);
      expect(component.totalCountLabel()).toBe('12 pending decisions');
      component.totalCount.set(0);
      expect(component.totalCountLabel()).toBe('0 pending decisions');
    });

    it('uses the real Arabic catalogue and Latin digits for the count and sort labels', () => {
      const translate = TestBed.inject(TranslateService);
      translate.use('ar');

      component.totalCount.set(1);
      expect(component.totalCountLabel()).toBe('قرار معلق واحد');
      component.totalCount.set(2);
      expect(component.totalCountLabel()).toBe('قراران معلقان');
      component.totalCount.set(3);
      expect(component.totalCountLabel()).toBe('3 قرارات معلقة');
      component.totalCount.set(12);
      expect(component.totalCountLabel()).toBe('12 قرارًا معلقًا');
      component.totalCount.set(0);
      expect(component.totalCountLabel()).toBe('لا توجد قرارات معلقة');
      expect(component.sortOptionLabel('submitted_asc')).toBe('الأقدم أولاً');
    });

    it('shows the total under the title and loaded-vs-total in the pagination status', () => {
      approvalsApi.listPendingApprovals.and.returnValue(of(list(mockPendingRequests, null, 120)));
      component.loadPendingApprovals();
      fixture.detectChanges();

      const count = fixture.nativeElement.querySelector('[data-testid="approval-total-count"]');
      expect(count?.textContent?.trim()).toBe('120 pending decisions');
      const status = fixture.nativeElement.querySelector('[data-testid="pagination-status"]');
      expect(status?.textContent).toContain('Showing 2 of 120');
    });

    it('shows the default empty state with no filters and the filtered empty state with Clear when a filter is active', () => {
      approvalsApi.listPendingApprovals.and.returnValue(of(list([], null, 0)));
      component.loadPendingApprovals();
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('[data-testid="empty-default"]')).toBeTruthy();
      expect(fixture.nativeElement.querySelector('[data-testid="empty-filtered"]')).toBeNull();

      component.onSortChange('submitted_asc');
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('[data-testid="empty-default"]')).toBeNull();
      expect(
        fixture.nativeElement.querySelector('[data-testid="empty-filtered"]')?.textContent,
      ).toContain('No pending decisions match these filters.');
      expect(fixture.nativeElement.querySelector('[data-testid="clear-filters-btn"]')).toBeTruthy();
    });

    it('announces the sort and new count in a polite live region', () => {
      approvalsApi.listPendingApprovals.and.returnValue(of(list(mockPendingRequests, null, 12)));
      component.onSortChange('submitted_asc');
      fixture.detectChanges();

      const live = fixture.nativeElement.querySelector(
        '[data-testid="queue-announcement"]',
      ) as HTMLElement;
      expect(live.getAttribute('aria-live')).toBe('polite');
      expect(live.textContent).toContain('Sorted by Oldest first, 12 pending decisions');

      TestBed.inject(TranslateService).use('ar');
      fixture.detectChanges();
      expect(live.textContent).toContain('تم الترتيب حسب الأقدم أولاً، 12 قرارًا معلقًا');
    });

    it('reloads page 1 with the current sort and branch after a decision', () => {
      component.sortOption.set('total_asc');
      component.branchFilter.set('branch-south');
      requestsApi.approveRequest.and.returnValue(
        of({ ...mockPendingRequests[0], status: 'approved' } as PurchaseRequest),
      );
      approvalsApi.listPendingApprovals.calls.reset();
      approvalsApi.listPendingApprovals.and.returnValue(of(list([], null, 0)));

      component.submitDecision('req-001', 'approve');

      expect(approvalsApi.listPendingApprovals).toHaveBeenCalledWith({
        sort: 'total_asc',
        branch_id: 'branch-south',
        limit: 50,
      });
    });

    it('updates controls and reloads when the URL changes (back/forward)', () => {
      approvalsApi.listPendingApprovals.calls.reset();
      queryParamMapSubject.next(
        convertToParamMap({ sort: 'total_asc', branch: 'branch-south' }),
      );
      fixture.detectChanges();

      expect(component.sortOption()).toBe('total_asc');
      expect(component.branchFilter()).toBe('branch-south');
      expect(approvalsApi.listPendingApprovals.calls.mostRecent().args[0]).toEqual({
        sort: 'total_asc',
        branch_id: 'branch-south',
        limit: 50,
      });
    });

    it('does not write the default sort to the URL', () => {
      component.onSortChange('submitted_asc');
      routerSpy.navigate.calls.reset();

      component.onSortChange('submitted_desc');

      expect(routerSpy.navigate).toHaveBeenCalledWith([], {
        queryParams: { sort: null, branch: null },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });
    });
  });
});

describe('Approvals API P-177 params', () => {
  let approvalsApiService: ApprovalsApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        ApiService,
        ApprovalsApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    approvalsApiService = TestBed.inject(ApprovalsApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('sends sort and branch_id only when set and returns total', () => {
    approvalsApiService
      .listPendingApprovals({
        sort: 'required_by_asc',
        branch_id: 'branch-north',
        cursor: 'c1',
        limit: 50,
      })
      .subscribe((res) => expect(res.total).toBe(0));

    const req = httpMock.expectOne((r) => r.url.startsWith('/api/v1/approvals/pending'));
    expect(req.request.url).toBe(
      '/api/v1/approvals/pending?sort=required_by_asc&branch_id=branch-north&cursor=c1&limit=50',
    );
    req.flush({ items: [], next_cursor: null, total: 0 });

    approvalsApiService.listPendingApprovals({ limit: 50 }).subscribe();
    const plain = httpMock.expectOne('/api/v1/approvals/pending?limit=50');
    plain.flush({ items: [], next_cursor: null, total: 0 });
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

  it('disables confirm button on reject when comment is empty, and enables when provided', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ApprovalDecisionDialogComponent],
      providers: [
        provideTranslateService(),
        {
          provide: MAT_DIALOG_DATA,
          useValue: { action: 'reject', requestId: 'req-001' },
        },
        {
          provide: MatDialogRef,
          useValue: jasmine.createSpyObj('MatDialogRef', ['close']),
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');

    dialogFixture = TestBed.createComponent(ApprovalDecisionDialogComponent);
    dialogFixture.detectChanges();

    const confirmBtn = dialogFixture.nativeElement.querySelector('.confirm-btn') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBeTrue();

    dialogFixture.componentInstance.comment = 'Price too high';
    dialogFixture.detectChanges();
    expect(confirmBtn.disabled).toBeFalse();
  });
});
