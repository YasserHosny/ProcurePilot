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
import { TranslatePipe, TranslateService } from "@ngx-translate/core";

import type { ApiError, Branch, BranchCreate, BranchUpdate } from "../../../../core/api/models";
import { OrganisationApiService } from "../../organisation-api";

export interface BranchFormDialogData {
  readonly mode: "create" | "edit";
  readonly branch?: Branch;
}

const FORM_I18N = "organisation.branches.form";

@Component({
  selector: "app-branch-form-dialog",
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    TranslatePipe,
  ],
  templateUrl: "./branch-form-dialog.component.html",
  styleUrl: "./branch-form-dialog.component.scss",
})
export class BranchFormDialogComponent {
  private readonly fb = inject(FormBuilder);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly translate = inject(TranslateService);
  private readonly dialogRef = inject(MatDialogRef<BranchFormDialogComponent, Branch | boolean>);

  readonly data: BranchFormDialogData = inject(MAT_DIALOG_DATA);

  readonly isEditMode = this.data.mode === "edit" && this.data.branch !== undefined;

  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    name: [this.data.branch?.name ?? "", [Validators.required]],
    address: [this.data.branch?.address ?? ""],
    region: [this.data.branch?.region ?? ""],
  });

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

    const { name, address, region } = this.form.getRawValue();

    if (this.isEditMode && this.data.branch) {
      const payload: BranchUpdate = {
        name: name.trim(),
        address: address.trim() || null,
        region: region.trim() || null,
      };
      this.organisationApi.updateBranch(this.data.branch.id, payload).subscribe({
        next: (branch) => {
          this.isSubmitting.set(false);
          this.dialogRef.close(branch);
        },
        error: (err: unknown) => this.handleSubmitError(err),
      });
      return;
    }

    const payload: BranchCreate = {
      name: name.trim(),
      address: address.trim() || null,
      region: region.trim() || null,
    };
    this.organisationApi.createBranch(payload).subscribe({
      next: (branch) => {
        this.isSubmitting.set(false);
        this.dialogRef.close(branch);
      },
      error: (err: unknown) => this.handleSubmitError(err),
    });
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }

  private handleSubmitError(err: unknown): void {
    this.isSubmitting.set(false);
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant("organisation.branches.genericError"),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant("organisation.branches.genericError"));
  }
}
