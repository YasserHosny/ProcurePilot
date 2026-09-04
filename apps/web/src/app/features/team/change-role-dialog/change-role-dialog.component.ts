import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { TranslatePipe } from '@ngx-translate/core';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import type { Branch, BranchList, Member, Role } from '../../../core/api/models';

export interface ChangeRoleDialogData {
  readonly member: Member;
}

/**
 * What this dialog collects — never what it does. The backend requires a membership to
 * ALREADY hold branch_manager/approver before an assignment can be created (FR-006), so the
 * role change and the branch assignment must be two sequential, server-round-tripped steps in
 * that exact order — a dialog closing with a bare Role can't express that sequencing, so the
 * parent (TeamComponent) owns both API calls, in order, after this dialog closes.
 */
export interface ChangeRoleDialogResult {
  readonly role: Role;
  readonly branchId: string | null;
}

/** Roles that CAN be scoped to a branch — these get the branch picker in this dialog. */
const BRANCH_SCOPED_ROLES: readonly Role[] = ['branch_manager', 'approver'];

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
  private readonly dialogRef = inject(
    MatDialogRef<ChangeRoleDialogComponent, ChangeRoleDialogResult>,
  );
  readonly data: ChangeRoleDialogData = inject(MAT_DIALOG_DATA);

  readonly roles: readonly Role[] = ['owner', 'buyer', 'branch_manager', 'approver', 'viewer'];

  readonly branches = signal<Branch[]>([]);

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
    // Assigning a branch is optional even when the role is branch-scopable — a plain role
    // change with no branch picked closes with branchId: null, and the parent skips the
    // assignment step entirely.
    const branchId = this.isBranchScopedRole(role) ? branch_id : null;
    this.dialogRef.close({ role, branchId });
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
}
