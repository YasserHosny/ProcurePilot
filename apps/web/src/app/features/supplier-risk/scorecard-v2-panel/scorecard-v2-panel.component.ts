import { Component, computed, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import type {
  SupplierRiskComponentV2,
  SupplierRiskEvidenceRefV2,
  SupplierScorecard,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { SupplierRiskApiService } from '../supplier-risk-api';

const COMPONENT_KEYS = [
  'concentration',
  'price_drift',
  'reliability',
  'single_source',
] as const;

type ComponentKey = (typeof COMPONENT_KEYS)[number];

@Component({
  selector: 'app-scorecard-v2-panel',
  standalone: true,
  imports: [
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './scorecard-v2-panel.component.html',
  styleUrl: './scorecard-v2-panel.component.scss',
})
export class ScorecardV2PanelComponent {
  private readonly api = inject(SupplierRiskApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  readonly scorecard = input.required<SupplierScorecard>();
  readonly supplierId = input.required<string>();
  readonly isPreparing = signal(false);
  readonly prepareFailed = signal(false);
  readonly isWriter = computed(() => this.session.hasRole('owner', 'buyer'));
  readonly componentRows = computed(() =>
    COMPONENT_KEYS.map((key) => ({
      key,
      value: this.scorecard().v2_components?.[key],
    })),
  );
  readonly hasV2 = computed(() => Boolean(this.scorecard().snapshot_id));
  readonly isStale = computed(() => {
    const validUntil = this.scorecard().valid_until;
    return validUntil ? Date.parse(validUntil) <= Date.now() : true;
  });
  readonly canPrepare = computed(() => {
    const card = this.scorecard();
    return (
      this.isWriter() &&
      Boolean(card.snapshot_id) &&
      (card.state === 'ready' || card.state === 'provisional') &&
      card.v2_risk_score !== null &&
      card.v2_risk_score !== undefined &&
      !this.isStale()
    );
  });

  prepareBrief(): void {
    if (!this.canPrepare() || this.isPreparing()) return;
    this.prepareFailed.set(false);
    this.isPreparing.set(true);
    this.api.prepareBrief(this.supplierId()).subscribe({
      next: (brief) => {
        this.isPreparing.set(false);
        void this.router.navigate(['/negotiation-briefs', brief.id]);
      },
      error: () => {
        this.isPreparing.set(false);
        this.prepareFailed.set(true);
      },
    });
  }

  weight(key: ComponentKey): string | null {
    return this.scorecard().v2_weights?.[key] ?? null;
  }

  excluded(component: SupplierRiskComponentV2 | undefined): [string, number][] {
    return component ? Object.entries(component.excluded_counts) : [];
  }

  percent(value: string | null | undefined): string {
    if (value === null || value === undefined) return '-';
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(1)}%` : '-';
  }

  sourceRoute(ref: SupplierRiskEvidenceRefV2): string[] | null {
    if (ref.source_kind === 'purchase_order') return ['/orders', ref.source_id];
    if (ref.source_kind === 'workspace_product') return ['/products', ref.source_id];
    return null;
  }
}
