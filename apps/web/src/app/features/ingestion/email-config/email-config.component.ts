import { NgClass } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RoleDirective } from '../../../core/auth/role.directive';
import {
  IngestionApiService,
  type TenantEmailConfig,
} from '../ingestion-api';

@Component({
  selector: 'app-email-config',
  standalone: true,
  imports: [
    NgClass,
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    TranslatePipe,
    RoleDirective,
  ],
  templateUrl: './email-config.component.html',
  styleUrl: './email-config.component.scss',
})
export class EmailConfigComponent implements OnInit {
  private readonly ingestionApi = inject(IngestionApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isMutating = signal<boolean>(false);
  readonly config = signal<TenantEmailConfig | null>(null);
  readonly error = signal<string | null>(null);

  readonly newDomain = signal<string>('');

  ngOnInit(): void {
    this.loadConfig();
  }

  loadConfig(): void {
    this.isLoading.set(true);
    this.error.set(null);
    this.ingestionApi.getEmailConfig().subscribe({
      next: (data) => {
        this.isLoading.set(false);
        this.config.set(data);
      },
      error: () => {
        this.isLoading.set(false);
        this.error.set(this.translate.instant('ingestion.emailConfig.loadError'));
      },
    });
  }

  async copyAddress(): Promise<void> {
    const address = this.config()?.forwarding_address;
    if (!address) {
      return;
    }

    try {
      await navigator.clipboard.writeText(address);
      this.snackBar.open(
        this.translate.instant('ingestion.emailConfig.copySuccess'),
        undefined,
        { duration: 3000 }
      );
    } catch {
      this.snackBar.open(
        this.translate.instant('ingestion.emailConfig.copyError'),
        undefined,
        { duration: 4000 }
      );
    }
  }

  toggleEnabled(): void {
    const current = this.config();
    if (!current || this.isMutating()) {
      return;
    }

    const willEnable = !current.enabled;
    this.isMutating.set(true);

    const request$ = willEnable
      ? this.ingestionApi.enableEmailConfig()
      : this.ingestionApi.disableEmailConfig();

    request$.subscribe({
      next: (updated) => {
        this.isMutating.set(false);
        this.config.set(updated);
        const msgKey = willEnable
          ? 'ingestion.emailConfig.enabledSuccess'
          : 'ingestion.emailConfig.disabledSuccess';
        this.snackBar.open(
          this.translate.instant(msgKey),
          undefined,
          { duration: 3000 }
        );
      },
      error: () => {
        this.isMutating.set(false);
        this.snackBar.open(
          this.translate.instant('ingestion.emailConfig.updateFailed'),
          undefined,
          { duration: 4000 }
        );
      },
    });
  }

  addDomain(): void {
    const raw = this.newDomain().trim().toLowerCase();
    if (!raw) {
      return;
    }

    const domainPattern = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$/i;
    if (!domainPattern.test(raw)) {
      this.snackBar.open(
        this.translate.instant('ingestion.emailConfig.invalidDomain'),
        undefined,
        { duration: 3000 }
      );
      return;
    }

    const current = this.config()?.domain_allowlist ?? [];
    if (current.includes(raw)) {
      this.snackBar.open(
        this.translate.instant('ingestion.emailConfig.duplicateDomain'),
        undefined,
        { duration: 3000 }
      );
      return;
    }

    const updatedAllowlist = [...current, raw];
    this.saveDomainAllowlist(updatedAllowlist, () => {
      this.newDomain.set('');
    });
  }

  removeDomain(domainToRemove: string): void {
    const current = this.config()?.domain_allowlist ?? [];
    const updatedAllowlist = current.filter((d) => d !== domainToRemove);
    this.saveDomainAllowlist(updatedAllowlist);
  }

  private saveDomainAllowlist(domains: string[], onSuccess?: () => void): void {
    if (this.isMutating()) {
      return;
    }
    this.isMutating.set(true);

    this.ingestionApi.updateEmailConfig({ domain_allowlist: domains }).subscribe({
      next: (updated) => {
        this.isMutating.set(false);
        this.config.set(updated);
        onSuccess?.();
        this.snackBar.open(
          this.translate.instant('ingestion.emailConfig.updateSuccess'),
          undefined,
          { duration: 3000 }
        );
      },
      error: () => {
        this.isMutating.set(false);
        this.snackBar.open(
          this.translate.instant('ingestion.emailConfig.updateFailed'),
          undefined,
          { duration: 4000 }
        );
      },
    });
  }
}
