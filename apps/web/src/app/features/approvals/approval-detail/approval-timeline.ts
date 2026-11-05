import type { PurchaseRequest } from '../../../core/api/models';

export interface TimelineEvent {
  readonly key: 'submitted' | 'routed' | 'awaiting' | 'approved' | 'rejected' | 'withdrawn';
  readonly name?: string;
  readonly at?: string;
  readonly reason?: string;
  readonly comment?: string | null;
  readonly selfMark?: string;
  readonly order: number;
}

/** Derives history solely from the request snapshot; never supplies missing timestamps. */
export function buildApprovalTimeline(request: PurchaseRequest | null, unavailable: string): readonly TimelineEvent[] {
  if (!request) return [];
  const events: TimelineEvent[] = [];
  const step = request.approval_step;
  if (request.submitted_at) {
    events.push({key: 'submitted', name: request.requester_name || request.requester_email || unavailable,
      at: request.submitted_at, order: Date.parse(request.submitted_at)});
  }
  if (step) {
    // No routing timestamp is carried by the API. The sort anchor preserves causal order;
    // it is never rendered as a time, nor taken from another table.
    events.push({key: 'routed', name: step.assigned_name || step.assigned_email || unavailable,
      reason: step.source, order: request.submitted_at ? Date.parse(request.submitted_at) : Number.NEGATIVE_INFINITY});
    if (step.status === 'pending' && request.status === 'submitted') {
      events.push({key: 'awaiting', name: step.assigned_name || step.assigned_email || unavailable,
        order: Number.POSITIVE_INFINITY, selfMark: step.self_approval ? 'requests.approval.selfApprovalPending' : undefined});
    } else if (step.status !== 'pending') {
      events.push({key: step.status, name: step.decided_name || step.decided_email || unavailable,
        at: step.decided_at ?? undefined, order: step.decided_at ? Date.parse(step.decided_at) : Number.POSITIVE_INFINITY,
        comment: step.comment, selfMark: step.self_approval
          ? step.status === 'approved' ? 'requests.approval.selfApproved' : 'requests.approval.selfRejected'
          : undefined});
    }
  }
  if (request.withdrawn_at) {
    events.push({key: 'withdrawn', at: request.withdrawn_at, order: Date.parse(request.withdrawn_at)});
  }
  return events.sort((a, b) => a.order - b.order);
}
