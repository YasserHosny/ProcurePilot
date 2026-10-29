/**
 * Matching API models and helper types for Chunk 4.4 (Matching & Normalisation).
 *
 * Fully typed against specs/004-matching-normalisation/contracts/matching.openapi.yaml.
 */

export type {
  MatchOutcome,
  MatchTaskStatus,
  MatchTaskPriority,
  MatchTaskReason,
  ProductSummary,
  QuotationLineSummary,
  FeatureScore,
  RfqMatchReason,
  MatchReason,
  MatchCandidate,
  MatchDecision,
  MatchTask,
  MatchResolutionRequest,
  MatchCorrectionRequest,
  MatchCorrectionResponse,
  LandedCost,
  QuotationLineMatchState,
  QuotationMatches,
  ProductCreate,
  PackDefinition,
  Money,
  ApiError,
} from '../../core/api/models';

import type { Observable } from 'rxjs';
import type { ApiService } from '../../core/api/api.service';
import type { MatchCorrectionRequest, MatchCorrectionResponse } from '../../core/api/models';

export function correctMatch(
  api: ApiService,
  lineId: string,
  body: MatchCorrectionRequest,
  idempotencyKey?: string,
): Observable<MatchCorrectionResponse> {
  return api.correctMatch(lineId, body, idempotencyKey);
}
