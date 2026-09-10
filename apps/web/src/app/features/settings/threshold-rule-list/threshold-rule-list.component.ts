import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  OnInit,
  TemplateRef,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import {
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApiError,
  Branch,
  BranchList,
  ConfigOptions,
  Member,
  ReferenceOption,
  ThresholdRule,
  ThresholdRuleCreate,
  ThresholdRuleList,
  ThresholdRuleUpdate,
} from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { SessionService } from '../../../core/auth/session.service';
import { FormatMoneyPipe } from '../../../core/format';
import { ApprovalsApiService } from '../../approvals/approvals-api';
import { OrganisationApiService } from '../organisation-api';

const RULES_I18N = 'approvals.thresholdRules';
const AMOUNT_PATTERN = /^\d+(\.\d{1,4})?$/;

function amountRangeValidator(group: AbstractControl): ValidationErrors | null {
  const minVal = group.get('min_amount')?.value;
  const maxVal = group.get('max_amount')?.value;
  if (!minVal || !maxVal || (typeof maxVal === 'string' && maxVal.trim() === '')) {
    return null;
  }
  const min = parseFloat(minVal);
  const max = parseFloat(maxVal);
  if (!isNaN(min) && !isNaN(max) && max < min) {
    return { maxLessThanMin: true };
  }
  return null;
}

@Component({
  selector: 'app-threshold-rule-list',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    TranslatePipe,
    RoleDirective,
    FormatMoneyPipe,
  ],
  templateUrl: './threshold-rule-list.component.html',
  styleUrl: './threshold-rule-list.component.scss',
})
export class ThresholdRuleListComponent implements OnInit {
  private readonly approvalsApi = inject(ApprovalsApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly fb = inject(FormBuilder);

  @ViewChild('ruleDialog') readonly ruleDialogTemplate!: TemplateRef<unknown>;
  @ViewChild('deleteDialog') readonly deleteDialogTemplate!: TemplateRef<unknown>;

  ruleDialogRef: MatDialogRef<unknown> | null = null;
  deleteDialogRef: MatDialogRef<unknown> | null = null;

  readonly isLoading = signal<boolean>(true);
  readonly rules = signal<ThresholdRule[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isSubmitting = signal<boolean>(false);
  readonly dialogErrorMessage = signal<string | null>(null);
  readonly dialogErrorTraceId = signal<string | null>(null);
  readonly editingRule = signal<ThresholdRule | null>(null);

  readonly isDeleting = signal<boolean>(false);
  readonly deletingRule = signal<ThresholdRule | null>(null);
  readonly deleteErrorMessage = signal<string | null>(null);
  readonly deleteErrorTraceId = signal<string | null>(null);

  readonly branches = signal<Branch[]>([]);
  readonly members = signal<Member[]>([]);
  readonly currencies = signal<readonly ReferenceOption[]>([]);

  readonly isOwner = computed<boolean>(() => this.session.hasRole('owner'));

  readonly displayedColumns = computed<readonly string[]>(() =>
    this.isOwner()
      ? ['branch', 'minAmount', 'maxAmount', 'currency', 'approver', 'actions']
      : ['branch', 'minAmount', 'maxAmount', 'currency', 'approver'],
  );

  readonly branchNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const branch of this.branches()) {
      byId.set(branch.id, branch.name);
    }
    return byId;
  });

  readonly memberEmailById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const member of this.members()) {
      byId.set(member.id, member.email);
    }
    return byId;
  });

  readonly form = this.fb.group(
    {
      branch_id: this.fb.control<string | null>(null),
      min_amount: this.fb.nonNullable.control('', [
        Validators.required,
        Validators.pattern(AMOUNT_PATTERN),
      ]),
      max_amount: this.fb.control<string | null>(null, [
        Validators.pattern(AMOUNT_PATTERN),
      ]),
      currency: this.fb.nonNullable.control('', [
        Validators.required,
        Validators.pattern(/^[A-Z]{3}$/),
      ]),
      approver_membership_id: this.fb.nonNullable.control('', [
        Validators.required,
      ]),
    },
    { validators: [amountRangeValidator] },
  );

  ngOnInit(): void {
    this.loadRules();
    this.loadReferenceData();
  }

  loadRules(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.approvalsApi.listThresholdRules({ limit: 50 }).subscribe({
      next: (res: ThresholdRuleList) => {
        this.rules.set([...res.items]);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  branchLabel(rule: ThresholdRule): string {
    if (!rule.branch_id) {
      return this.translate.instant(`${RULES_I18N}.defaultBranch`);
    }
    return this.branchNameById().get(rule.branch_id) ?? rule.branch_id;
  }

  approverLabel(rule: ThresholdRule): string {
    return (
      this.memberEmailById().get(rule.approver_membership_id) ??
      rule.approver_membership_id
    );
  }

  isBranchInList(id: string | null): boolean {
    if (!id) return false;
    return this.branches().some((b) => b.id === id);
  }

  isMemberInList(id: string): boolean {
    return this.members().some((m) => m.id === id);
  }

  isCurrencyInList(code: string): boolean {
    return this.currencies().some((c) => c.code === code);
  }

  openCreateDialog(): void {
    this.editingRule.set(null);
    this.dialogErrorMessage.set(null);
    this.dialogErrorTraceId.set(null);

    const defaultCurrency =
      this.session.tenant()?.currency ??
      (this.currencies().length > 0 ? this.currencies()[0].code : 'USD');

    this.form.reset({
      branch_id: null,
      min_amount: '',
      max_amount: null,
      currency: defaultCurrency,
      approver_membership_id: '',
    });

    this.ruleDialogRef = this.dialog.open(this.ruleDialogTemplate, {
      width: '500px',
    });
  }

  openEditDialog(rule: ThresholdRule): void {
    this.editingRule.set(rule);
    this.dialogErrorMessage.set(null);
    this.dialogErrorTraceId.set(null);

    this.form.reset({
      branch_id: rule.branch_id ?? null,
      min_amount: rule.min_amount,
      max_amount: rule.max_amount ?? null,
      currency: rule.currency,
      approver_membership_id: rule.approver_membership_id,
    });

    this.ruleDialogRef = this.dialog.open(this.ruleDialogTemplate, {
      width: '500px',
    });
  }

  closeRuleDialog(): void {
    this.ruleDialogRef?.close();
    this.ruleDialogRef = null;
  }

  saveRule(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);
    this.dialogErrorMessage.set(null);
    this.dialogErrorTraceId.set(null);

    const raw = this.form.getRawValue();
    const current = this.editingRule();

    if (current) {
      const payload: ThresholdRuleUpdate = {
        branch_id: raw.branch_id || null,
        min_amount: raw.min_amount.trim(),
        max_amount: raw.max_amount?.trim() || null,
        currency: raw.currency.trim().toUpperCase(),
        approver_membership_id: raw.approver_membership_id.trim(),
      };

      this.approvalsApi.updateThresholdRule(current.id, payload).subscribe({
        next: () => {
          this.isSubmitting.set(false);
          this.closeRuleDialog();
          this.loadRules();
          this.snackBar.open(
            this.translate.instant(`${RULES_I18N}.updateSuccess`),
            undefined,
            { duration: 3500 },
          );
        },
        error: (err: unknown) => {
          this.isSubmitting.set(false);
          this.handleDialogError(err);
        },
      });
      return;
    }

    const payload: ThresholdRuleCreate = {
      branch_id: raw.branch_id || null,
      min_amount: raw.min_amount.trim(),
      max_amount: raw.max_amount?.trim() || null,
      currency: raw.currency.trim().toUpperCase(),
      approver_membership_id: raw.approver_membership_id.trim(),
    };

    this.approvalsApi.createThresholdRule(payload).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.closeRuleDialog();
        this.loadRules();
        this.snackBar.open(
          this.translate.instant(`${RULES_I18N}.createSuccess`),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        this.handleDialogError(err);
      },
    });
  }

  openDeleteDialog(rule: ThresholdRule): void {
    this.deletingRule.set(rule);
    this.deleteErrorMessage.set(null);
    this.deleteErrorTraceId.set(null);

    this.deleteDialogRef = this.dialog.open(this.deleteDialogTemplate, {
      width: '440px',
    });
  }

  closeDeleteDialog(): void {
    this.deleteDialogRef?.close();
    this.deleteDialogRef = null;
    this.deletingRule.set(null);
  }

  confirmDelete(): void {
    const rule = this.deletingRule();
    if (!rule) {
      return;
    }

    this.isDeleting.set(true);
    this.deleteErrorMessage.set(null);
    this.deleteErrorTraceId.set(null);

    this.approvalsApi.deleteThresholdRule(rule.id).subscribe({
      next: () => {
        this.isDeleting.set(false);
        this.closeDeleteDialog();
        this.loadRules();
        this.snackBar.open(
          this.translate.instant(`${RULES_I18N}.deleteSuccess`),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        this.isDeleting.set(false);
        this.handleDeleteError(err);
      },
    });
  }

  private loadReferenceData(): void {
    this.organisationApi
      .listBranches()
      .pipe(catchError(() => of<BranchList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.branches.set([...res.items]));

    this.api
      .members()
      .pipe(
        catchError(() =>
          of<{ items: Member[]; next_cursor: string | null }>({
            items: [],
            next_cursor: null,
          }),
        ),
      )
      .subscribe((res) => this.members.set([...res.items]));

    this.api
      .configOptions()
      .pipe(
        catchError(() =>
          of<ConfigOptions>({ regions: [], currencies: [], tax_models: [] }),
        ),
      )
      .subscribe((res) => this.currencies.set([...res.currencies]));
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${RULES_I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${RULES_I18N}.genericError`));
  }

  private handleDialogError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.dialogErrorTraceId.set(apiError?.trace_id ?? null);
      this.dialogErrorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${RULES_I18N}.genericError`),
      );
      return;
    }
    this.dialogErrorMessage.set(
      this.translate.instant(`${RULES_I18N}.genericError`),
    );
  }

  private handleDeleteError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.deleteErrorTraceId.set(apiError?.trace_id ?? null);
      this.deleteErrorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${RULES_I18N}.genericError`),
      );
      return;
    }
    this.deleteErrorMessage.set(
      this.translate.instant(`${RULES_I18N}.genericError`),
    );
  }
}
