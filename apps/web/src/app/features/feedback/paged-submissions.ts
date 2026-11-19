import { signal } from '@angular/core';
import type { Observable, Subscription } from 'rxjs';

import type { Submission, SubmissionPage } from './feedback-api';

export const FEEDBACK_PAGE_SIZE = 10;

/**
 * Cursor-paged list state shared by the member list and the owner inbox. A newer request
 * supersedes an older one, so a slow response for a previous filter never overwrites the list.
 */
export class PagedSubmissions {
  readonly items = signal<readonly Submission[]>([]);
  readonly loading = signal(false);
  readonly failed = signal(false);
  readonly nextCursor = signal<string | null>(null);

  private inFlight: Subscription | null = null;

  constructor(private readonly fetch: (cursor: string | null) => Observable<SubmissionPage>) {}

  /** Starts again from the first page. */
  reload(): void {
    this.run(null, true);
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (cursor && !this.loading()) this.run(cursor, false);
  }

  remove(id: string): void {
    this.items.update((list) => list.filter((item) => item.id !== id));
  }

  private run(cursor: string | null, replace: boolean): void {
    this.inFlight?.unsubscribe();
    this.loading.set(true);
    this.failed.set(false);
    this.inFlight = this.fetch(cursor).subscribe({
      next: (page) => {
        this.items.update((list) => (replace ? [...page.items] : [...list, ...page.items]));
        this.nextCursor.set(page.next_cursor ?? null);
        this.loading.set(false);
      },
      error: () => {
        this.failed.set(true);
        this.loading.set(false);
      },
    });
  }
}
