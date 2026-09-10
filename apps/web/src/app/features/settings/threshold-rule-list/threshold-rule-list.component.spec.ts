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
  Branch,
  Member,
  Role,
  ThresholdRule,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ApprovalsApiService } from '../../approvals/approvals-api';
import { OrganisationApiService } from '../organisation-api';
import { ThresholdRuleListComponent } from './threshold-rule-list.component';

const mockRules: ThresholdRule[] = [
  {
    id: 'tr-1',
    branch_id: 'b1',
    min_amount: '1000',
    max_amount: '5000',
    currency: 'USD',
    approver_membership_id: 'm1',
    created_by: 'm1',
    created_at: '2026-08-20T10:00:00Z',
  },
  {
    id: 'tr-2',
    branch_id: null,
    min_amount: '5000.00',
    max_amount: null,
    currency: 'USD',
    approver_membership_id: 'm2',
    created_by: 'm1',
    created_at: '2026-08-21T10:00:00Z',
  },
];

const mockBranches: Branch[] = [
  {
    id: 'b1',
    name: 'Main Branch',
    address: '12 High St',
    region: 'GB',
    is_active: true,
    created_at: '2026-08-20T10:00:00Z',
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
];

describe('ThresholdRuleListComponent', () => {
  let component: ThresholdRuleListComponent;
  let fixture: ComponentFixture<ThresholdRuleListComponent>;
  let approvalsApi: jasmine.SpyObj<ApprovalsApiService>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let mockDialogRef: jasmine.SpyObj<MatDialogRef<unknown>>;
  let roleSignal: WritableSignal<Role | null>;
  let sessionMock: {
    hasRole: jasmine.Spy;
    role: WritableSignal<Role | null>;
    tenant: WritableSignal<{ currency: string } | null>;
    currentMember: unknown;
    isAuthenticated: unknown;
    activeLocale: unknown;
  };

  beforeEach(async () => {
    approvalsApi = jasmine.createSpyObj('ApprovalsApiService', [
      'listThresholdRules',
      'createThresholdRule',
      'updateThresholdRule',
      'deleteThresholdRule',
    ]);
    organisationApi = jasmine.createSpyObj('OrganisationApiService', [
      'listBranches',
    ]);
    api = jasmine.createSpyObj('ApiService', ['members', 'configOptions']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    mockDialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);

    dialogSpy.open.and.returnValue(mockDialogRef);

    roleSignal = signal<Role | null>('owner');
    sessionMock = {
      hasRole: jasmine
        .createSpy('hasRole')
        .and.callFake((...roles: readonly Role[]) => {
          const current = roleSignal();
          return current !== null && roles.includes(current);
        }),
      role: roleSignal,
      tenant: signal({ currency: 'USD' }),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      activeLocale: signal('en'),
    };

    approvalsApi.listThresholdRules.and.returnValue(
      of({ items: mockRules, next_cursor: null }),
    );
    organisationApi.listBranches.and.returnValue(
      of({ items: mockBranches, next_cursor: null }),
    );
    api.members.and.returnValue(
      of({ items: mockMembers, next_cursor: null }),
    );
    api.configOptions.and.returnValue(
      of({
        regions: [],
        currencies: [{ code: 'USD', label_en: 'US Dollar', label_ar: 'دولار أمريكي' }],
        tax_models: [],
      }),
    );

    await TestBed.configureTestingModule({
      imports: [ThresholdRuleListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApprovalsApiService, useValue: approvalsApi },
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: api },
        { provide: SessionService, useValue: sessionMock },
      ],
    })
      .overrideComponent(ThresholdRuleListComponent, {
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

    fixture = TestBed.createComponent(ThresholdRuleListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load threshold rules on init with limit 50', () => {
    expect(approvalsApi.listThresholdRules).toHaveBeenCalledWith({ limit: 50 });
    expect(component.rules().length).toBe(2);
    expect(component.rules()[0].min_amount).toBe('1000');
    expect(component.isLoading()).toBeFalse();
  });

  it('should show the empty state when no threshold rules exist', () => {
    approvalsApi.listThresholdRules.and.returnValue(
      of({ items: [], next_cursor: null }),
    );
    component.loadRules();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.empty-state')).toBeTruthy();
    expect(compiled.querySelector('.rules-table')).toBeNull();
  });

  it('should render branch name for rules with a branch, and default label for tenant-wide rules', () => {
    expect(component.branchLabel(mockRules[0])).toBe('Main Branch');
    expect(component.branchLabel(mockRules[1])).toBe('All branches (default)');
  });

  it('should render approver email when known, and fall back to membership id', () => {
    expect(component.approverLabel(mockRules[0])).toBe('approver1@example.com');
    const unknownRule: ThresholdRule = {
      ...mockRules[0],
      approver_membership_id: 'unknown-id',
    };
    expect(component.approverLabel(unknownRule)).toBe('unknown-id');
  });

  it('should surface API errors with trace id on list load failure', () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'internal', message: 'Database failed', trace_id: 'tr_err_1' },
    });
    approvalsApi.listThresholdRules.and.returnValue(throwError(() => error500));
    component.loadRules();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('Database failed');
    expect(component.errorTraceId()).toBe('tr_err_1');

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.error-banner')).toBeTruthy();
    expect(compiled.textContent).toContain('tr_err_1');
  });

  it('should hide create button and actions column for non-owner roles', () => {
    expect(component.isOwner()).toBeTrue();
    expect(component.displayedColumns()).toContain('actions');

    roleSignal.set('viewer');
    fixture.detectChanges();

    expect(component.isOwner()).toBeFalse();
    expect(component.displayedColumns()).not.toContain('actions');
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.action-btn')).toBeNull();
    expect(compiled.querySelectorAll('.actions-cell').length).toBe(0);
  });

  it('should validate form fields correctly', () => {
    component.openCreateDialog();

    expect(component.form.valid).toBeFalse();

    // Set invalid pattern on min_amount
    component.form.controls.min_amount.setValue('abc');
    expect(component.form.controls.min_amount.hasError('pattern')).toBeTrue();

    // Set valid min_amount
    component.form.controls.min_amount.setValue('100');
    expect(component.form.controls.min_amount.valid).toBeTrue();

    // Set max_amount lower than min_amount
    component.form.controls.max_amount.setValue('50');
    expect(component.form.hasError('maxLessThanMin')).toBeTrue();

    // Fix max_amount >= min_amount
    component.form.controls.max_amount.setValue('200');
    expect(component.form.hasError('maxLessThanMin')).toBeFalse();

    // Approver is required
    expect(component.form.controls.approver_membership_id.hasError('required')).toBeTrue();
    component.form.controls.approver_membership_id.setValue('m1');

    // Currency
    component.form.controls.currency.setValue('USD');

    expect(component.form.valid).toBeTrue();
  });

  it('should open create dialog and submit a new threshold rule', () => {
    component.openCreateDialog();
    expect(dialogSpy.open).toHaveBeenCalledWith(component.ruleDialogTemplate, {
      width: '500px',
    });
    expect(component.editingRule()).toBeNull();

    component.form.controls.min_amount.setValue('500');
    component.form.controls.max_amount.setValue('2500');
    component.form.controls.currency.setValue('USD');
    component.form.controls.approver_membership_id.setValue('m1');
    component.form.controls.branch_id.setValue('b1');

    const createdRule: ThresholdRule = {
      id: 'tr-3',
      branch_id: 'b1',
      min_amount: '500',
      max_amount: '2500',
      currency: 'USD',
      approver_membership_id: 'm1',
      created_by: 'm1',
      created_at: '2026-08-22T10:00:00Z',
    };
    approvalsApi.createThresholdRule.and.returnValue(of(createdRule));

    component.saveRule();

    expect(approvalsApi.createThresholdRule).toHaveBeenCalledWith({
      branch_id: 'b1',
      min_amount: '500',
      max_amount: '2500',
      currency: 'USD',
      approver_membership_id: 'm1',
    });
    expect(mockDialogRef.close).toHaveBeenCalled();
    expect(approvalsApi.listThresholdRules).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Threshold rule created.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should open edit dialog pre-filled and submit an update', () => {
    component.openEditDialog(mockRules[0]);
    expect(dialogSpy.open).toHaveBeenCalledWith(component.ruleDialogTemplate, {
      width: '500px',
    });
    expect(component.editingRule()).toEqual(mockRules[0]);
    expect(component.form.controls.min_amount.value).toBe('1000');
    expect(component.form.controls.max_amount.value).toBe('5000');
    expect(component.form.controls.currency.value).toBe('USD');
    expect(component.form.controls.branch_id.value).toBe('b1');
    expect(component.form.controls.approver_membership_id.value).toBe('m1');

    component.form.controls.max_amount.setValue('6000');

    const updatedRule: ThresholdRule = { ...mockRules[0], max_amount: '6000' };
    approvalsApi.updateThresholdRule.and.returnValue(of(updatedRule));

    component.saveRule();

    expect(approvalsApi.updateThresholdRule).toHaveBeenCalledWith('tr-1', {
      branch_id: 'b1',
      min_amount: '1000',
      max_amount: '6000',
      currency: 'USD',
      approver_membership_id: 'm1',
    });
    expect(mockDialogRef.close).toHaveBeenCalled();
    expect(approvalsApi.listThresholdRules).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Threshold rule updated.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should surface dialog error when rule creation fails', () => {
    component.openCreateDialog();
    component.form.controls.min_amount.setValue('500');
    component.form.controls.currency.setValue('USD');
    component.form.controls.approver_membership_id.setValue('m1');

    const error422 = new HttpErrorResponse({
      status: 422,
      error: { code: 'validation', message: 'Invalid rule', trace_id: 'tr_dlg_1' },
    });
    approvalsApi.createThresholdRule.and.returnValue(throwError(() => error422));

    component.saveRule();

    expect(component.isSubmitting()).toBeFalse();
    expect(component.dialogErrorMessage()).toBe('Invalid rule');
    expect(component.dialogErrorTraceId()).toBe('tr_dlg_1');
    expect(mockDialogRef.close).not.toHaveBeenCalled();
  });

  it('should open delete dialog and delete a threshold rule', () => {
    component.openDeleteDialog(mockRules[0]);
    expect(dialogSpy.open).toHaveBeenCalledWith(component.deleteDialogTemplate, {
      width: '440px',
    });
    expect(component.deletingRule()).toEqual(mockRules[0]);

    approvalsApi.deleteThresholdRule.and.returnValue(of(void 0));

    component.confirmDelete();

    expect(approvalsApi.deleteThresholdRule).toHaveBeenCalledWith('tr-1');
    expect(mockDialogRef.close).toHaveBeenCalled();
    expect(component.deletingRule()).toBeNull();
    expect(approvalsApi.listThresholdRules).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Threshold rule deleted.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should surface error when delete fails', () => {
    component.openDeleteDialog(mockRules[0]);

    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'internal', message: 'Delete failed', trace_id: 'tr_del_1' },
    });
    approvalsApi.deleteThresholdRule.and.returnValue(throwError(() => error500));

    component.confirmDelete();

    expect(component.isDeleting()).toBeFalse();
    expect(component.deleteErrorMessage()).toBe('Delete failed');
    expect(component.deleteErrorTraceId()).toBe('tr_del_1');
    expect(mockDialogRef.close).not.toHaveBeenCalled();
  });
});
