import { signal } from '@angular/core';
import { type Observable, Subscription } from 'rxjs';

import { CursorPager } from '../../layout/list-pager/cursor-pager';
import type { Submission, SubmissionPage } from './feedback-api';

/**
 * Cursor-paged list state shared by the member list and the owner inbox. A newer request
 * supersedes an older one, so a slow response for a previous filter never overwrites the list.
 */
export class PagedSubmissions {
  readonly items = signal<readonly Submission[]>([]);
  readonly loading = signal(false);
  readonly failed = signal(false);
  readonly pager: CursorPager;

  private inFlight: Subscription | null = null;

  constructor(
    key: string,
    private readonly fetch: (params: ReturnType<CursorPager['params']>) => Observable<SubmissionPage>,
  ) {
    this.pager = new CursorPager(key);
  }

  resetAndReload(): void {
    this.items.set([]);
    this.pager.reset();
    this.reload();
  }

  remove(id: string): void {
    this.items.update((list) => list.filter((item) => item.id !== id));
    this.reload();
  }

  reload(): void {
    this.inFlight?.unsubscribe();
    const request = new Subscription();
    this.inFlight = request;
    this.loading.set(true);
    this.failed.set(false);
    request.add(
      this.fetch(this.pager.params()).subscribe({
        next: (page) => {
          if (!this.pager.loaded({ ...page, next_cursor: page.next_cursor ?? null })) {
            this.reload();
            return;
          }
          this.items.set(page.items);
          this.loading.set(false);
        },
        error: () => {
          if (!this.pager.failed()) this.items.set([]);
          this.failed.set(true);
          this.loading.set(false);
        },
      }),
    );
  }
}
