import type { BasketSplitJob } from '../offers-api';

export type BasketSplitUIState =
  | 'idle'
  | 'submitting'
  | 'queued'
  | 'running'
  | 'completed_feasible'
  | 'completed_infeasible'
  | 'failed';

export interface BasketSplitFormItem {
  workspace_product_id: string;
  quantity: string;
}

export function determineBasketSplitUIState(
  job: BasketSplitJob | null,
  isSubmitting: boolean,
): BasketSplitUIState {
  if (isSubmitting) return 'submitting';
  if (!job) return 'idle';

  switch (job.status) {
    case 'queued':
      return 'queued';
    case 'running':
      return 'running';
    case 'completed':
      if (job.result && job.result.feasible) {
        return 'completed_feasible';
      }
      return 'completed_infeasible';
    case 'failed':
      return 'failed';
    default:
      return 'idle';
  }
}
