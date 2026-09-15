import { NgClass, NgFor, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type {
  ScorecardConfidence,
  SupplierScoreMetric,
  SupplierScorecard,
} from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';

/**
 * Supplier Scorecard (R2.4 Supplier IQ, T028).
 *
 * Dense operational display showing historical supplier performance:
 * - Fulfilment rate, quality score, price competitiveness, spend exposure, freshness score, savings contribution
 * - Deterministic risk scoring and sub-score breakdown
 * - Source transaction counts (purchase records, quality issues, landed costs, savings)
 * - Insufficient evidence handling when transaction history is sparse
 * - No autonomous purchasing side effects
 */
@Component({
  selector: 'app-supplier-scorecard',
  standalone: true,
  imports: [
    NgIf,
    NgFor,
    NgClass,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatSelectModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  template: `
    <main role="main" aria-labelledby="scorecard-heading" class="scorecard-page">
      <!-- Back navigation -->
      <nav [attr.aria-label]="'supplierIq.backToSupplier' | translate">
        <a
          mat-button
          [routerLink]="['/suppliers', supplierId()]"
          class="back-link"
          [attr.aria-label]="'supplierIq.backToSupplier' | translate"
        >
          <mat-icon aria-hidden="true">arrow_back</mat-icon>
          {{ 'supplierIq.backToSupplier' | translate }}
        </a>
      </nav>

      <!-- Page header -->
      <header class="page-header">
        <div class="header-titles">
          <h1 id="scorecard-heading">{{ 'supplierIq.header' | translate }}</h1>
          <p class="supplier-subtitle" *ngIf="supplierName()">
            {{ supplierName() }}
          </p>
        </div>

        <!-- Window Selection -->
        <div class="window-selector" role="group" [attr.aria-label]="'supplierIq.windowLabel' | translate:{ months: windowMonths() }">
          <mat-chip-set>
            <mat-chip
              *ngFor="let months of [3, 6, 12]"
              [highlighted]="windowMonths() === months"
              (click)="changeWindow(months)"
              tabindex="0"
              (keydown.enter)="changeWindow(months)"
              (keydown.space)="changeWindow(months)"
              [attr.aria-label]="'supplierIq.windowLabel' | translate:{ months: months }"
            >
              {{ 'supplierIq.windowLabel' | translate:{ months: months } }}
            </mat-chip>
          </mat-chip-set>
        </div>
      </header>

      <!-- Loading State -->
      <div *ngIf="isLoading()" class="loading-state" role="status">
        <mat-spinner [attr.aria-label]="'common.loading' | translate" diameter="48"></mat-spinner>
        <p>{{ 'common.loading' | translate }}</p>
      </div>

      <!-- Error State -->
      <div *ngIf="errorMessage() && !isLoading()" class="error-banner" role="alert">
        <mat-icon aria-hidden="true">error_outline</mat-icon>
        <span>{{ errorMessage() }}</span>
      </div>

      <!-- Scorecard Content -->
      <div *ngIf="scorecard() && !isLoading()" class="scorecard-content">
        <!-- Insufficient evidence notice -->
        <section
          *ngIf="isInsufficient()"
          role="status"
          aria-live="polite"
          [attr.aria-label]="'supplierIq.insufficientEvidence.badge' | translate"
          class="insufficient-notice"
        >
          <mat-chip-set>
            <mat-chip color="warn" highlighted>
              <mat-icon matChipAvatar aria-hidden="true">warning</mat-icon>
              {{ 'supplierIq.insufficientEvidence.badge' | translate }}
            </mat-chip>
          </mat-chip-set>
          <p class="notice-text">{{ 'supplierIq.insufficientEvidence.notice' | translate }}</p>
        </section>

        <!-- Top summary row: Risk Score & Confidence -->
        <div class="summary-cards-row">
          <!-- Overall Risk Card -->
          <mat-card class="summary-card risk-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.riskScore.label' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="risk-metric-display">
                <span class="risk-score-value">{{ formatRiskScore(riskScore()?.total) }}</span>
                <span class="risk-level-badge" [ngClass]="riskLevel()">
                  {{ ('supplierIq.riskScore.' + riskLevel()) | translate }}
                </span>
              </div>
              <p class="risk-rule-version" *ngIf="riskScore()?.rule_version">
                {{ riskScore()?.rule_version }}
              </p>
            </mat-card-content>
          </mat-card>

          <!-- Confidence & Validity Card -->
          <mat-card class="summary-card confidence-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.confidence.label' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="confidence-display">
                <span class="confidence-badge" [ngClass]="confidence()">
                  {{ ('supplierIq.confidence.' + confidence()) | translate }}
                </span>
              </div>
              <p class="window-dates" *ngIf="scorecard()?.window_start">
                {{ scorecard()?.window_start | formatDate }} — {{ scorecard()?.window_end | formatDate }}
              </p>
            </mat-card-content>
          </mat-card>
        </div>

        <!-- Performance Metrics Grid -->
        <section aria-labelledby="metrics-heading" class="metrics-section">
          <h2 id="metrics-heading" class="section-heading">{{ 'supplierIq.metrics.sectionTitle' | translate }}</h2>

          <div class="metrics-grid" role="list" [attr.aria-label]="'supplierIq.metrics.sectionTitle' | translate">
            <!-- Fulfilment Rate -->
            <mat-card role="listitem" class="metric-card" tabindex="0">
              <mat-card-header>
                <mat-card-title>{{ 'supplierIq.metrics.fulfilmentRate' | translate }}</mat-card-title>
              </mat-card-header>
              <mat-card-content>
                <div class="metric-value">{{ formatMetricValue(metrics()['fulfilment_rate']) }}</div>
                <div class="metric-sample-count" *ngIf="metrics()['fulfilment_rate'] as m">
                  {{ 'supplierIq.sampleCounts.samples' | translate:{ count: m.sample_count } }}
                </div>
              </mat-card-content>
            </mat-card>

            <!-- Quality Score -->
            <mat-card role="listitem" class="metric-card" tabindex="0">
              <mat-card-header>
                <mat-card-title>{{ 'supplierIq.metrics.qualityScore' | translate }}</mat-card-title>
              </mat-card-header>
              <mat-card-content>
                <div class="metric-value">{{ formatMetricValue(metrics()['quality_score']) }}</div>
                <div class="metric-sample-count" *ngIf="metrics()['quality_score'] as m">
                  {{ 'supplierIq.sampleCounts.samples' | translate:{ count: m.sample_count } }}
                </div>
              </mat-card-content>
            </mat-card>

            <!-- Price Competitiveness -->
            <mat-card role="listitem" class="metric-card" tabindex="0">
              <mat-card-header>
                <mat-card-title>{{ 'supplierIq.metrics.priceCompetitiveness' | translate }}</mat-card-title>
              </mat-card-header>
              <mat-card-content>
                <div class="metric-value">{{ formatMetricValue(metrics()['price_competitiveness']) }}</div>
                <div class="metric-sample-count" *ngIf="metrics()['price_competitiveness'] as m">
                  {{ 'supplierIq.sampleCounts.samples' | translate:{ count: m.sample_count } }}
                </div>
              </mat-card-content>
            </mat-card>

            <!-- Spend Exposure -->
            <mat-card role="listitem" class="metric-card" tabindex="0">
              <mat-card-header>
                <mat-card-title>{{ 'supplierIq.metrics.spendExposure' | translate }}</mat-card-title>
              </mat-card-header>
              <mat-card-content>
                <div class="metric-value">{{ formatMetricValue(metrics()['spend_exposure']) }}</div>
                <div class="metric-sample-count" *ngIf="metrics()['spend_exposure'] as m">
                  {{ 'supplierIq.sampleCounts.samples' | translate:{ count: m.sample_count } }}
                </div>
              </mat-card-content>
            </mat-card>

            <!-- Freshness Score -->
            <mat-card role="listitem" class="metric-card" tabindex="0">
              <mat-card-header>
                <mat-card-title>{{ 'supplierIq.metrics.freshnessScore' | translate }}</mat-card-title>
              </mat-card-header>
              <mat-card-content>
                <div class="metric-value">{{ formatMetricValue(metrics()['freshness_score']) }}</div>
                <div class="metric-sample-count" *ngIf="metrics()['freshness_score'] as m">
                  {{ 'supplierIq.sampleCounts.samples' | translate:{ count: m.sample_count } }}
                </div>
              </mat-card-content>
            </mat-card>

            <!-- Savings Contribution -->
            <mat-card role="listitem" class="metric-card" tabindex="0">
              <mat-card-header>
                <mat-card-title>{{ 'supplierIq.metrics.savingsContribution' | translate }}</mat-card-title>
              </mat-card-header>
              <mat-card-content>
                <div class="metric-value">{{ formatMetricValue(metrics()['savings_contribution']) }}</div>
                <div class="metric-sample-count" *ngIf="metrics()['savings_contribution'] as m">
                  {{ 'supplierIq.sampleCounts.samples' | translate:{ count: m.sample_count } }}
                </div>
              </mat-card-content>
            </mat-card>
          </div>
        </section>

        <!-- Risk Sub-scores Breakdown -->
        <section aria-labelledby="risk-breakdown-heading" class="risk-section" *ngIf="riskScore()?.sub_scores?.length">
          <h2 id="risk-breakdown-heading" class="section-heading">{{ 'supplierIq.riskScore.breakdown' | translate }}</h2>

          <div class="sub-scores-grid">
            <mat-card *ngFor="let sub of riskScore()?.sub_scores" class="sub-score-card" tabindex="0">
              <div class="sub-score-header">
                <span class="sub-score-name">{{ ('supplierIq.subScores.' + sub.name) | translate }}</span>
                <span class="sub-score-val">{{ formatRiskScore(sub.score) }}</span>
              </div>
              <div class="sub-score-weight">
                <span>{{ 'supplierIq.riskScore.weightLabel' | translate:{ weight: sub.weight } }}</span>
              </div>
            </mat-card>
          </div>
        </section>

        <!-- Source Evidence Counts -->
        <section aria-labelledby="evidence-heading" class="evidence-section">
          <h2 id="evidence-heading" class="section-heading">{{ 'supplierIq.sourceEvidence.sectionTitle' | translate }}</h2>

          <mat-card class="evidence-card">
            <dl class="evidence-list">
              <div class="evidence-row">
                <dt>{{ 'supplierIq.sourceEvidence.purchaseRecord' | translate }}</dt>
                <dd><strong>{{ sourceCounts()['purchase_record'] ?? 0 }}</strong></dd>
              </div>
              <div class="evidence-row">
                <dt>{{ 'supplierIq.sourceEvidence.tenantPurchaseRecord' | translate }}</dt>
                <dd><strong>{{ sourceCounts()['tenant_purchase_record'] ?? 0 }}</strong></dd>
              </div>
              <div class="evidence-row">
                <dt>{{ 'supplierIq.sourceEvidence.deliveryQualityIssue' | translate }}</dt>
                <dd><strong>{{ sourceCounts()['delivery_quality_issue'] ?? 0 }}</strong></dd>
              </div>
              <div class="evidence-row">
                <dt>{{ 'supplierIq.sourceEvidence.landedCost' | translate }}</dt>
                <dd><strong>{{ sourceCounts()['landed_cost'] ?? 0 }}</strong></dd>
              </div>
              <div class="evidence-row">
                <dt>{{ 'supplierIq.sourceEvidence.marketLandedCost' | translate }}</dt>
                <dd><strong>{{ sourceCounts()['market_landed_cost'] ?? 0 }}</strong></dd>
              </div>
              <div class="evidence-row">
                <dt>{{ 'supplierIq.sourceEvidence.savingRecord' | translate }}</dt>
                <dd><strong>{{ sourceCounts()['saving_record'] ?? 0 }}</strong></dd>
              </div>
              <div class="evidence-row">
                <dt>{{ 'supplierIq.sourceEvidence.tenantSavingRecord' | translate }}</dt>
                <dd><strong>{{ sourceCounts()['tenant_saving_record'] ?? 0 }}</strong></dd>
              </div>
            </dl>
          </mat-card>
        </section>

        <!-- Scorecard Footer Metadata -->
        <footer class="scorecard-footer">
          <span *ngIf="scorecard()?.rule_version">
            {{ 'supplierIq.ruleVersion' | translate:{ version: scorecard()?.rule_version } }}
          </span>
          <span *ngIf="scorecard()?.computed_at">
            {{ 'supplierIq.computedAt' | translate:{ date: (scorecard()?.computed_at | formatDate) } }}
          </span>
        </footer>
      </div>
    </main>
  `,
  styles: [
    `
      .scorecard-page {
        padding-inline: 1.5rem;
        padding-block: 1.5rem;
        max-width: 1100px;
        margin-inline: auto;
      }

      .back-link {
        margin-block-end: 1rem;
      }

      .page-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        flex-wrap: wrap;
        gap: 1rem;
        margin-block-end: 1.5rem;
      }

      .header-titles h1 {
        font-size: 1.75rem;
        font-weight: 600;
        margin: 0;
      }

      .supplier-subtitle {
        color: #5f6368;
        font-size: 1.125rem;
        margin-block-start: 0.25rem;
        margin-block-end: 0;
      }

      .window-selector mat-chip {
        cursor: pointer;
      }

      .loading-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding-block: 3rem;
        gap: 1rem;
      }

      .error-banner {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 1rem;
        border-radius: 4px;
        background-color: var(--mat-warn-lighter-color, #ffebee);
        color: var(--mat-warn-color, #c62828);
        margin-block-end: 1.5rem;
      }

      .insufficient-notice {
        margin-block-end: 1.5rem;
        padding: 1rem;
        border-inline-start: 4px solid var(--mat-warn-color, #f44336);
        background-color: var(--mat-warn-lighter-color, #fce4ec);
        border-radius: 4px;
      }

      .notice-text {
        margin-block-start: 0.75rem;
        margin-block-end: 0;
        line-height: 1.4;
      }

      .summary-cards-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 1.25rem;
        margin-block-end: 2rem;
      }

      .summary-card {
        padding: 1rem;
      }

      .risk-metric-display,
      .confidence-display {
        display: flex;
        align-items: center;
        gap: 1rem;
        padding-block: 0.5rem;
      }

      .risk-score-value {
        font-size: 2.25rem;
        font-weight: 700;
      }

      .risk-level-badge,
      .confidence-badge {
        padding-inline: 0.75rem;
        padding-block: 0.25rem;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.875rem;
        text-transform: capitalize;
      }

      .risk-level-badge.low,
      .confidence-badge.high {
        background-color: #e8f5e9;
        color: #2e7d32;
      }

      .risk-level-badge.medium,
      .confidence-badge.medium {
        background-color: #fff8e1;
        color: #7c4a03;
      }

      .risk-level-badge.high,
      .confidence-badge.low {
        background-color: #ffebee;
        color: #c62828;
      }

      .risk-rule-version,
      .window-dates {
        color: #5f6368;
        font-size: 0.8125rem;
        margin-block-start: 0.5rem;
        margin-block-end: 0;
      }

      .section-heading {
        font-size: 1.25rem;
        font-weight: 600;
        margin-block-start: 0;
        margin-block-end: 1rem;
      }

      .metrics-section,
      .risk-section,
      .evidence-section {
        margin-block-end: 2rem;
      }

      .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 1rem;
      }

      .metric-card {
        padding: 0.5rem;
      }

      .metric-card:focus,
      .summary-card:focus,
      .sub-score-card:focus {
        outline: 2px solid var(--mat-primary-color, #1976d2);
        outline-offset: 2px;
      }

      .metric-value {
        font-size: 1.75rem;
        font-weight: 700;
        padding-block: 0.25rem;
      }

      .metric-sample-count {
        font-size: 0.8125rem;
        color: var(--mat-hint-color, #757575);
      }

      .sub-scores-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 0.75rem;
      }

      .sub-score-card {
        padding: 0.75rem 1rem;
      }

      .sub-score-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-weight: 500;
      }

      .sub-score-weight {
        font-size: 0.75rem;
        color: var(--mat-hint-color, #757575);
        margin-block-start: 0.25rem;
      }

      .evidence-card {
        padding: 0.5rem 1.25rem;
      }

      .evidence-list {
        margin: 0;
      }

      .evidence-row {
        display: flex;
        justify-content: space-between;
        padding-block: 0.75rem;
        border-block-end: 1px solid var(--mat-divider-color, #e0e0e0);
      }

      .evidence-row:last-child {
        border-block-end: none;
      }

      .evidence-row dt {
        font-weight: 400;
      }

      .evidence-row dd {
        margin: 0;
      }

      .scorecard-footer {
        display: flex;
        justify-content: space-between;
        color: var(--mat-hint-color, #757575);
        font-size: 0.8125rem;
        margin-block-start: 1rem;
        padding-block-start: 1rem;
        border-block-start: 1px solid var(--mat-divider-color, #e0e0e0);
      }
    `,
  ],
})
export class SupplierScorecardComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ApiService);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly supplierId = signal<string>('');
  readonly supplierName = signal<string>('');
  readonly windowMonths = signal<number>(6);
  readonly scorecard = signal<SupplierScorecard | null>(null);
  readonly isLoading = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);

  readonly isInsufficient = computed<boolean>(
    () => this.scorecard()?.insufficient_evidence ?? true,
  );

  readonly confidence = computed<ScorecardConfidence>(
    () => this.scorecard()?.confidence ?? 'low',
  );

  readonly riskScore = computed(() => this.scorecard()?.risk_score);

  readonly riskLevel = computed<'low' | 'medium' | 'high'>(() => {
    const score = parseFloat(this.scorecard()?.risk_score?.total ?? '0');
    if (isNaN(score) || score < 0.30) return 'low';
    if (score < 0.70) return 'medium';
    return 'high';
  });

  readonly metrics = computed<Record<string, SupplierScoreMetric>>(
    () => this.scorecard()?.metrics ?? {},
  );

  readonly sourceCounts = computed<Partial<Record<string, number>>>(
    () => this.scorecard()?.source_counts ?? {},
  );

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const id = params.get('id');
      if (id) {
        this.supplierId.set(id);
        this.loadSupplierAndScorecard(id, this.windowMonths());
      }
    });
  }

  changeWindow(months: number): void {
    if (months === this.windowMonths()) return;
    this.windowMonths.set(months);
    const id = this.supplierId();
    if (id) {
      this.loadScorecardOnly(id, months);
    }
  }

  loadSupplierAndScorecard(id: string, windowMonths: number): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    // Fetch supplier info for header
    this.api
      .supplier(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (supp) => {
          this.supplierName.set(supp.name);
        },
        error: () => {
          // Supplier name load failure is non-fatal
        },
      });

    this.loadScorecardOnly(id, windowMonths);
  }

  private loadScorecardOnly(id: string, windowMonths: number): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.api
      .getSupplierScorecard(id, { window_months: windowMonths })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (sc) => {
          this.scorecard.set(sc);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          if (err instanceof HttpErrorResponse && err.status === 404) {
            this.errorMessage.set(this.translate.instant('supplierIq.error.notFound'));
          } else {
            this.errorMessage.set(this.translate.instant('supplierIq.error.generic'));
          }
        },
      });
  }

  formatMetricValue(metric: SupplierScoreMetric | null | undefined): string {
    if (!metric || metric.value === null || metric.value === undefined) {
      return '—';
    }
    const num = parseFloat(metric.value);
    if (isNaN(num)) {
      return metric.value;
    }
    // If normalized 0-1 probability/rate, convert to percentage
    if (num >= 0 && num <= 1) {
      return `${(num * 100).toFixed(1)}%`;
    }
    return `${num.toFixed(1)}%`;
  }

  formatRiskScore(score: string | null | undefined): string {
    if (!score) return '—';
    const num = parseFloat(score);
    if (isNaN(num)) return score;
    if (num >= 0 && num <= 1) {
      return `${(num * 100).toFixed(1)}%`;
    }
    return `${num.toFixed(1)}%`;
  }
}
