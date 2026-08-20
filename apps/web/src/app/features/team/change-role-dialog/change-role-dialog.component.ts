import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { TranslatePipe } from '@ngx-translate/core';

import type { Member, Role } from '../../../core/api/models';

export interface ChangeRoleDialogData {
  readonly member: Member;
}

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
  private readonly dialogRef = inject(MatDialogRef<ChangeRoleDialogComponent, Role>);
  readonly data: ChangeRoleDialogData = inject(MAT_DIALOG_DATA);

  readonly roles: readonly Role[] = ['owner', 'buyer', 'branch_manager', 'approver', 'viewer'];

  readonly form = this.fb.nonNullable.group({
    role: [this.data.member.role, [Validators.required]],
  });

  onConfirm(): void {
    if (this.form.invalid) return;
    this.dialogRef.close(this.form.getRawValue().role);
  }

  onCancel(): void {
    this.dialogRef.close();
  }
}
