import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Product } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { PosApiService, type SyncedProductSignal } from '../../pos/pos-api';
import { formatConfidenceClass, formatScorePercent } from '../offer-formatting';
import type { OfferComparison, Recommendation, RecommendationConfidence } from '../offers-api';
import { type ProjectedOffer, projectComparison } from './compare-projection';
import { CompareRecommendationComponent } from './compare-recommendation.component';
import { CompareTableComponent } from './compare-table.component';

@Component({
  selector: 'app-compare',
  standalone: true,
  imports: [
    FormsModule,
    ReactiveFormsModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCheckboxModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatDatePipe,
    CompareRecommendationComponent,
    CompareTableComponent,
  ],
  templateUrl: './compare.component.html',
  styleUrl: './compare.component.scss',
})
export class CompareComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly posApi = inject(PosApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(false);
  readonly products = signal<Product[]>([]);
  readonly selectedProductId = signal<string>('');
  readonly productSignal = signal<SyncedProductSignal | null>(null);
  readonly quantityInput = signal<string>('10');
  readonly includeExpired = signal<boolean>(false);
  readonly rawComparison = signal<OfferComparison | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  // Network call counter for testing SC-002
  networkCallCount = 0;

  // Pure client-side instantaneous projection (SC-002: <150ms budget, no network request per keystroke)
  readonly projected = computed(() => {
    return projectComparison(this.rawComparison(), this.quantityInput());
  });

  readonly selectedProduct = computed<Product | null>(() => {
    const id = this.selectedProductId();
    return this.products().find((p) => p.id === id) ?? null;
  });

  readonly displayedColumns = [
    'supplier',
    'unitPrice',
    'landedCost',
    'leadTime',
    'reliability',
    'stockSignal',
    'matchConfidence',
    'validity',
    'status',
    'actions',
  ];

  readonly visibleOffers = computed<readonly ProjectedOffer[]>(() => {
    const proj = this.projected();
    if (!proj) return [];
    if (this.includeExpired()) {
      return proj.offers;
    }
    return proj.offers.filter((o) => !o.is_expired);
  });

  readonly recommendedOffer = computed<ProjectedOffer | null>(() => {
    const proj = this.projected();
    if (!proj || !proj.recommendation) return null;
    return proj.offers.find((o) => o.id === proj.recommendation?.recommended_offer_id) ?? null;
  });

  ngOnInit(): void {
    this.loadProductList();

    this.route.paramMap.subscribe((params) => {
      const id = params.get('id') || params.get('productId');
      if (id) {
        this.selectedProductId.set(id);
        this.fetchComparison(id);
      }
    });

    this.route.queryParamMap.subscribe((queryParams) => {
      const pId = queryParams.get('product_id');
      const qty = queryParams.get('quantity');
      if (qty) {
        this.quantityInput.set(qty);
      }
      if (pId && pId !== this.selectedProductId()) {
        this.selectedProductId.set(pId);
        this.fetchComparison(pId);
      }
    });
  }

  loadProductList(): void {
    this.api.products({ limit: 100, status: 'active' }).subscribe({
      next: (res) => {
        this.products.set(res.items);
        if (!this.selectedProductId() && res.items.length > 0) {
          const firstId = res.items[0].id;
          this.selectedProductId.set(firstId);
          this.fetchComparison(firstId);
        }
      },
      error: () => {
        // Soft fail on product list load
      },
    });
  }

  onProductChange(productId: string): void {
    this.selectedProductId.set(productId);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { product_id: productId, quantity: this.quantityInput() },
      queryParamsHandling: 'merge',
    });
    this.fetchComparison(productId);
  }

  fetchComparison(productId: string): void {
    if (!productId) {
      this.productSignal.set(null);
      return;
    }
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.networkCallCount++;

    this.fetchProductSignal(productId);

    const qty = this.quantityInput() || '10';
    this.api.compareOffers({ product_id: productId, quantity: qty }).subscribe({
      next: (comp) => {
        this.rawComparison.set(comp);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.rawComparison.set(null);
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          this.errorTraceId.set(apiError?.trace_id ?? null);
          if (err.status === 404) {
            this.errorMessage.set(this.translate.instant('compare.empty.message'));
          } else {
            this.errorMessage.set(apiError?.message ?? err.message);
          }
        } else {
          this.errorMessage.set(this.translate.instant('compare.empty.message'));
        }
      },
    });
  }

  fetchProductSignal(productId: string): void {
    if (!productId) {
      this.productSignal.set(null);
      return;
    }
    this.productSignal.set(null);
    this.posApi.listSignals({ workspaceProductId: productId, matchStatus: 'matched' }).subscribe({
      next: (res) => {
        const match = res.items.find((item) => item.matched_workspace_product_id === productId) ?? res.items[0] ?? null;
        this.productSignal.set(match);
      },
      error: () => {
        // Defensive: Absence of POS connection or error renders zero visible difference (FR-007, US3)
        this.productSignal.set(null);
      },
    });
  }

  onQuantityChange(newQty: string): void {
    this.quantityInput.set(newQty);
    // Instant client-side recompute happens automatically through the computed signal `projected`
    // No network request is initiated per keystroke (SC-002).
  }

  toggleIncludeExpired(): void {
    this.includeExpired.update((val) => !val);
  }

  formatScore(score: string | null | undefined): string {
    return formatScorePercent(score);
  }

  getConfidenceClass(confidence: string): string {
    return formatConfidenceClass(confidence as RecommendationConfidence);
  }

  formatPercent(val: string | number | null | undefined): string {
    if (val === null || val === undefined || val === '') return '—';
    const n = typeof val === 'number' ? val : parseFloat(val);
    if (isNaN(n)) return '—';
    return `${(n * 100).toFixed(0)}%`;
  }

  hasSupplierRiskEvidence(rec: Recommendation | null | undefined): boolean {
    if (!rec?.evidence?.components) return false;
    return !!(
      rec.evidence.components['supplier_risk'] ||
      rec.evidence.components['risk_score'] ||
      rec.evidence.components['supplier_iq']
    );
  }

  hasSupplierRiskNote(riskNotes: readonly string[] | undefined): boolean {
    if (!riskNotes) return false;
    return riskNotes.some(
      (note) =>
        note.includes('supplier_risk') ||
        note.includes('quality') ||
        note === 'high_supplier_risk' ||
        note === 'elevated_supplier_risk',
    );
  }

  getSupplierRiskScore(rec: Recommendation | null | undefined): string | null {
    if (!rec?.evidence?.components) return null;
    return (
      rec.evidence.components['supplier_risk'] ||
      rec.evidence.components['risk_score'] ||
      rec.evidence.components['supplier_iq'] ||
      null
    );
  }

  getSupplierRiskWeight(rec: Recommendation | null | undefined): string {
    if (!rec?.evidence?.weights) return '15';
    const rawWeight = (
      rec.evidence.weights['supplier_risk'] ||
      rec.evidence.weights['risk_score'] ||
      rec.evidence.weights['supplier_iq'] ||
      '15'
    );
    const numericWeight = parseFloat(rawWeight);
    if (!isNaN(numericWeight) && numericWeight > 0 && numericWeight <= 1) {
      return `${Math.round(numericWeight * 100)}`;
    }
    return rawWeight;
  }

  getRecordPurchaseParams(offer: ProjectedOffer): Record<string, string> {
    const params: Record<string, string> = {
      product_id: this.selectedProductId(),
      supplier_id: offer.supplier_id,
      quantity: this.quantityInput() || '10',
      unit_price: offer.projected_unit_price.amount,
      currency: offer.projected_unit_price.currency,
      total_paid: offer.projected_landed_cost.amount,
      base_unit: this.selectedProduct()?.base_unit || 'each',
    };
    if (offer.quotation_line_id) {
      params['quotation_line_id'] = offer.quotation_line_id;
    }
    if (offer.match_decision_id) {
      params['match_decision_id'] = offer.match_decision_id;
    }
    if (offer.id) {
      params['landed_cost_id'] = offer.id;
    }
    return params;
  }
}
