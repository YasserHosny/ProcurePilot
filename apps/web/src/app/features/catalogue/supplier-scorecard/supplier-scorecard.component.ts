import { NgIf } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

/**
 * Supplier Scorecard — R2.4 Supplier IQ placeholder.
 *
 * This is a minimal standalone component that satisfies the T005 routing
 * requirement and provides ARIA-compliant markup with supplierIq i18n keys.
 * Full data-fetching and metric rendering land in the implementation task.
 */
@Component({
  selector: 'app-supplier-scorecard',
  standalone: true,
  imports: [
    NgIf,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    TranslatePipe,
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
        <h1 id="scorecard-heading">{{ 'supplierIq.header' | translate }}</h1>
      </header>

      <!-- Insufficient evidence notice (shown when no data) -->
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

      <!-- Metrics section -->
      <section aria-labelledby="metrics-heading" class="metrics-section">
        <h2 id="metrics-heading">{{ 'supplierIq.metrics.sectionTitle' | translate }}</h2>

        <div class="metrics-grid" role="list" [attr.aria-label]="'supplierIq.metrics.sectionTitle' | translate">
          <mat-card role="listitem" class="metric-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.metrics.fulfilmentRate' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="metric-value" role="text" [attr.aria-label]="'supplierIq.metrics.fulfilmentRate' | translate">—</div>
            </mat-card-content>
          </mat-card>

          <mat-card role="listitem" class="metric-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.metrics.onTimeDelivery' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="metric-value" role="text" [attr.aria-label]="'supplierIq.metrics.onTimeDelivery' | translate">—</div>
            </mat-card-content>
          </mat-card>

          <mat-card role="listitem" class="metric-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.metrics.qualityScore' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="metric-value" role="text" [attr.aria-label]="'supplierIq.metrics.qualityScore' | translate">—</div>
            </mat-card-content>
          </mat-card>

          <mat-card role="listitem" class="metric-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.metrics.priceCompetitiveness' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="metric-value" role="text" [attr.aria-label]="'supplierIq.metrics.priceCompetitiveness' | translate">—</div>
            </mat-card-content>
          </mat-card>

          <mat-card role="listitem" class="metric-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.metrics.spendExposure' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="metric-value" role="text" [attr.aria-label]="'supplierIq.metrics.spendExposure' | translate">—</div>
            </mat-card-content>
          </mat-card>

          <mat-card role="listitem" class="metric-card" tabindex="0">
            <mat-card-header>
              <mat-card-title>{{ 'supplierIq.metrics.disputeRate' | translate }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <div class="metric-value" role="text" [attr.aria-label]="'supplierIq.metrics.disputeRate' | translate">—</div>
            </mat-card-content>
          </mat-card>
        </div>
      </section>

      <!-- Risk score section -->
      <section aria-labelledby="risk-heading" class="risk-section">
        <h2 id="risk-heading">{{ 'supplierIq.riskScore.breakdown' | translate }}</h2>
        <p>{{ 'supplierIq.riskScore.label' | translate }}: —</p>
      </section>

      <!-- Evidence sources section -->
      <section aria-labelledby="evidence-heading" class="evidence-section">
        <h2 id="evidence-heading">{{ 'supplierIq.sourceEvidence.sectionTitle' | translate }}</h2>
        <dl>
          <div class="evidence-row">
            <dt>{{ 'supplierIq.sourceEvidence.quotationCount' | translate }}</dt>
            <dd>—</dd>
          </div>
          <div class="evidence-row">
            <dt>{{ 'supplierIq.sourceEvidence.deliveryCount' | translate }}</dt>
            <dd>—</dd>
          </div>
          <div class="evidence-row">
            <dt>{{ 'supplierIq.sourceEvidence.qualityIssueCount' | translate }}</dt>
            <dd>—</dd>
          </div>
        </dl>
      </section>

      <!-- Confidence rating -->
      <footer class="scorecard-footer">
        <span>{{ 'supplierIq.confidence.label' | translate }}: —</span>
      </footer>
    </main>
  `,
  styles: [
    `
      .scorecard-page {
        padding-inline: 1.5rem;
        padding-block: 1.5rem;
        max-width: 1024px;
        margin-inline: auto;
      }

      .back-link {
        margin-block-end: 1rem;
      }

      .page-header {
        margin-block-end: 1.5rem;
      }

      .page-header h1 {
        font-size: 1.75rem;
        font-weight: 500;
        margin: 0;
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
      }

      .metrics-section,
      .risk-section,
      .evidence-section {
        margin-block-end: 2rem;
      }

      .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 1rem;
        margin-block-start: 1rem;
      }

      .metric-card {
        cursor: default;
      }

      .metric-card:focus {
        outline: 2px solid currentColor;
        outline-offset: 2px;
      }

      .metric-value {
        font-size: 1.5rem;
        font-weight: 600;
        padding-block-start: 0.5rem;
      }

      .evidence-row {
        display: flex;
        justify-content: space-between;
        padding-block: 0.5rem;
        border-block-end: 1px solid var(--mat-divider-color, #e0e0e0);
      }

      .scorecard-footer {
        color: var(--mat-hint-color, #757575);
        font-size: 0.875rem;
        margin-block-start: 1rem;
      }
    `,
  ],
})
export class SupplierScorecardComponent {
  private readonly route = inject(ActivatedRoute);

  /** Supplier ID extracted from the route parameter. */
  readonly supplierId = signal<string>('');

  /** Placeholder: true when evidence is insufficient to show scores. */
  readonly isInsufficient = signal<boolean>(true);

  constructor() {
    this.route.paramMap.subscribe((params) => {
      this.supplierId.set(params.get('id') ?? '');
    });
  }
}
