import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Invitation, Role } from '../../../core/api/models';

interface CreatedInvitationResult {
  readonly invitation: Invitation;
  readonly token?: string;
  readonly inviteUrl?: string;
}

@Component({
  selector: 'app-invite-dialog',
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
  templateUrl: './invite-dialog.component.html',
  styleUrl: './invite-dialog.component.scss',
})
export class InviteDialogComponent {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly translate = inject(TranslateService);
  private readonly dialogRef = inject(MatDialogRef<InviteDialogComponent, boolean>);

  readonly roles: readonly Role[] = ['owner', 'buyer', 'branch_manager', 'approver', 'viewer'];

  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly createdResult = signal<CreatedInvitationResult | null>(null);
  readonly isCopied = signal<boolean>(false);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    role: ['buyer' as Role, [Validators.required]],
  });

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.isSubmitting.set(true);

    const { email, role } = this.form.getRawValue();

    this.api.invite(email.trim(), role).subscribe({
      next: (invitation) => {
        this.isSubmitting.set(false);
        const token = (invitation as Invitation & { token?: string }).token;
        const origin = typeof window !== 'undefined' ? window.location.origin : '';
        const inviteUrl = token ? `${origin}/onboarding/accept-invitation?token=${encodeURIComponent(token)}` : undefined;

        this.createdResult.set({
          invitation,
          token,
          inviteUrl,
        });
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          this.errorTraceId.set(apiError?.trace_id ?? null);

          if (err.status === 409) {
            this.errorMessage.set(
              this.translate.instant('team.inviteDialog.duplicateInviteError'),
            );
            return;
          }

          this.errorMessage.set(
            apiError?.message ??
              err.message ??
              this.translate.instant('team.inviteDialog.genericError'),
          );
          return;
        }

        this.errorMessage.set(this.translate.instant('team.inviteDialog.genericError'));
      },
    });
  }

  copyToClipboard(textToCopy: string): void {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      void navigator.clipboard.writeText(textToCopy).then(() => {
        this.isCopied.set(true);
        setTimeout(() => this.isCopied.set(false), 2500);
      });
    }
  }

  onCloseSuccess(): void {
    this.dialogRef.close(true);
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }
}
