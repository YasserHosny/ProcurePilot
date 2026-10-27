import type { RecommendationConfidence, StockSignal } from './offers-api';

/**
 * Helper formatting utilities for Smart Compare & Intelligence.
 */

export function formatScorePercent(score: string | number | null | undefined): string {
  if (score === null || score === undefined || score === '') return '—';
  const num = typeof score === 'number' ? score : parseFloat(score);
  if (isNaN(num)) return '—';
  return `${(num * 100).toFixed(1)}%`;
}

export function formatConfidenceClass(confidence: RecommendationConfidence): string {
  switch (confidence) {
    case 'high':
      return 'confidence-high';
    case 'medium':
      return 'confidence-medium';
    case 'low':
      return 'confidence-low';
    default:
      return '';
  }
}

export function formatStockSignal(signal: StockSignal | null | undefined): string {
  // Always unknown in Chunk 4.5
  return signal ?? 'unknown';
}
