import { HttpErrorResponse } from "@angular/common/http";
import { Component, inject, signal } from "@angular/core";
import { FormBuilder, ReactiveFormsModule, Validators } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from "@angular/material/dialog";
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
  CostCentre,
  CostCentreCreate,
  CostCentreUpdate,
  Member,
} from "../../../../core/api/models";
import { ApiService } from "../../../../core/api/api.service";
import { OrganisationApiService } from "../../organisation-api";

export interface CostCentreFormDialogData {
  readonly mode: "create" | "edit";
  readonly costCentre?: CostCentre;
}

const COST_CENTRES_I18N = "organisation.costCentres";
const FORM_I18N = `${COST_CENTRES_I18N}.form`;

@Component({
  selector: "app-cost-centre-form-dialog",
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
  templateUrl: "./cost-centre-form-dialog.component.html",
  styleUrl: "./cost-centre-form-dialog.component.scss",
})
export class CostCentreFormDialogComponent {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly translate = inject(TranslateService);
  private readonly dialogRef = inject(
    MatDialogRef<CostCentreFormDialogComponent, CostCentre | boolean>,
  );

  readonly data: CostCentreFormDialogData = inject(MAT_DIALOG_DATA);

  readonly isEditMode = this.data.mode === "edit" && this.data.costCentre !== undefined;

  readonly members = signal<Member[]>([]);
  readonly branches = signal<Branch[]>([]);

  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly allBranchesKey = `${COST_CENTRES_I18N}.allBranchesValue`;

  readonly form = this.fb.group({
    name: this.fb.nonNullable.control(this.data.costCentre?.name ?? "", [
      Validators.required,
    ]),
    code: this.fb.nonNullable.control(this.data.costCentre?.code ?? "", [
      Validators.required,
    ]),
    budget_owner_membership_id: this.fb.nonNullable.control<string | null>(
      this.data.costCentre?.budget_owner_membership_id ?? null,
    ),
    branch_id: this.fb.nonNullable.control<string | null>(
      this.data.costCentre?.branch_id ?? null,
    ),
  });

  constructor() {
    this.loadPickers();
  }

  get titleKey(): string {
    return this.isEditMode ? `${FORM_I18N}.editTitle` : `${FORM_I18N}.createTitle`;
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.isSubmitting.set(true);

    const raw = this.form.getRawValue();
    const payload: CostCentreCreate = {
      name: raw.name.trim(),
      code: raw.code.trim(),
      budget_owner_membership_id: raw.budget_owner_membership_id,
      branch_id: raw.branch_id,
    };

    if (this.isEditMode && this.data.costCentre) {
      this.organisationApi
        .updateCostCentre(this.data.costCentre.id, payload satisfies CostCentreUpdate)
        .subscribe({
          next: (costCentre) => {
            this.isSubmitting.set(false);
            this.dialogRef.close(costCentre);
          },
          error: (err: unknown) => this.handleSubmitError(err),
        });
      return;
    }

    this.organisationApi.createCostCentre(payload).subscribe({
      next: (costCentre) => {
        this.isSubmitting.set(false);
        this.dialogRef.close(costCentre);
      },
      error: (err: unknown) => this.handleSubmitError(err),
    });
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }

  private loadPickers(): void {
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

    this.organisationApi
      .listBranches()
      .pipe(catchError(() => of<BranchList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.branches.set([...res.items]));
  }

  private handleSubmitError(err: unknown): void {
    this.isSubmitting.set(false);
    if (!(err instanceof HttpErrorResponse)) {
      this.errorMessage.set(this.translate.instant(`${COST_CENTRES_I18N}.genericError`));
      return;
    }
    const apiError = err.error as ApiError | undefined;
    this.errorTraceId.set(apiError?.trace_id ?? null);
    if (err.status === 409) {
      this.errorMessage.set(this.translate.instant(`${COST_CENTRES_I18N}.duplicateCodeError`));
      return;
    }
    this.errorMessage.set(
      apiError?.message ??
        err.message ??
        this.translate.instant(`${COST_CENTRES_I18N}.genericError`),
    );
  }
}
