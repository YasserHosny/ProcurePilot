import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
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
import { CursorPager } from '../../../layout/list-pager/cursor-pager';
import { ListPagerComponent } from '../../../layout/list-pager/list-pager.component';
import { SupplierRiskApiService, SupplierRiskSnapshot } from '../supplier-risk-api';

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
    ListPagerComponent,
    FormatDatePipe,
  ],
  templateUrl: './risk-queue.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './risk-queue.component.scss',
})
export class RiskQueueComponent implements OnInit {
  private readonly api = inject(SupplierRiskApiService);
  private readonly session = inject(SessionService);

  private latestLoadRequestId = 0;

  readonly risks = signal<SupplierRiskSnapshot[]>([]);
  readonly pager = new CursorPager('supplier-risks');
  readonly isLoading = signal(true);
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
    this.loadRisks();
  }

  loadRisks(): void {
    const requestId = ++this.latestLoadRequestId;
    this.isLoading.set(true);
    this.error.set(null);

    const { cursor, limit } = this.pager.params();
    this.api.listRisks(cursor, limit).subscribe({
      next: (page) => {
        if (requestId !== this.latestLoadRequestId) return;
        if (!this.pager.loaded(page)) {
          this.loadRisks();
          return;
        }
        this.risks.set(page.items);
        this.isLoading.set(false);
      },
      error: () => {
        if (requestId !== this.latestLoadRequestId) return;
        if (!this.pager.failed()) this.risks.set([]);
        this.error.set('load');
        this.isLoading.set(false);
      },
    });
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
        this.pager.reset();
        this.loadRisks();
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
