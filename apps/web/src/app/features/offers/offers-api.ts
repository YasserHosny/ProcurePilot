import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  AllocatedBasketLine,
  ApiError,
  BasketItemRequest,
  BasketOptimiseRequest,
  BasketSplitJob,
  BasketSplitJobStatus,
  BasketSplitResult,
  InfeasibleBasketItem,
  Money,
  Offer,
  OfferComparison,
  PriceHistoryMetric,
  PriceHistoryPoint,
  PriceHistoryResponse,
  PriceHistorySummary,
  ProductRef,
  OptimisationConstraint,
  OptimisationWeights,
  Recommendation,
  RecommendationConfidence,
  RecommendationEvidence,
  RecommendationRiskNote,
  RecommendationTieBreak,
  RecommendationWeights,
  RiskTolerance,
  SingleSupplierBaseline,
  StockSignal,
  SupplierAllocation,
  UrgencyLevel,
  ViolatedOptimisationConstraint,
} from '../../core/api/models';

export type {
  ProductRef,
  StockSignal,
  Offer,
  RecommendationConfidence,
  RecommendationRiskNote,
  RecommendationWeights,
  RecommendationTieBreak,
  RecommendationEvidence,
  Recommendation,
  OfferComparison,
  PriceHistoryPoint,
  PriceHistoryMetric,
  PriceHistorySummary,
  PriceHistoryResponse,
  BasketItemRequest,
  BasketOptimiseRequest,
  OptimisationWeights,
  RiskTolerance,
  UrgencyLevel,
  OptimisationConstraint,
  ViolatedOptimisationConstraint,
  AllocatedBasketLine,
  SupplierAllocation,
  SingleSupplierBaseline,
  InfeasibleBasketItem,
  BasketSplitResult,
  BasketSplitJobStatus,
  BasketSplitJob,
  Money,
  ApiError,
};

@Injectable({ providedIn: 'root' })
export class OffersApiService {
  private readonly api = inject(ApiService);

  getOffers(params: {
    product_id: string;
    quantity: string;
    include_expired?: boolean;
    cursor?: string;
    limit?: number;
  }): Observable<{ items: Offer[]; next_cursor: string | null }> {
    return this.api.getOffers(params);
  }

  compareOffers(params: {
    product_id: string;
    quantity: string;
  }): Observable<OfferComparison> {
    return this.api.compareOffers(params);
  }

  getPriceHistory(
    productId: string,
    params?: {
      supplier_id?: string;
      window_months?: number;
      cursor?: string;
      limit?: number;
    },
  ): Observable<PriceHistoryResponse> {
    return this.api.getPriceHistory(productId, params);
  }

  optimiseBasket(
    body: BasketOptimiseRequest,
    idempotencyKey?: string,
  ): Observable<BasketSplitJob> {
    return this.api.optimiseBasket(body, idempotencyKey);
  }

  getBasketSplitJob(id: string): Observable<BasketSplitJob> {
    return this.api.getBasketSplitJob(id);
  }
}
