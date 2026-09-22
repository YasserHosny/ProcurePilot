import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { SupplierRiskApiService, SupplierRiskSnapshot } from '../supplier-risk-api';

const PAGE_SIZE = 50;
const DRIVER_ORDER = [
  'concentration',
  'price_drift',
  'reliability',
  'single_source',
] as const;

type QueueError = 'load' | 'recompute';

@Component({
  selector: 'app-risk-queue',
  standalone: true,
  imports: [
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTableModule,
    MatTooltipModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './risk-queue.component.html',
  styleUrl: './risk-queue.component.scss',
})
export class RiskQueueComponent implements OnInit {
  private readonly api = inject(SupplierRiskApiService);
  private readonly session = inject(SessionService);

  readonly risks = signal<SupplierRiskSnapshot[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly isLoading = signal(true);
  readonly isLoadingMore = signal(false);
  readonly isRecomputing = signal(false);
  readonly error = signal<QueueError | null>(null);
  readonly recomputedCount = signal<number | null>(null);
  readonly isWriter = computed(() => this.session.hasRole('owner', 'buyer'));

  readonly displayedColumns: readonly string[] = [
    'supplier',
    'risk',
    'confidence',
    'state',
    'driver',
    'posture',
    'validity',
    'actions',
  ];

  ngOnInit(): void {
    this.loadRisks(true);
  }

  loadRisks(reset: boolean): void {
    if (reset) {
      this.isLoading.set(true);
      this.error.set(null);
    } else {
      if (this.isLoadingMore() || !this.nextCursor()) return;
      this.isLoadingMore.set(true);
    }

    const cursor = reset ? undefined : (this.nextCursor() ?? undefined);
    this.api.listRisks(cursor, PAGE_SIZE).subscribe({
      next: (page) => {
        this.risks.update((current) => (reset ? [...page.items] : [...current, ...page.items]));
        this.nextCursor.set(page.next_cursor);
        this.isLoading.set(false);
        this.isLoadingMore.set(false);
      },
      error: () => {
        this.error.set('load');
        this.isLoading.set(false);
        this.isLoadingMore.set(false);
      },
    });
  }

  loadMore(): void {
    this.loadRisks(false);
  }

  recompute(): void {
    if (!this.isWriter() || this.isRecomputing()) return;

    this.error.set(null);
    this.recomputedCount.set(null);
    this.isRecomputing.set(true);
    this.api.recompute().subscribe({
      next: (result) => {
        this.recomputedCount.set(result.generated_snapshots);
        this.isRecomputing.set(false);
        this.loadRisks(true);
      },
      error: () => {
        this.error.set('recompute');
        this.isRecomputing.set(false);
      },
    });
  }

  topDriver(risk: SupplierRiskSnapshot): string | null {
    let selected: string | null = null;
    let highest = Number.NEGATIVE_INFINITY;
    for (const driver of DRIVER_ORDER) {
      const value = risk.risk_score.components[driver];
      if (value === null || value === undefined) continue;
      const numeric = Number(value);
      if (Number.isFinite(numeric) && numeric > highest) {
        highest = numeric;
        selected = driver;
      }
    }
    return selected;
  }

  riskPercent(risk: SupplierRiskSnapshot): number | null {
    const value = risk.risk_score.total;
    if (value === null) return null;
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Math.round(numeric * 100) : null;
  }

  evidenceAgeDays(computedAt: string): number {
    const timestamp = Date.parse(computedAt);
    if (!Number.isFinite(timestamp)) return 0;
    return Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
  }

  isStale(validUntil: string): boolean {
    const timestamp = Date.parse(validUntil);
    return Number.isFinite(timestamp) && timestamp <= Date.now();
  }
}
