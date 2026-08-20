import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, ConfigOptions } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { SIGNUP_STRINGS } from './signup.strings';

interface ErrorAlert {
  readonly type: 'error' | 'forbidden';
  readonly title: string;
  readonly message: string;
  readonly traceId?: string;
}

@Component({
  selector: 'app-signup',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './signup.component.html',
  styleUrl: './signup.component.scss',
})
export class SignupComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly strings = SIGNUP_STRINGS;

  readonly isSubmitting = signal<boolean>(false);
  readonly isLoadingConfig = signal<boolean>(true);
  readonly hidePassword = signal<boolean>(true);
  readonly configOptions = signal<ConfigOptions | null>(null);
  readonly errorAlert = signal<ErrorAlert | null>(null);

  /**
   * Reactive form for workspace creation (FR-031).
   * Note: Region, currency, and tax_model deliberately have NO pre-selected default value.
   */
  readonly form = this.fb.nonNullable.group({
    invitation_token: ['', [Validators.required, Validators.minLength(32)]],
    business_name: ['', [Validators.required, Validators.maxLength(200)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(12)]],
    region: ['', [Validators.required]],
    currency: ['', [Validators.required]],
    tax_model: ['', [Validators.required]],
  });

  ngOnInit(): void {
    const tokenParam =
      this.route.snapshot.queryParamMap.get('token') ??
      this.route.snapshot.queryParamMap.get('invitation_token');
    if (tokenParam) {
      this.form.patchValue({ invitation_token: tokenParam });
    }

    this.loadConfigOptions();
  }

  loadConfigOptions(): void {
    this.isLoadingConfig.set(true);
    this.api.configOptions().subscribe({
      next: (options) => {
        this.configOptions.set(options);
        this.isLoadingConfig.set(false);
      },
      error: () => {
        this.isLoadingConfig.set(false);
        this.errorAlert.set({
          type: 'error',
          title: this.strings.defaultErrorTitle,
          message: this.strings.configError,
        });
      },
    });
  }

  togglePasswordVisibility(): void {
    this.hidePassword.update((val) => !val);
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.errorAlert.set(null);
    this.isSubmitting.set(true);

    const formVal = this.form.getRawValue();

    this.api
      .signup({
        invitation_token: formVal.invitation_token.trim(),
        business_name: formVal.business_name.trim(),
        email: formVal.email.trim(),
        password: formVal.password,
        region: formVal.region,
        currency: formVal.currency,
        tax_model: formVal.tax_model,
        default_locale: 'en',
      })
      .subscribe({
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
                type: 'forbidden',
                title: this.strings.invitationForbiddenTitle,
                message: this.strings.invitationForbiddenMessage,
                traceId: apiError?.trace_id,
              });
              return;
            }

            this.errorAlert.set({
              type: 'error',
              title: this.strings.defaultErrorTitle,
              message: apiError?.message ?? err.message ?? this.strings.invitationForbiddenMessage,
              traceId: apiError?.trace_id,
            });
            return;
          }

          this.errorAlert.set({
            type: 'error',
            title: this.strings.defaultErrorTitle,
            message: this.strings.configError,
          });
        },
      });
  }
}
