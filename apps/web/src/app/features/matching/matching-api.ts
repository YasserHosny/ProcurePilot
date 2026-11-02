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
  BulkConfirmResult,
  LandedCost,
  QuotationLineMatchState,
  QuotationMatches,
  ProductCreate,
  PackDefinition,
  Money,
  ApiError,
} from '../../core/api/models';

import type { Observable } from 'rxjs';
import type { TranslateService } from '@ngx-translate/core';
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

export function formatSweptLinesMessage(
  translate: TranslateService,
  sweptLines?: readonly string[] | null,
): string | null {
  const count = sweptLines?.length ?? 0;
  if (count <= 0) {
    return null;
  }
  const locale = translate.getCurrentLang() || translate.getFallbackLang() || 'en';
  const category = new Intl.PluralRules(locale).select(count);
  return translate.instant(`matching.sweptLines.${category}`, { count });
}

export function appendSweptMessage(base: string, swept: string): string {
  const trimmed = base.trim();
  const sep = trimmed.endsWith('.') || trimmed.endsWith('۔') || trimmed.endsWith('!') ? ' ' : '. ';
  return `${trimmed}${sep}${swept}`;
}
