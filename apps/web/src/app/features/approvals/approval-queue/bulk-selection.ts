import type { BulkApprovalDecisionInput, Money, PurchaseRequest } from '../../../core/api/models';

export const BULK_SELECTION_LIMIT = 25;

/** Exact decimal arithmetic within each currency; the API carries up to four places. */
export function selectionCurrencyTotals(requests: readonly PurchaseRequest[]): Money[] {
  const totals = new Map<string, bigint>();
  for (const request of requests) {
    const value = request.estimated_total;
    if (!value) continue;
    const negative = value.amount.startsWith('-');
    const [whole, fraction = ''] = value.amount.replace(/^-/, '').split('.');
    const amount = BigInt(whole + fraction.padEnd(6, '0')) * (negative ? -1n : 1n);
    totals.set(value.currency, (totals.get(value.currency) ?? 0n) + amount);
  }
  return [...totals].sort(([a], [b]) => a.localeCompare(b)).map(([currency, total]) => {
    const digits = (total < 0n ? -total : total).toString().padStart(7, '0');
    const fraction = digits.slice(-6).replace(/0+$/, '');
    return {currency, amount: `${total < 0n ? '-' : ''}${digits.slice(0, -6)}${fraction ? '.' + fraction : ''}`};
  });
}

export function bulkAttemptSignature(body: BulkApprovalDecisionInput): string {
  return JSON.stringify([body.decision, body.comment, [...body.request_ids].sort()]);
}

export function bulkFailureKey(code: string | null): string {
  switch (code) {
    case 'group_request_use_group_decision': return 'approvals.bulk.reasons.group';
    case 'self_decision_not_allowed': return 'approvals.bulk.reasons.self';
    case 'not_found': return 'approvals.bulk.reasons.notFound';
    case 'unavailable': return 'approvals.bulk.reasons.unavailable';
    case 'conflict':
    case 'not_submitted':
    case 'no_pending_approval': return 'approvals.bulk.reasons.notPending';
    case 'auth.permission_denied': return 'approvals.bulk.reasons.notAllowed';
    default: return 'approvals.bulk.reasons.generic';
  }
}
