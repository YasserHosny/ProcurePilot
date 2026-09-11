import { HttpErrorResponse } from '@angular/common/http';
import { signal, WritableSignal } from '@angular/core';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type {
  ApprovalDelegation,
  Member,
  Me,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ApprovalsApiService } from '../../approvals/approvals-api';
import { DelegationListComponent } from './delegation-list.component';

const mockDelegations: ApprovalDelegation[] = [
  {
    id: 'dlg-1',
    delegator_membership_id: 'm1',
    delegate_membership_id: 'm2',
    starts_on: '2026-09-01',
    ends_on: '2026-09-07',
    created_at: '2026-08-20T10:00:00Z',
  },
  {
    id: 'dlg-2',
    delegator_membership_id: 'm1',
    delegate_membership_id: 'm3',
    starts_on: '2026-10-01',
    ends_on: '2026-10-15',
    created_at: '2026-08-21T10:00:00Z',
  },
];

const mockMembers: Member[] = [
  {
    id: 'm1',
    email: 'approver1@example.com',
    role: 'approver',
    status: 'active',
    mfa_enabled: false,
    created_at: '2026-08-01T09:00:00Z',
  },
  {
    id: 'm2',
    email: 'approver2@example.com',
    role: 'approver',
    status: 'active',
    mfa_enabled: false,
    created_at: '2026-08-02T09:00:00Z',
  },
  {
    id: 'm3',
    email: 'approver3@example.com',
    role: 'approver',
    status: 'active',
    mfa_enabled: false,
    created_at: '2026-08-03T09:00:00Z',
  },
];

const mockMe: Me = {
  id: 'm1',
  email: 'approver1@example.com',
  role: 'approver',
  preferred_locale: 'en',
  mfa_enabled: false,
  tenant: {
    id: 't1',
    name: 'Acme',
    slug: 'acme',
    region: 'GB',
    currency: 'USD',
    tax_model: 'vat',
    default_locale: 'en',
    created_at: '2026-08-01T09:00:00Z',
  },
};

describe('DelegationListComponent', () => {
  let component: DelegationListComponent;
  let fixture: ComponentFixture<DelegationListComponent>;
  let approvalsApi: jasmine.SpyObj<ApprovalsApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let mockDialogRef: jasmine.SpyObj<MatDialogRef<unknown>>;
  let sessionMock: {
    currentMember: WritableSignal<Me | null>;
    hasRole: jasmine.Spy;
    role: unknown;
    tenant: unknown;
    isAuthenticated: unknown;
    activeLocale: unknown;
  };

  beforeEach(async () => {
    approvalsApi = jasmine.createSpyObj('ApprovalsApiService', [
      'listApprovalDelegations',
      'createApprovalDelegation',
      'cancelApprovalDelegation',
    ]);
    api = jasmine.createSpyObj('ApiService', ['members']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    mockDialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);

    dialogSpy.open.and.returnValue(mockDialogRef);

    sessionMock = {
      currentMember: signal<Me | null>(mockMe),
      hasRole: jasmine.createSpy('hasRole').and.returnValue(false),
      role: signal('approver'),
      tenant: signal(mockMe.tenant),
      isAuthenticated: signal(true),
      activeLocale: signal('en'),
    };

    approvalsApi.listApprovalDelegations.and.returnValue(
      of({ items: mockDelegations }),
    );
    approvalsApi.createApprovalDelegation.and.returnValue(of(mockDelegations[0]));
    approvalsApi.cancelApprovalDelegation.and.returnValue(of(void 0));
    api.members.and.returnValue(
      of({ items: mockMembers, next_cursor: null }),
    );

    await TestBed.configureTestingModule({
      imports: [DelegationListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApprovalsApiService, useValue: approvalsApi },
        { provide: ApiService, useValue: api },
        { provide: SessionService, useValue: sessionMock },
      ],
    })
      .overrideComponent(DelegationListComponent, {
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

    fixture = TestBed.createComponent(DelegationListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load approval delegations on init for the current member', () => {
    expect(approvalsApi.listApprovalDelegations).toHaveBeenCalledWith({
      membership_id: 'm1',
    });
    expect(component.delegations().length).toBe(2);
    expect(component.delegations()[0].delegate_membership_id).toBe('m2');
    expect(component.isLoading()).toBeFalse();
  });

  it('should show the empty state when no delegations exist', () => {
    approvalsApi.listApprovalDelegations.and.returnValue(of({ items: [] }));
    component.loadDelegations();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.empty-state')).toBeTruthy();
    expect(compiled.querySelector('.delegations-table')).toBeNull();
  });

  it('should render delegate email when known, and fall back to membership id', () => {
    expect(component.delegateLabel(mockDelegations[0])).toBe('approver2@example.com');
    const unknownDelegation: ApprovalDelegation = {
      ...mockDelegations[0],
      delegate_membership_id: 'unknown-id',
    };
    expect(component.delegateLabel(unknownDelegation)).toBe('unknown-id');
  });

  it('should exclude the current user from the delegate picker', () => {
    expect(component.availableMembers().length).toBe(2);
    expect(component.availableMembers().some((member) => member.id === 'm1')).toBeFalse();
  });

  it('should surface API errors with trace id on list load failure', () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'internal', message: 'Database failed', trace_id: 'dlg_err_1' },
    });
    approvalsApi.listApprovalDelegations.and.returnValue(throwError(() => error500));
    component.loadDelegations();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('Database failed');
    expect(component.errorTraceId()).toBe('dlg_err_1');

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.error-banner')).toBeTruthy();
    expect(compiled.textContent).toContain('dlg_err_1');
  });

  it('should validate form fields correctly', () => {
    component.openCreateDialog();

    expect(component.form.valid).toBeFalse();

    // All required fields
    expect(component.form.controls.delegate_membership_id.hasError('required')).toBeTrue();
    expect(component.form.controls.starts_on.hasError('required')).toBeTrue();
    expect(component.form.controls.ends_on.hasError('required')).toBeTrue();

    // Set delegate and start date
    component.form.controls.delegate_membership_id.setValue('m2');
    component.form.controls.starts_on.setValue('2026-09-10');

    // End date before start date
    component.form.controls.ends_on.setValue('2026-09-09');
    expect(component.form.hasError('endsOnBeforeStartsOn')).toBeTrue();

    // Fix end date
    component.form.controls.ends_on.setValue('2026-09-10');
    expect(component.form.hasError('endsOnBeforeStartsOn')).toBeFalse();
    expect(component.form.valid).toBeTrue();
  });

  it('should open create dialog and submit a new delegation without delegator_membership_id', () => {
    component.openCreateDialog();
    expect(dialogSpy.open).toHaveBeenCalledWith(component.delegationDialogTemplate, {
      width: '500px',
    });

    component.form.controls.delegate_membership_id.setValue('m2');
    component.form.controls.starts_on.setValue('2026-09-10');
    component.form.controls.ends_on.setValue('2026-09-20');

    approvalsApi.createApprovalDelegation.and.returnValue(of(mockDelegations[0]));

    component.saveDelegation();

    expect(approvalsApi.createApprovalDelegation).toHaveBeenCalledWith({
      delegate_membership_id: 'm2',
      starts_on: '2026-09-10',
      ends_on: '2026-09-20',
    });
    expect(mockDialogRef.close).toHaveBeenCalled();
    expect(approvalsApi.listApprovalDelegations).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Delegation created.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should surface dialog error when delegation creation fails', () => {
    component.openCreateDialog();
    component.form.controls.delegate_membership_id.setValue('m2');
    component.form.controls.starts_on.setValue('2026-09-10');
    component.form.controls.ends_on.setValue('2026-09-20');

    const error422 = new HttpErrorResponse({
      status: 422,
      error: { code: 'validation', message: 'Invalid delegation', trace_id: 'dlg_dlg_1' },
    });
    approvalsApi.createApprovalDelegation.and.returnValue(throwError(() => error422));

    component.saveDelegation();

    expect(component.isSubmitting()).toBeFalse();
    expect(component.dialogErrorMessage()).toBe('Invalid delegation');
    expect(component.dialogErrorTraceId()).toBe('dlg_dlg_1');
    expect(mockDialogRef.close).not.toHaveBeenCalled();
  });

  it('should block submit when ends_on is before starts_on', () => {
    component.openCreateDialog();
    component.form.controls.delegate_membership_id.setValue('m2');
    component.form.controls.starts_on.setValue('2026-09-10');
    component.form.controls.ends_on.setValue('2026-09-09');

    component.saveDelegation();

    expect(approvalsApi.createApprovalDelegation).not.toHaveBeenCalled();
  });

  it('should open cancel dialog and cancel a delegation', () => {
    component.openCancelDialog(mockDelegations[0]);
    expect(dialogSpy.open).toHaveBeenCalledWith(component.cancelDialogTemplate, {
      width: '440px',
    });
    expect(component.cancellingDelegation()).toEqual(mockDelegations[0]);

    approvalsApi.cancelApprovalDelegation.and.returnValue(of(void 0));

    component.confirmCancel();

    expect(approvalsApi.cancelApprovalDelegation).toHaveBeenCalledWith('dlg-1');
    expect(mockDialogRef.close).toHaveBeenCalled();
    expect(component.cancellingDelegation()).toBeNull();
    expect(approvalsApi.listApprovalDelegations).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Delegation cancelled.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should surface error when cancel fails', () => {
    component.openCancelDialog(mockDelegations[0]);

    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'internal', message: 'Cancel failed', trace_id: 'dlg_can_1' },
    });
    approvalsApi.cancelApprovalDelegation.and.returnValue(throwError(() => error500));

    component.confirmCancel();

    expect(component.isCancelling()).toBeFalse();
    expect(component.cancelErrorMessage()).toBe('Cancel failed');
    expect(component.cancelErrorTraceId()).toBe('dlg_can_1');
    expect(mockDialogRef.close).not.toHaveBeenCalled();
  });
});
