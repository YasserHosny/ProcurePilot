import { HttpErrorResponse } from '@angular/common/http';
import { Location } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError } from '../../../core/api/models';
import { BrandLogoComponent } from '../../../layout/brand-logo/brand-logo.component';

/** Matches the API's minimum (`PasswordUpdateRequest.password`). */
const MIN_PASSWORD_LENGTH = 12;

type PageState = 'form' | 'invalid' | 'done';

interface RecoverySession {
  accessToken: string;
  refreshToken: string;
}

/**
 * The reset email's link lands here with the recovery session in the URL fragment
 * (`#access_token=…&refresh_token=…&type=recovery`), or an `#error=…` when it has expired.
 */
function parseRecoveryFragment(fragment: string | null): RecoverySession | null {
  if (!fragment) {
    return null;
  }
  const params = new URLSearchParams(fragment);
  const accessToken = params.get('access_token');
  const refreshToken = params.get('refresh_token');
  if (params.has('error') || params.get('type') !== 'recovery' || !accessToken || !refreshToken) {
    return null;
  }
  return { accessToken, refreshToken };
}

function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const { password, confirm } = group.value as { password: string; confirm: string };
  return password === confirm ? null : { mismatch: true };
}

@Component({
  selector: 'app-update-password',
  standalone: true,
  imports: [
    BrandLogoComponent,
    ReactiveFormsModule,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    TranslatePipe,
  ],
  templateUrl: './update-password.component.html',
  styleUrl: '../password-reset/password-reset.component.scss',
})
export class UpdatePasswordComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly location = inject(Location);
  private readonly translate = inject(TranslateService);

  private session: RecoverySession | null = null;

  readonly minLength = MIN_PASSWORD_LENGTH;
  readonly state = signal<PageState>('form');
  readonly isLoading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group(
    {
      password: ['', [Validators.required, Validators.minLength(MIN_PASSWORD_LENGTH)]],
      confirm: ['', [Validators.required]],
    },
    { validators: passwordsMatch },
  );

  ngOnInit(): void {
    this.session = parseRecoveryFragment(this.route.snapshot.fragment);
    // The tokens are a live session: keep them out of the address bar and browser history.
    this.location.replaceState('/auth/update-password');
    if (!this.session) {
      this.state.set('invalid');
    }
  }

  onSubmit(): void {
    if (this.form.invalid || !this.session) {
      this.form.markAllAsTouched();
      return;
    }

    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.isLoading.set(true);

    const { accessToken, refreshToken } = this.session;
    this.api.updatePassword(accessToken, refreshToken, this.form.getRawValue().password).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.session = null;
        this.state.set('done');
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  private handleError(err: unknown): void {
    if (!(err instanceof HttpErrorResponse)) {
      this.errorMessage.set(this.translate.instant('auth.update.genericError'));
      return;
    }
    const apiError = err.error as ApiError | undefined;
    this.errorTraceId.set(apiError?.trace_id ?? null);

    if (err.status === 401) {
      this.session = null;
      this.state.set('invalid');
      return;
    }
    if (err.status === 422) {
      const reason = apiError?.details?.['reason'];
      const key =
        reason === 'same_password'
          ? 'auth.update.samePasswordError'
          : reason === 'weak_password'
            ? 'auth.update.weakPasswordError'
            : 'auth.update.genericError';
      this.errorMessage.set(this.translate.instant(key));
      return;
    }
    if (err.status === 429) {
      this.errorMessage.set(this.translate.instant('auth.update.rateLimitedError'));
      return;
    }
    this.errorMessage.set(this.translate.instant('auth.update.genericError'));
  }
}
