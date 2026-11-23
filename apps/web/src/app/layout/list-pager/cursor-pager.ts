import { computed, signal } from '@angular/core';

export const PAGE_SIZE_OPTIONS: readonly number[] = [10, 25, 50];
export const DEFAULT_PAGE_SIZE = 25;

/** The shape every cursor-paged list endpoint returns. */
export interface CursorPage {
  readonly items: readonly unknown[];
  readonly next_cursor: string | null;
  readonly total?: number | null;
}

/**
 * Previous/Next paging over a cursor API (PPS-228).
 *
 * The API hands out only a next cursor, so Previous walks back through the cursors of the
 * pages already visited. That works the same for offset and keyset cursors. Page size is
 * remembered per list in the browser; a size change starts again from the first page.
 */
export class CursorPager {
  readonly pageSize = signal<number>(DEFAULT_PAGE_SIZE);
  readonly nextCursor = signal<string | null>(null);
  readonly total = signal<number | null>(null);
  readonly count = signal<number>(0);
  private readonly cursors = signal<readonly (string | null)[]>([null]);
  private undo: { cursors: readonly (string | null)[]; pageSize: number; nextCursor: string | null } | null =
    null;

  readonly pageIndex = computed(() => this.cursors().length - 1);
  readonly cursor = computed(() => this.cursors()[this.cursors().length - 1]);
  readonly hasPrevious = computed(() => this.pageIndex() > 0);
  readonly hasNext = computed(() => this.nextCursor() !== null);
  readonly from = computed(() => (this.count() ? this.pageIndex() * this.pageSize() + 1 : 0));
  readonly to = computed(() => (this.count() ? this.from() + this.count() - 1 : 0));
  /** Whether there is anything to page: more than one page, or a page already left. */
  readonly needed = computed(() => this.hasPrevious() || this.hasNext() || this.count() > PAGE_SIZE_OPTIONS[0]);

  constructor(private readonly storageKey: string) {
    const stored = Number(readStorage(this.key));
    if (PAGE_SIZE_OPTIONS.includes(stored)) this.pageSize.set(stored);
  }

  /** Query parameters for the current page. */
  params(): { cursor?: string; limit: number } {
    const cursor = this.cursor();
    return cursor ? { cursor, limit: this.pageSize() } : { limit: this.pageSize() };
  }

  /**
   * Records the page the API returned for the current cursor. Returns false when a page past
   * the first came back empty (the list shrank, e.g. its last row was withdrawn): the pager
   * has stepped back one page and the host should load again instead of showing «no results».
   */
  loaded(page: CursorPage): boolean {
    this.undo = null;
    if (page.items.length === 0 && this.hasPrevious()) {
      this.cursors.update((stack) => stack.slice(0, -1));
      return false;
    }
    this.count.set(page.items.length);
    this.nextCursor.set(page.next_cursor);
    this.total.set(page.total ?? null);
    return true;
  }

  /**
   * After a failed load. Returns true when it undid a Previous / Next / size move, so the host
   * keeps the rows on screen; otherwise it resets the pager (no stale range or controls) and
   * returns false, so the host clears the rows.
   */
  failed(): boolean {
    if (this.revert()) return true;
    this.reset();
    return false;
  }

  /** Back to the first page, as after a filter or sort change. */
  reset(): void {
    this.undo = null;
    this.cursors.set([null]);
    this.nextCursor.set(null);
    this.total.set(null);
    this.count.set(0);
  }

  goNext(): boolean {
    const next = this.nextCursor();
    if (!next) return false;
    this.remember();
    this.cursors.update((stack) => [...stack, next]);
    return true;
  }

  goPrevious(): boolean {
    if (!this.hasPrevious()) return false;
    this.remember();
    this.cursors.update((stack) => stack.slice(0, -1));
    return true;
  }

  setPageSize(size: number): boolean {
    if (!PAGE_SIZE_OPTIONS.includes(size) || size === this.pageSize()) return false;
    const before = { cursors: this.cursors(), pageSize: this.pageSize(), nextCursor: this.nextCursor() };
    this.pageSize.set(size);
    writeStorage(this.key, String(size));
    this.cursors.set([null]);
    this.undo = before;
    return true;
  }

  /**
   * Undoes the last Previous / Next / page-size move after its page failed to load, so the
   * rows still on screen and the range keep matching. True when there was a move to undo.
   */
  revert(): boolean {
    const undo = this.undo;
    if (!undo) return false;
    this.undo = null;
    this.cursors.set(undo.cursors);
    this.nextCursor.set(undo.nextCursor);
    if (undo.pageSize !== this.pageSize()) {
      this.pageSize.set(undo.pageSize);
      writeStorage(this.key, String(undo.pageSize));
    }
    return true;
  }

  private remember(): void {
    this.undo = { cursors: this.cursors(), pageSize: this.pageSize(), nextCursor: this.nextCursor() };
  }

  private get key(): string {
    return `pp.pageSize.${this.storageKey}`;
  }
}

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Private windows and blocked storage: the size still applies for this visit.
  }
}
