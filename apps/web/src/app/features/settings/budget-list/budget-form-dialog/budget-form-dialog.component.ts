import { HttpErrorResponse } from "@angular/common/http";
import { Component, inject, signal } from "@angular/core";
import { AbstractControl, FormBuilder, ReactiveFormsModule, Validators } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatDialogModule, MatDialogRef } from "@angular/material/dialog";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatIconModule } from "@angular/material/icon";
import { MatInputModule } from "@angular/material/input";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatSelectModule } from "@angular/material/select";
import { TranslatePipe, TranslateService } from "@ngx-translate/core";
import { of } from "rxjs";
import { catchError } from "rxjs/operators";

import type {
  ApiError,
  Branch,
  BranchList,
  BudgetCreate,
  BudgetCreated,
  BudgetPeriod,
  BudgetScope,
  ConfigOptions,
  CostCentre,
  CostCentreList,
  ReferenceOption,
} from "../../../../core/api/models";
import { ApiService } from "../../../../core/api/api.service";
import { SessionService } from "../../../../core/auth/session.service";
import { I18nService } from "../../../../core/i18n/i18n.service";
import { OrganisationApiService } from "../../organisation-api";

const BUDGETS_I18N = "organisation.budgets";
const FORM_I18N = `${BUDGETS_I18N}.form`;

/** Mirrors the contract's `^\d+(\.\d{1,4})?$` — a positive decimal string, no sign. */
const AMOUNT_PATTERN = /^\d+(\.\d{1,4})?$/;

const PERIODS: readonly BudgetPeriod[] = ["monthly", "quarterly", "annual"];
const SCOPES: readonly BudgetScope[] = ["organisation", "branch", "cost_centre"];

@Component({
  selector: "app-budget-form-dialog",
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    TranslatePipe,
  ],
  templateUrl: "./budget-form-dialog.component.html",
  styleUrl: "./budget-form-dialog.component.scss",
})
export class BudgetFormDialogComponent {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly session = inject(SessionService);
  private readonly i18n = inject(I18nService);
  private readonly translate = inject(TranslateService);
  private readonly dialogRef = inject(
    MatDialogRef<BudgetFormDialogComponent, BudgetCreated | boolean>,
  );

  readonly branches = signal<Branch[]>([]);
  readonly costCentres = signal<CostCentre[]>([]);
  readonly currencies = signal<readonly ReferenceOption[]>([]);

  readonly periods = PERIODS;
  readonly scopes = SCOPES;

  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  /** Drives the scope-dependent target pickers; kept in step via the scope control's events. */
  readonly selectedScope = signal<BudgetScope | null>(null);

  readonly form = this.fb.group({
    amount: this.fb.nonNullable.control("", [
      Validators.required,
      Validators.pattern(AMOUNT_PATTERN),
    ]),
    currency: this.fb.nonNullable.control<string>(
      this.session.tenant()?.currency ?? "",
      [Validators.required],
    ),
    period: this.fb.control<BudgetPeriod | null>(null, [Validators.required]),
    period_start: this.fb.nonNullable.control("", [Validators.required]),
    scope: this.fb.control<BudgetScope | null>(null, [Validators.required]),
    branch_id: this.fb.control<string | null>(null),
    cost_centre_id: this.fb.control<string | null>(null),
  });

  constructor() {
    this.loadPickers();
    this.form.controls.scope.valueChanges.subscribe((scope) => this.onScopeChange(scope));
  }

  get titleKey(): string {
    return `${FORM_I18N}.createTitle`;
  }

  currencyLabel(option: ReferenceOption): string {
    const label = this.i18n.currentLocale() === "ar" ? option.label_ar : option.label_en;
    return `${label || option.code} (${option.code})`;
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    const { period, scope } = raw;
    if (period === null || scope === null) {
      // Unreachable behind the form.invalid guard above; satisfies the payload types.
      return;
    }

    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.isSubmitting.set(true);

    const payload: BudgetCreate = {
      amount: raw.amount.trim(),
      currency: raw.currency,
      period,
      period_start: raw.period_start,
      scope,
      branch_id: scope === "branch" ? raw.branch_id : null,
      cost_centre_id: scope === "cost_centre" ? raw.cost_centre_id : null,
    };

    this.organisationApi.createBudget(payload).subscribe({
      next: (created) => {
        // The budget IS saved regardless of overlap_warning — FR-005. The caller decides
        // how to surface the flag; closing with the result keeps that decision list-side.
        this.isSubmitting.set(false);
        this.dialogRef.close(created);
      },
      error: (err: unknown) => this.handleSubmitError(err),
    });
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }

  /**
   * Scope decides which target picker exists at all: exactly one for branch/cost_centre
   * scopes, none for the whole organisation. Switching scope away clears the value the
   * previous picker held so it can never leak into the payload.
   */
  private onScopeChange(scope: BudgetScope | null): void {
    this.selectedScope.set(scope);

    const branchControl = this.form.controls.branch_id;
    const costCentreControl = this.form.controls.cost_centre_id;

    if (scope === "branch") {
      this.resetControl(costCentreControl, false);
      this.resetControl(branchControl, true);
      return;
    }

    if (scope === "cost_centre") {
      this.resetControl(branchControl, false);
      this.resetControl(costCentreControl, true);
      return;
    }

    this.resetControl(branchControl, false);
    this.resetControl(costCentreControl, false);
  }

  private resetControl(
    control: AbstractControl<string | null>,
    required: boolean,
  ): void {
    control.setValue(null);
    control.clearValidators();
    if (required) {
      control.setValidators(Validators.required);
    }
    control.updateValueAndValidity();
  }

  private loadPickers(): void {
    this.organisationApi
      .listBranches()
      .pipe(catchError(() => of<BranchList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.branches.set([...res.items]));

    this.organisationApi
      .listCostCentres()
      .pipe(catchError(() => of<CostCentreList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.costCentres.set([...res.items]));

    this.api
      .configOptions()
      .pipe(
        catchError(() =>
          of<ConfigOptions>({ regions: [], currencies: [], tax_models: [] }),
        ),
      )
      .subscribe((res) => this.currencies.set(res.currencies));
  }

  private handleSubmitError(err: unknown): void {
    this.isSubmitting.set(false);
    if (!(err instanceof HttpErrorResponse)) {
      this.errorMessage.set(this.translate.instant(`${BUDGETS_I18N}.genericError`));
      return;
    }
    const apiError = err.error as ApiError | undefined;
    this.errorTraceId.set(apiError?.trace_id ?? null);
    this.errorMessage.set(
      apiError?.message ??
        err.message ??
        this.translate.instant(`${BUDGETS_I18N}.genericError`),
    );
  }
}
