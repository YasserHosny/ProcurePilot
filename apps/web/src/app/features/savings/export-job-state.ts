import type { ExportFormat, ExportJob } from './exports-api';

export type ExportJobUIState =
  | 'idle'
  | 'submitting'
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_empty'
  | 'failed';

export interface ExportFormValue {
  format: ExportFormat;
  period_start: string;
  period_end: string;
  supplier_id: string | null;
}

export function determineExportJobUIState(
  job: ExportJob | null,
  isSubmitting: boolean,
): ExportJobUIState {
  if (isSubmitting) return 'submitting';
  if (!job) return 'idle';

  switch (job.status) {
    case 'queued':
      return 'queued';
    case 'running':
      return 'running';
    case 'completed':
      if (job.row_count === 0) {
        return 'completed_empty';
      }
      return 'completed';
    case 'failed':
      return 'failed';
    default:
      return 'idle';
  }
}
