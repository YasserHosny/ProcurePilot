import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n';
import type { Submission } from '../feedback-api';
import { WorkspaceFeedbackComponent } from './workspace-feedback.component';

const en = enCatalog.feedback;

function submission(over: Partial<Submission> = {}): Submission {
  return {
    id: 'sub-1',
    text: 'Approvals are slow',
    category: 'idea',
    status: 'new',
    submitter_name: 'Mona Adel',
    member_role: 'approver',
    page_path: '/approvals',
    locale: 'en',
    created_at: '2026-11-18T10:00:00Z',
    can_withdraw: false,
    attachments: [],
    ...over,
  };
}

describe('WorkspaceFeedbackComponent (owner inbox, read-only, FR-013)', () => {
  let fixture: ComponentFixture<WorkspaceFeedbackComponent>;
  let http: HttpTestingController;

  const root = (): HTMLElement => fixture.nativeElement as HTMLElement;
  const text = (): string => (root().textContent ?? '').replace(/\s+/g, ' ');
  const listReq = (): ReturnType<HttpTestingController['expectOne']> =>
    http.expectOne((r) => r.url === '/api/v1/feedback' && r.method === 'GET');

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceFeedbackComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        provideTranslateService(),
        { provide: I18nService, useValue: { currentLocale: signal('en') } },
      ],
    }).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(WorkspaceFeedbackComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('lists every member\'s feedback with who sent it and their role', () => {
    listReq().flush({ items: [submission(), submission({ id: 'sub-2', submitter_name: 'Omar', member_role: 'viewer' })], next_cursor: null });
    fixture.detectChanges();
    expect(text()).toContain('Mona Adel (Approver)');
    expect(text()).toContain('Omar (Viewer)');
    expect(text()).toContain(en.list.workspaceIntro);
  });

  it('offers no way to change status, label or delete, not even to withdraw', () => {
    listReq().flush({
      items: [submission({ can_withdraw: true })],
      next_cursor: null,
    });
    fixture.detectChanges();
    expect(root().querySelector('[data-test="withdraw"]')).toBeNull();
    const buttons = Array.from(root().querySelectorAll('button')).map((b) => b.textContent!.trim());
    expect(buttons.filter((b) => /delete|label|resolve|withdraw/i.test(b))).toEqual([]);
  });

  it('filters by status and category and refetches from the first page', () => {
    listReq().flush({ items: [submission()], next_cursor: 'c' });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.onStatusFilter('new');
    const byStatus = listReq();
    expect(byStatus.request.params.get('status')).toBe('new');
    expect(byStatus.request.params.has('cursor')).toBeFalse();
    byStatus.flush({ items: [], next_cursor: null });

    component.onCategoryFilter('bug');
    const both = listReq();
    expect(both.request.params.get('status')).toBe('new');
    expect(both.request.params.get('category')).toBe('bug');
    both.flush({ items: [], next_cursor: null });
    fixture.detectChanges();
    expect(text()).toContain(en.list.emptyWorkspace);
  });

  it('loads more with the cursor', () => {
    listReq().flush({ items: [submission()], next_cursor: 'cur-2' });
    fixture.detectChanges();
    root().querySelector<HTMLButtonElement>('[data-test="load-more"]')!.click();
    const next = listReq();
    expect(next.request.params.get('cursor')).toBe('cur-2');
    next.flush({ items: [submission({ id: 'sub-3' })], next_cursor: null });
    fixture.detectChanges();
    expect(root().querySelectorAll('[data-test="card"]').length).toBe(2);
  });

  it('shows an error with retry when the inbox cannot be loaded', () => {
    listReq().flush({ code: 'not_found', message: 'x', trace_id: 't' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();
    expect(text()).toContain(en.list.loadError);
    expect(root().querySelector('[data-test="retry"]')).not.toBeNull();
  });
});
