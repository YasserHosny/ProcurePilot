import { DecimalPipe, NgClass } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  type DigestSubscription,
  type DigestView,
  DigestsApiService,
} from './digests-api';

@Component({
  selector: 'app-digest-settings',
  standalone: true,
  imports: [
    NgClass,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDividerModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatDatePipe,
    DecimalPipe,
  ],
  templateUrl: './digest-settings.component.html',
  styleUrl: './digest-settings.component.scss',
})
export class DigestSettingsComponent implements OnInit {
  private readonly digestsApi = inject(DigestsApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoadingView = signal<boolean>(true);
  readonly isLoadingSubs = signal<boolean>(true);
  readonly isMutating = signal<boolean>(false);

  readonly digestView = signal<DigestView | null>(null);
  readonly subscriptions = signal<DigestSubscription[]>([]);
  readonly showOnboarding = signal<boolean>(true);

  readonly viewError = signal<string | null>(null);
  readonly subsError = signal<string | null>(null);

  ngOnInit(): void {
    this.loadDigestView();
    this.loadSubscriptions();
  }

  loadDigestView(): void {
    this.isLoadingView.set(true);
    this.viewError.set(null);
    this.digestsApi.getLatestDigest().subscribe({
      next: (view) => {
        this.isLoadingView.set(false);
        this.digestView.set(view);
      },
      error: (err) => {
        this.isLoadingView.set(false);
        this.viewError.set(err?.message || 'Failed to load weekly digest.');
      },
    });
  }

  loadSubscriptions(): void {
    this.isLoadingSubs.set(true);
    this.subsError.set(null);
    this.digestsApi.getSubscriptions().subscribe({
      next: (res) => {
        this.isLoadingSubs.set(false);
        this.subscriptions.set(res.items || []);
      },
      error: (err) => {
        this.isLoadingSubs.set(false);
        this.subsError.set(err?.message || 'Failed to load subscriptions.');
      },
    });
  }

  togglePause(sub: DigestSubscription): void {
    const nextStatus = sub.status === 'active' ? 'paused' : 'active';
    this.isMutating.set(true);
    this.digestsApi.updateSubscription(sub.id, { status: nextStatus }).subscribe({
      next: (updated) => {
        this.isMutating.set(false);
        this.subscriptions.update((subs) =>
          subs.map((s) => (s.id === updated.id ? updated : s))
        );
        this.snackBar.open(
          this.translate.instant('digests.settings.statusUpdated') || 'Status updated',
          undefined,
          { duration: 3000 }
        );
      },
      error: (err) => {
        this.isMutating.set(false);
        this.snackBar.open(err?.message || 'Update failed', undefined, { duration: 4000 });
      },
    });
  }

  toggleChannel(sub: DigestSubscription): void {
    const nextChannel = sub.channel === 'email' ? 'in_app' : 'email';
    this.isMutating.set(true);
    this.digestsApi.updateSubscription(sub.id, { channel: nextChannel }).subscribe({
      next: (updated) => {
        this.isMutating.set(false);
        this.subscriptions.update((subs) =>
          subs.map((s) => (s.id === updated.id ? updated : s))
        );
        this.snackBar.open(
          this.translate.instant('digests.settings.channelUpdated') || 'Delivery channel updated',
          undefined,
          { duration: 3000 }
        );
      },
      error: (err) => {
        this.isMutating.set(false);
        this.snackBar.open(err?.message || 'Update failed', undefined, { duration: 4000 });
      },
    });
  }

  dismissOnboarding(): void {
    this.showOnboarding.set(false);
  }
}
