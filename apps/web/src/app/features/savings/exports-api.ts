import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  ExportCreate,
  ExportFilters,
  ExportFormat,
  ExportJob,
  ExportStatus,
} from '../../core/api/models';

export type {
  ExportFormat,
  ExportStatus,
  ExportFilters,
  ExportCreate,
  ExportJob,
};

@Injectable({ providedIn: 'root' })
export class ExportsApiService {
  private readonly api = inject(ApiService);

  createExport(body: ExportCreate, idempotencyKey?: string): Observable<ExportJob> {
    return this.api.createExport(body, idempotencyKey);
  }

  getExportJob(id: string): Observable<ExportJob> {
    return this.api.getExportJob(id);
  }
}
