import { CursorPager } from './cursor-pager';

describe('CursorPager', () => {
  const KEY = 'pp.pageSize.spec-list';
  const page = (count: number, next: string | null, total: number | null = null) => ({
    items: Array.from({ length: count }),
    next_cursor: next,
    total,
  });

  beforeEach(() => localStorage.removeItem(KEY));

  it('starts on the first page at 25 rows with no cursor', () => {
    const pager = new CursorPager('spec-list');
    expect(pager.params()).toEqual({ limit: 25 });
    expect(pager.hasPrevious()).toBeFalse();
    expect(pager.hasNext()).toBeFalse();
  });

  it('walks forward and back through visited cursors and computes the range', () => {
    const pager = new CursorPager('spec-list');
    pager.loaded(page(25, 'c2', 60));
    expect([pager.from(), pager.to(), pager.total()]).toEqual([1, 25, 60]);

    expect(pager.goNext()).toBeTrue();
    expect(pager.params()).toEqual({ cursor: 'c2', limit: 25 });
    pager.loaded(page(25, 'c3', 60));
    expect(pager.goNext()).toBeTrue();
    pager.loaded(page(10, null, 60));
    expect([pager.from(), pager.to()]).toEqual([51, 60]);
    expect(pager.goNext()).toBeFalse();

    expect(pager.goPrevious()).toBeTrue();
    expect(pager.params()).toEqual({ cursor: 'c2', limit: 25 });
    expect(pager.goPrevious()).toBeTrue();
    expect(pager.params()).toEqual({ limit: 25 });
    expect(pager.goPrevious()).toBeFalse();
  });

  it('a page-size change starts again from the first page and is remembered per list', () => {
    const pager = new CursorPager('spec-list');
    pager.loaded(page(25, 'c2'));
    pager.goNext();
    expect(pager.setPageSize(50)).toBeTrue();
    expect(pager.params()).toEqual({ limit: 50 });
    expect(new CursorPager('spec-list').pageSize()).toBe(50);
    expect(new CursorPager('another-list').pageSize()).toBe(25);
  });

  it('ignores sizes outside the options and a stored size it does not offer', () => {
    localStorage.setItem(KEY, '7');
    const pager = new CursorPager('spec-list');
    expect(pager.pageSize()).toBe(25);
    expect(pager.setPageSize(1000)).toBeFalse();
    expect(pager.setPageSize(25)).toBeFalse();
  });

  it('revert undoes the last move after a failed load, and only once', () => {
    const pager = new CursorPager('spec-list');
    pager.loaded(page(25, 'c2', 30));
    pager.goNext();
    expect(pager.revert()).toBeTrue();
    expect(pager.params()).toEqual({ limit: 25 });
    expect(pager.nextCursor()).toBe('c2');
    expect(pager.revert()).toBeFalse();

    pager.setPageSize(10);
    expect(pager.revert()).toBeTrue();
    expect(pager.pageSize()).toBe(25);
    expect(localStorage.getItem(KEY)).toBe('25');
  });

  it('a successful load or a reset leaves nothing to revert', () => {
    const pager = new CursorPager('spec-list');
    pager.loaded(page(25, 'c2'));
    pager.goNext();
    pager.loaded(page(5, null));
    expect(pager.revert()).toBeFalse();
    pager.goPrevious();
    pager.reset();
    expect(pager.revert()).toBeFalse();
  });

  it('is needed only when there is more than one page or more rows than the smallest size', () => {
    const pager = new CursorPager('spec-list');
    pager.loaded(page(8, null));
    expect(pager.needed()).toBeFalse();
    pager.loaded(page(12, null));
    expect(pager.needed()).toBeTrue();
    pager.loaded(page(3, 'c2'));
    expect(pager.needed()).toBeTrue();
  });

  it('an empty page past the first steps back and asks the host to load again', () => {
    const pager = new CursorPager('spec-list');
    pager.loaded(page(25, 'c2', 26));
    pager.goNext();
    expect(pager.loaded(page(1, null, 26))).toBeTrue();

    // The last row was withdrawn: page 2 is now empty.
    expect(pager.loaded(page(0, null, null))).toBeFalse();
    expect(pager.params()).toEqual({ limit: 25 });
    expect(pager.loaded(page(25, null, 25))).toBeTrue();
    expect([pager.from(), pager.to(), pager.total()]).toEqual([1, 25, 25]);
  });

  it('an empty first page is simply empty', () => {
    const pager = new CursorPager('spec-list');
    expect(pager.loaded(page(0, null, 0))).toBeTrue();
    expect(pager.needed()).toBeFalse();
  });

  it('failed() keeps the rows after a failed move, and resets the pager otherwise', () => {
    const pager = new CursorPager('spec-list');
    pager.loaded(page(25, 'c2', 26));
    pager.goNext();
    expect(pager.failed()).toBeTrue();
    expect(pager.params()).toEqual({ limit: 25 });

    pager.goNext();
    pager.loaded(page(1, null, 26));
    expect(pager.failed()).toBeFalse();
    expect([pager.pageIndex(), pager.count(), pager.total(), pager.needed()]).toEqual([0, 0, null, false]);
  });
});
