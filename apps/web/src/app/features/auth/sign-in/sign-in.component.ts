import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { ApiError } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';

@Component({
  selector: 'app-sign-in',
  standalone: true,
  imports: [
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
  templateUrl: './sign-in.component.html',
  styleUrl: './sign-in.component.scss',
})
export class SignInComponent {
  private readonly fb = inject(FormBuilder);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(false);
  readonly hidePassword = signal<boolean>(true);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });

  togglePasswordVisibility(): void {
    this.hidePassword.update((val) => !val);
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.isLoading.set(true);

    const { email, password } = this.form.getRawValue();

    this.session.login(email.trim(), password).subscribe({
      next: () => {
        this.isLoading.set(false);
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/home';
        void this.router.navigateByUrl(returnUrl);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          this.errorTraceId.set(apiError?.trace_id ?? null);

          // Deliberate security rule: 401 must not reveal whether account exists
          if (err.status === 401) {
            this.errorMessage.set(this.translate.instant('auth.signin.invalidCredentialsError'));
            return;
          }

          if (err.status === 429) {
            this.errorMessage.set(this.translate.instant('auth.signin.rateLimitedError'));
            return;
          }

          this.errorMessage.set(
            apiError?.message ?? err.message ?? this.translate.instant('auth.signin.genericError'),
          );
          return;
        }

        this.errorMessage.set(this.translate.instant('auth.signin.genericError'));
      },
    });
  }
}
