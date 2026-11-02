import { Component, inject, ChangeDetectionStrategy } from '@angular/core';
import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { TranslatePipe } from '@ngx-translate/core';

import type { Member } from '../../../core/api/models';

export interface EditNameDialogData {
  readonly member: Member;
}

export interface EditNameDialogResult {
  readonly displayName: string;
}

function nonWhitespaceValidator(control: AbstractControl): ValidationErrors | null {
  const value = control.value;
  if (typeof value === 'string' && value.trim().length === 0) {
    return { whitespace: true };
  }
  return null;
}

@Component({
  selector: 'app-edit-name-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    TranslatePipe,
  ],
  templateUrl: './edit-name-dialog.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './edit-name-dialog.component.scss',
})
export class EditNameDialogComponent {
  private readonly fb = inject(FormBuilder);
  private readonly dialogRef = inject(
    MatDialogRef<EditNameDialogComponent, EditNameDialogResult>,
  );
  readonly data: EditNameDialogData = inject(MAT_DIALOG_DATA);

  readonly form = this.fb.nonNullable.group({
    display_name: [
      this.data.member.display_name ?? '',
      [Validators.required, Validators.maxLength(100), nonWhitespaceValidator],
    ],
  });

  onConfirm(): void {
    if (this.form.invalid) return;

    const trimmed = this.form.getRawValue().display_name.trim();
    if (!trimmed) return;

    this.dialogRef.close({ displayName: trimmed });
  }

  onCancel(): void {
    this.dialogRef.close();
  }
}
