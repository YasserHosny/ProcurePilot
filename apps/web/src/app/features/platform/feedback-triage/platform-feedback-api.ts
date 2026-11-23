import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../../environments/environment';

/** Contract: specs/025-user-feedback/contracts/feedback.openapi.yaml (`/platform/feedback`). */
export type FeedbackStatus = 'new' | 'reviewed' | 'resolved';
export type FeedbackCategory = 'bug' | 'idea' | 'question' | 'other';

export const FEEDBACK_STATUSES: readonly FeedbackStatus[] = ['new', 'reviewed', 'resolved'];
export const FEEDBACK_CATEGORIES: readonly FeedbackCategory[] = ['bug', 'idea', 'question', 'other'];
export const MAX_LABELS = 10;
export const MAX_LABEL_LENGTH = 40;

export interface FeedbackAttachment {
  readonly id: string;
  readonly kind: 'image' | 'audio';
  readonly content_type: string;
  readonly size_bytes: number;
  readonly display_order: number;
}

export interface OperatorSubmission {
  readonly id: string;
  readonly text: string;
  readonly category?: FeedbackCategory | null;
  readonly status: FeedbackStatus;
  readonly submitter_name: string;
  readonly submitter_email: string;
  readonly member_role: string;
  readonly page_path: string;
  readonly locale: 'en' | 'ar';
  readonly created_at: string;
  readonly attachments: readonly FeedbackAttachment[];
  readonly tenant_id: string;
  readonly tenant_name?: string;
  readonly labels: readonly string[];
  readonly app_version: string;
  readonly is_demo: boolean;
  readonly status_changed_at?: string | null;
}

export interface OperatorSubmissionPage {
  readonly items: readonly OperatorSubmission[];
  readonly next_cursor?: string | null;
  readonly total?: number | null;
}

export interface OperatorMe {
  readonly digest_enabled: boolean;
  readonly digest_locale: 'en' | 'ar';
}

export interface SignedUrl {
  readonly url: string;
  readonly expires_in: number;
}

export interface FeedbackFilters {
  readonly status?: FeedbackStatus | null;
  readonly category?: FeedbackCategory | null;
  readonly tenantId?: string | null;
  /** `true` = demo workspaces only, `false` = real workspaces only, null/undefined = both. */
  readonly isDemo?: boolean | null;
}

export interface FeedbackPatch {
  readonly status?: FeedbackStatus;
  readonly labels?: readonly string[];
}

/** Statuses an item may move to from `current`: forward only (data-model.md state machine). */
export function nextStatuses(current: FeedbackStatus): readonly FeedbackStatus[] {
  const index = FEEDBACK_STATUSES.indexOf(current);
  return FEEDBACK_STATUSES.slice(index + 1);
}

@Injectable({ providedIn: 'root' })
export class PlatformFeedbackApiService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBaseUrl}/platform/feedback`;

  list(
    filters: FeedbackFilters,
    cursor?: string | null,
    limit = 25,
  ): Observable<OperatorSubmissionPage> {
    let params = new HttpParams().set('limit', String(limit));
    if (cursor) params = params.set('cursor', cursor);
    if (filters.status) params = params.set('status', filters.status);
    if (filters.category) params = params.set('category', filters.category);
    if (filters.tenantId) params = params.set('tenant_id', filters.tenantId);
    if (filters.isDemo !== null && filters.isDemo !== undefined) {
      params = params.set('is_demo', String(filters.isDemo));
    }
    return this.http.get<OperatorSubmissionPage>(this.base, { params });
  }

  get(id: string): Observable<OperatorSubmission> {
    return this.http.get<OperatorSubmission>(`${this.base}/${id}`);
  }

  update(id: string, patch: FeedbackPatch): Observable<OperatorSubmission> {
    return this.http.patch<OperatorSubmission>(`${this.base}/${id}`, patch);
  }

  attachmentUrl(id: string, attachmentId: string): Observable<SignedUrl> {
    return this.http.get<SignedUrl>(`${this.base}/${id}/attachments/${attachmentId}/url`);
  }

  setDigestPreference(enabled: boolean, locale?: 'en' | 'ar'): Observable<OperatorMe> {
    const body: { enabled: boolean; locale?: 'en' | 'ar' } = locale
      ? { enabled, locale }
      : { enabled };
    return this.http.put<OperatorMe>(`${this.base}/digest-preference`, body);
  }
}
