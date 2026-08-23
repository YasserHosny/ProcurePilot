import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApiError,
  Branch,
  BranchList,
  BranchRoleAssignmentCreate,
  Member,
  Role,
} from '../../../core/api/models';

export interface ChangeRoleDialogData {
  readonly member: Member;
}

/** Roles that CAN be scoped to a branch — these get the branch picker in this dialog. */
const BRANCH_SCOPED_ROLES: readonly Role[] = ['branch_manager', 'approver'];

const DIALOG_I18N = 'team.changeRoleDialog';

@Component({
  selector: 'app-change-role-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    TranslatePipe,
  ],
  templateUrl: './change-role-dialog.component.html',
  styleUrl: './change-role-dialog.component.scss',
})
export class ChangeRoleDialogComponent {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly translate = inject(TranslateService);
  private readonly dialogRef = inject(MatDialogRef<ChangeRoleDialogComponent, Role>);
  readonly data: ChangeRoleDialogData = inject(MAT_DIALOG_DATA);

  readonly roles: readonly Role[] = ['owner', 'buyer', 'branch_manager', 'approver', 'viewer'];

  readonly branches = signal<Branch[]>([]);
  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  /** Drives branch-picker visibility; kept in step via the role control's events. */
  readonly selectedRole = signal<Role>(this.data.member.role);

  readonly form = this.fb.nonNullable.group({
    role: [this.data.member.role, [Validators.required]],
    branch_id: this.fb.control<string | null>(null),
  });

  constructor() {
    this.loadBranches();
    this.form.controls.role.valueChanges.subscribe((role) => this.onRoleChange(role));
  }

  isBranchScopedRole(role: Role): boolean {
    return BRANCH_SCOPED_ROLES.includes(role);
  }

  onConfirm(): void {
    if (this.form.invalid) return;

    const { role, branch_id } = this.form.getRawValue();

    // Assigning a branch is optional: a plain role change closes exactly as before and
    // the parent's contract (close value === selected Role) is untouched.
    const branchId = this.isBranchScopedRole(role) ? branch_id : null;
    if (branchId === null) {
      this.dialogRef.close(role);
      return;
    }

    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.isSubmitting.set(true);

    const payload: BranchRoleAssignmentCreate = {
      membership_id: this.data.member.id,
      branch_id: branchId,
    };

    // The assignment is the dialog's own second action; it happens here, not in team.component.
    this.api.createBranchRoleAssignment(payload).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.dialogRef.close(role);
      },
      error: (err: unknown) => this.handleAssignmentError(err),
    });
  }

  onCancel(): void {
    this.dialogRef.close();
  }

  /** Fail-soft: an unavailable branch list must never block the role change itself. */
  private loadBranches(): void {
    this.api
      .listBranches()
      .pipe(catchError(() => of<BranchList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.branches.set([...res.items]));
  }

  /**
   * Reset first so a stale pick can never survive a role switch (budget-form-dialog
   * pattern): the value and any validators are cleared whenever the role moves away
   * from a branch-scopable one.
   */
  private onRoleChange(role: Role): void {
    this.selectedRole.set(role);

    const branchControl = this.form.controls.branch_id;
    branchControl.setValue(null);
    branchControl.clearValidators();
    branchControl.updateValueAndValidity();
  }

  private handleAssignmentError(err: unknown): void {
    this.isSubmitting.set(false);
    if (!(err instanceof HttpErrorResponse)) {
      this.errorMessage.set(this.translate.instant(`${DIALOG_I18N}.assignmentError`));
      return;
    }
    const apiError = err.error as ApiError | undefined;
    this.errorTraceId.set(apiError?.trace_id ?? null);
    if (err.status === 409) {
      this.errorMessage.set(
        this.translate.instant(`${DIALOG_I18N}.duplicateAssignmentError`),
      );
      return;
    }
    this.errorMessage.set(
      apiError?.message ??
        err.message ??
        this.translate.instant(`${DIALOG_I18N}.assignmentError`),
    );
  }
}
