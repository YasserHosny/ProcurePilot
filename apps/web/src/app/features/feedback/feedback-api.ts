import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, retry, throwError, timer } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { Locale, Role } from '../../core/api/models';
import { I18nService } from '../../core/i18n';

export type FeedbackCategory = 'bug' | 'idea' | 'question' | 'other';
export type FeedbackStatus = 'new' | 'reviewed' | 'resolved';

export const FEEDBACK_CATEGORIES: readonly FeedbackCategory[] = ['bug', 'idea', 'question', 'other'];
export const FEEDBACK_STATUSES: readonly FeedbackStatus[] = ['new', 'reviewed', 'resolved'];

export interface FeedbackAttachment {
  readonly id: string;
  readonly kind: 'image' | 'audio';
  readonly content_type: string;
  readonly size_bytes: number;
  readonly display_order: number;
}

/** Tenant-facing view. The API never sends operator labels to members or owners. */
export interface Submission {
  readonly id: string;
  readonly text: string;
  readonly category?: FeedbackCategory | null;
  readonly status: FeedbackStatus;
  /** Present in the owner inbox. */
  readonly submitter_name?: string;
  readonly member_role: Role;
  readonly page_path: string;
  readonly locale: Locale;
  readonly created_at: string;
  /** True only for the submitter while the status is `new`. */
  readonly can_withdraw?: boolean;
  readonly attachments: readonly FeedbackAttachment[];
}

export interface SubmissionPage {
  readonly items: readonly Submission[];
  readonly next_cursor?: string | null;
  readonly total?: number | null;
}

export interface SignedUrl {
  readonly url: string;
  readonly expires_in: number;
}

export interface SubmitFeedbackInput {
  readonly text: string;
  readonly category: FeedbackCategory | null;
  readonly images: readonly File[];
  readonly audio: File | null;
}

export interface ListParams {
  readonly cursor?: string | null;
  readonly limit?: number;
}

export interface WorkspaceListParams extends ListParams {
  readonly status?: FeedbackStatus | null;
  readonly category?: FeedbackCategory | null;
}

/** A dropped connection is the one failure worth replaying: the Idempotency-Key makes it safe. */
const RETRY_DELAY_MS = 800;

@Injectable({ providedIn: 'root' })
export class FeedbackApiService {
  private readonly http = inject(HttpClient);
  private readonly i18n = inject(I18nService);
  private readonly base = `${environment.apiBaseUrl}/feedback`;

  /** One key per composition: a retry of the same draft must not create a second submission. */
  newIdempotencyKey(): string {
    return crypto.randomUUID();
  }

  submit(input: SubmitFeedbackInput, idempotencyKey: string): Observable<Submission> {
    const form = new FormData();
    form.append('text', input.text);
    if (input.category) form.append('category', input.category);
    for (const image of input.images) form.append('images', image, image.name);
    if (input.audio) form.append('audio', input.audio, input.audio.name);

    // Content-Type is deliberately not set: the browser adds the multipart boundary.
    const headers = new HttpHeaders({
      'Idempotency-Key': idempotencyKey,
      'Accept-Language': this.i18n.currentLocale(),
    });
    return this.http.post<Submission>(this.base, form, { headers }).pipe(
      retry({
        count: 1,
        delay: (error: { status?: number }) =>
          error.status === 0 ? timer(RETRY_DELAY_MS) : throwError(() => error),
      }),
    );
  }

  listMine(params: ListParams = {}): Observable<SubmissionPage> {
    return this.http.get<SubmissionPage>(`${this.base}/mine`, { params: listParams(params) });
  }

  /** Owner inbox. The API answers 404 to every other role. */
  listWorkspace(params: WorkspaceListParams = {}): Observable<SubmissionPage> {
    let query = listParams(params);
    if (params.status) query = query.set('status', params.status);
    if (params.category) query = query.set('category', params.category);
    return this.http.get<SubmissionPage>(this.base, { params: query });
  }

  get(id: string): Observable<Submission> {
    return this.http.get<Submission>(`${this.base}/${encodeURIComponent(id)}`);
  }

  withdraw(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${encodeURIComponent(id)}`);
  }

  attachmentUrl(id: string, attachmentId: string): Observable<SignedUrl> {
    return this.http.get<SignedUrl>(
      `${this.base}/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}/url`,
    );
  }
}

function listParams(params: ListParams): HttpParams {
  let query = new HttpParams();
  if (params.cursor) query = query.set('cursor', params.cursor);
  if (params.limit) query = query.set('limit', String(params.limit));
  return query;
}
