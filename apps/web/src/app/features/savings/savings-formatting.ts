import type { BaselinePolicy, Money, PurchaseDeliveryResult, SavingStatus } from './savings-api';

export function getSavingStatusClass(status: SavingStatus): string {
  switch (status) {
    case 'verified':
      return 'status-verified';
    case 'pending':
    default:
      return 'status-pending';
  }
}

export function getDeliveryResultClass(result: PurchaseDeliveryResult): string {
  switch (result) {
    case 'delivered':
      return 'delivery-delivered';
    case 'partially_delivered':
      return 'delivery-partial';
    case 'ordered':
      return 'delivery-ordered';
    case 'cancelled':
      return 'delivery-cancelled';
    case 'disputed':
      return 'delivery-disputed';
    default:
      return 'delivery-default';
  }
}

export function getBaselinePolicyClass(policy: BaselinePolicy): string {
  switch (policy) {
    case 'last_paid':
      return 'policy-last-paid';
    case 'rolling_average_6m':
      return 'policy-rolling-avg';
    case 'none_available':
    default:
      return 'policy-none';
  }
}

export function getDeltaClass(delta: Money | null | undefined): 'positive-delta' | 'negative-delta' | 'zero-delta' {
  if (!delta || !delta.amount) return 'zero-delta';
  const val = parseFloat(delta.amount);
  if (isNaN(val) || Math.abs(val) < 0.0001) return 'zero-delta';
  if (val > 0) return 'positive-delta';
  return 'negative-delta';
}

export function isPositiveSaving(delta: Money | null | undefined): boolean {
  if (!delta || !delta.amount) return false;
  const val = parseFloat(delta.amount);
  return !isNaN(val) && val > 0.0001;
}

export function isNegativeSaving(delta: Money | null | undefined): boolean {
  if (!delta || !delta.amount) return false;
  const val = parseFloat(delta.amount);
  return !isNaN(val) && val < -0.0001;
}
