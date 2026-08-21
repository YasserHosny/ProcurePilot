import type { Money, RecommendationConfidence, StockSignal } from './offers-api';

/**
 * Helper formatting utilities for Smart Compare & Intelligence.
 */

export function formatMoney(money: Money | null | undefined): string {
  if (!money || money.amount === undefined || money.amount === null) {
    return '—';
  }
  const num = parseFloat(money.amount);
  if (isNaN(num)) {
    return `${money.amount} ${money.currency}`;
  }
  const formatted = num.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
  return `${formatted} ${money.currency}`;
}

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
