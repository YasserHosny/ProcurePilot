import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { SessionService } from '../../../core/auth/session.service';
import { I18nService } from '../../../core/i18n';
import type { Submission } from '../feedback-api';
import { MyFeedbackComponent } from './my-feedback.component';

const en = enCatalog.feedback;

function submission(over: Partial<Submission> = {}): Submission {
  return {
    id: 'sub-1',
    text: 'The totals look wrong',
    category: 'bug',
    status: 'new',
    member_role: 'buyer',
    page_path: '/quotations',
    locale: 'en',
    created_at: '2026-11-18T10:00:00Z',
    can_withdraw: true,
    attachments: [],
    ...over,
  };
}

describe('MyFeedbackComponent (US4, FR-012, FR-014)', () => {
  let fixture: ComponentFixture<MyFeedbackComponent>;
  let http: HttpTestingController;
  let dialogResult: boolean;
  let dialogOpen: jasmine.Spy;
  const isOwner = signal(false);

  const root = (): HTMLElement => fixture.nativeElement as HTMLElement;
  const text = (): string => (root().textContent ?? '').replace(/\s+/g, ' ');
  const mineReq = (): ReturnType<HttpTestingController['expectOne']> =>
    http.expectOne((r) => r.url === '/api/v1/feedback/mine');

  beforeEach(async () => {
    dialogResult = true;
    isOwner.set(false);
    dialogOpen = jasmine.createSpy('open').and.callFake(() => ({ afterClosed: () => of(dialogResult) }));
    await TestBed.configureTestingModule({
      imports: [MyFeedbackComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        provideTranslateService(),
        { provide: I18nService, useValue: { currentLocale: signal('en') } },
        { provide: SessionService, useValue: { hasRole: () => isOwner() } },
        { provide: MatDialog, useValue: { open: dialogOpen } },
      ],
    }).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(MyFeedbackComponent);
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    localStorage.removeItem('pp.pageSize.my-feedback');
  });

  it('lists the member\'s own submissions with text, category, status and page', () => {
    mineReq().flush({
      items: [submission(), submission({ id: 'sub-2', text: 'Add export', category: null, status: 'reviewed', can_withdraw: false })],
      next_cursor: null,
    });
    fixture.detectChanges();
    expect(text()).toContain('The totals look wrong');
    expect(text()).toContain(en.category.bug);
    expect(text()).toContain(en.status.new);
    expect(text()).toContain(en.status.reviewed);
    expect(text()).toContain('/quotations');
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(2);
  });

  it('never shows operator labels even if one were present in the payload', () => {
    mineReq().flush({
      items: [{ ...submission(), labels: ['internal-only'] }],
      next_cursor: null,
    });
    fixture.detectChanges();
    expect(text()).not.toContain('internal-only');
  });

  it('shows an empty state', () => {
    mineReq().flush({ items: [], next_cursor: null });
    fixture.detectChanges();
    expect(text()).toContain(en.list.empty);
  });

  it('shows an error with a retry', () => {
    mineReq().flush({ code: 'x', message: 'x', trace_id: 't' }, { status: 500, statusText: 'Err' });
    fixture.detectChanges();
    expect(text()).toContain(en.list.loadError);
    root().querySelector<HTMLButtonElement>('[data-test="retry"]')!.click();
    mineReq().flush({ items: [submission()], next_cursor: null });
    fixture.detectChanges();
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(1);
  });

  it('pages with Next and Previous, passes limit, and keeps rows when Next fails', () => {
    const page1 = Array.from({ length: 25 }, (_, i) => submission({ id: `sub-${i}`, text: `Item ${i}` }));
    const initial = mineReq();
    expect(initial.request.params.get('limit')).toBe('25');
    initial.flush({ items: page1, next_cursor: 'cur-1', total: 26 });
    fixture.detectChanges();

    const range = (): string | undefined =>
      root().querySelector('.list-pager__range')?.textContent?.trim();
    const nextBtn = (): HTMLButtonElement =>
      root().querySelector('.list-pager__next') as HTMLButtonElement;
    const prevBtn = (): HTMLButtonElement =>
      root().querySelector('.list-pager__previous') as HTMLButtonElement;

    expect(range()).toBe('1–25 of 26');

    nextBtn().click();
    const failNext = mineReq();
    expect(failNext.request.params.get('cursor')).toBe('cur-1');
    expect(failNext.request.params.get('limit')).toBe('25');
    failNext.flush({ code: 'x', message: 'x', trace_id: 't' }, { status: 500, statusText: 'Err' });
    fixture.detectChanges();
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(25);
    expect(componentPageIndex(fixture)).toBe(0);

    nextBtn().click();
    const next = mineReq();
    expect(next.request.params.get('cursor')).toBe('cur-1');
    next.flush({
      items: [submission({ id: 'sub-99', text: 'Second page' })],
      next_cursor: null,
      total: 26,
    });
    fixture.detectChanges();
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(1);
    expect(text()).toContain('Second page');
    expect(range()).toBe('26–26 of 26');

    prevBtn().click();
    const prev = mineReq();
    expect(prev.request.params.has('cursor')).toBeFalse();
    prev.flush({ items: page1, next_cursor: 'cur-1', total: 26 });
    fixture.detectChanges();
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(25);
    expect(range()).toBe('1–25 of 26');
  });

  function componentPageIndex(f: ComponentFixture<MyFeedbackComponent>): number {
    return f.componentInstance.list.pager.pageIndex();
  }

  it('offers withdraw only while the submission can still be withdrawn', () => {
    mineReq().flush({
      items: [
        submission({ id: 'a', can_withdraw: true }),
        submission({ id: 'b', status: 'reviewed', can_withdraw: false }),
      ],
      next_cursor: null,
    });
    fixture.detectChanges();
    expect(root().querySelectorAll('[data-test="withdraw"]').length).toBe(1);
  });

  it('withdraws after confirmation and removes the item', () => {
    mineReq().flush({ items: [submission({ id: 'a' }), submission({ id: 'b', text: 'Keep me' })], next_cursor: null });
    fixture.detectChanges();
    root().querySelector<HTMLButtonElement>('[data-test="withdraw"]')!.click();
    expect(dialogOpen).toHaveBeenCalled();
    const del = http.expectOne('/api/v1/feedback/a');
    expect(del.request.method).toBe('DELETE');
    del.flush(null, { status: 204, statusText: 'No Content' });
    mineReq().flush({ items: [submission({ id: 'b', text: 'Keep me' })], next_cursor: null, total: 1 });
    fixture.detectChanges();
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(1);
    expect(text()).toContain('Keep me');
  });

  it('does nothing when the member cancels the confirmation', () => {
    dialogResult = false;
    mineReq().flush({ items: [submission({ id: 'a' })], next_cursor: null });
    fixture.detectChanges();
    root().querySelector<HTMLButtonElement>('[data-test="withdraw"]')!.click();
    http.expectNone('/api/v1/feedback/a');
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(1);
  });

  it('explains a refused withdrawal (already reviewed) and refreshes the list', () => {
    mineReq().flush({ items: [submission({ id: 'a' })], next_cursor: null });
    fixture.detectChanges();
    root().querySelector<HTMLButtonElement>('[data-test="withdraw"]')!.click();
    http
      .expectOne('/api/v1/feedback/a')
      .flush(
        { code: 'feedback.withdraw_refused', message: 'no', trace_id: 't' },
        { status: 409, statusText: 'Conflict' },
      );
    fixture.detectChanges();
    expect(text()).toContain(en.withdraw.refused);
    mineReq().flush({
      items: [submission({ id: 'a', status: 'reviewed', can_withdraw: false })],
      next_cursor: null,
    });
    fixture.detectChanges();
    expect(root().querySelector('[data-test="withdraw"]')).toBeNull();
  });

  it('links owners to the workspace inbox and nobody else', () => {
    mineReq().flush({ items: [], next_cursor: null });
    fixture.detectChanges();
    expect(root().querySelector('[data-test="workspace-link"]')).toBeNull();

    isOwner.set(true);
    fixture = TestBed.createComponent(MyFeedbackComponent);
    fixture.detectChanges();
    mineReq().flush({ items: [], next_cursor: null });
    fixture.detectChanges();
    expect(root().querySelector('[data-test="workspace-link"]')).not.toBeNull();
  });

  it('shows screenshots and a voice message through signed links', () => {
    mineReq().flush({
      items: [
        submission({
          attachments: [
            { id: 'i1', kind: 'image', content_type: 'image/png', size_bytes: 1, display_order: 1 },
            { id: 'au', kind: 'audio', content_type: 'audio/webm', size_bytes: 1, display_order: 0 },
          ],
        }),
      ],
      next_cursor: null,
    });
    fixture.detectChanges();
    http
      .expectOne('/api/v1/feedback/sub-1/attachments/i1/url')
      .flush({ url: 'https://files.example/i1', expires_in: 300 });
    fixture.detectChanges();
    expect(root().querySelectorAll('app-feedback-attachment').length).toBe(2);
    expect(root().querySelector('img')).not.toBeNull();
    expect(root().querySelector('[data-test="load-audio"]')).not.toBeNull();
  });
});
