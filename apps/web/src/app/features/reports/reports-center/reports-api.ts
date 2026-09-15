import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../../environments/environment';

export type ReportKind = 'savings_ledger' | 'spend_by_supplier' | 'alerts_summary';
export type ReportFormat = 'csv' | 'xlsx' | 'pdf';
export type ReportScheduleStatus = 'active' | 'paused';
export type ReportArtifactStatus = 'queued' | 'running' | 'completed' | 'failed' | 'expired';

export interface ReportScheduleFilters {
  supplier_id?: string | null;
  branch_id?: string | null;
}

export interface ReportArtifactFilters {
  period_start?: string | null;
  period_end?: string | null;
  supplier_id?: string | null;
  branch_id?: string | null;
}

export interface ReportSchedule {
  id: string;
  kind: ReportKind;
  format: ReportFormat;
  weekday: number;
  filters: ReportScheduleFilters;
  filters_digest?: string;
  locale: 'en' | 'ar';
  status?: ReportScheduleStatus;
  is_active?: boolean;
  next_run_at: string;
  last_run_at?: string | null;
  rule_version?: string;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportArtifact {
  id: string;
  schedule_id?: string | null;
  kind: ReportKind;
  format: ReportFormat;
  status: ReportArtifactStatus;
  filters: ReportArtifactFilters;
  locale: 'en' | 'ar';
  row_count: number | null;
  rule_version?: string;
  download_url?: string | null;
  expires_at?: string | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ReportScheduleList {
  items: ReportSchedule[];
  next_cursor: string | null;
}

export interface ReportArtifactList {
  items: ReportArtifact[];
  next_cursor: string | null;
}

@Injectable({ providedIn: 'root' })
export class ReportsApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  getSchedules(params?: {
    cursor?: string;
    limit?: number;
  }): Observable<ReportScheduleList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<ReportScheduleList>(`${this.base}/reports/schedules${qs}`);
  }

  getArtifacts(params?: {
    cursor?: string;
    limit?: number;
    kind?: ReportKind;
    status?: ReportArtifactStatus;
  }): Observable<ReportArtifactList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.kind) query.set('kind', params.kind);
    if (params?.status) query.set('status', params.status);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<ReportArtifactList>(`${this.base}/reports/artifacts${qs}`);
  }
}
