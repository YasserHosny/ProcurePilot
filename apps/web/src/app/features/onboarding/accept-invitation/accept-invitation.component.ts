import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';

interface ErrorAlert {
  readonly title: string;
  readonly message: string;
  readonly traceId?: string;
}

@Component({
  selector: 'app-accept-invitation',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatRadioModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    TranslatePipe,
  ],
  templateUrl: './accept-invitation.component.html',
  styleUrl: './accept-invitation.component.scss',
})
export class AcceptInvitationComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly translate = inject(TranslateService);

  readonly isSubmitting = signal<boolean>(false);
  readonly hidePassword = signal<boolean>(true);
  readonly errorAlert = signal<ErrorAlert | null>(null);

  /** 'new' = requires password; 'existing' = already has account, no password */
  readonly accountMode = signal<'new' | 'existing'>('new');

  readonly form = this.fb.nonNullable.group({
    token: ['', [Validators.required]],
    password: ['', [Validators.required, Validators.minLength(12)]],
  });

  ngOnInit(): void {
    const tokenParam =
      this.route.snapshot.queryParamMap.get('token') ??
      this.route.snapshot.queryParamMap.get('invitation_token');
    if (tokenParam) {
      this.form.patchValue({ token: tokenParam.trim() });
    }
  }

  onAccountModeChange(mode: 'new' | 'existing'): void {
    this.accountMode.set(mode);
    const passwordControl = this.form.controls.password;

    if (mode === 'new') {
      passwordControl.setValidators([Validators.required, Validators.minLength(12)]);
    } else {
      passwordControl.clearValidators();
      passwordControl.setValue('');
    }
    passwordControl.updateValueAndValidity();
  }

  togglePasswordVisibility(): void {
    this.hidePassword.update((v) => !v);
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.errorAlert.set(null);
    this.isSubmitting.set(true);

    const { token, password } = this.form.getRawValue();
    const passwordPayload = this.accountMode() === 'new' && password ? password : undefined;

    this.api.acceptInvitation(token.trim(), passwordPayload).subscribe({
      next: (session) => {
        this.isSubmitting.set(false);
        this.session.adopt(session);
        void this.router.navigate(['/home']);
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          if (err.status === 403) {
            this.errorAlert.set({
              title: this.translate.instant('onboarding.acceptInvitation.invalidOrExpiredTitle'),
              message: this.translate.instant(
                'onboarding.acceptInvitation.invalidOrExpiredMessage',
              ),
              traceId: apiError?.trace_id,
            });
            return;
          }

          this.errorAlert.set({
            title: this.translate.instant('onboarding.acceptInvitation.defaultErrorTitle'),
            message:
              apiError?.message ??
              err.message ??
              this.translate.instant('onboarding.acceptInvitation.genericError'),
            traceId: apiError?.trace_id,
          });
          return;
        }

        this.errorAlert.set({
          title: this.translate.instant('onboarding.acceptInvitation.defaultErrorTitle'),
          message: this.translate.instant('onboarding.acceptInvitation.genericError'),
        });
      },
    });
  }
}
