import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { environment } from '../../../../environments/environment';
import { OperatorService } from '../../../core/auth/operator.service';
import { SessionService } from '../../../core/auth/session.service';
import { FeedbackTriageComponent } from './feedback-triage.component';
import type { OperatorSubmission } from './platform-feedback-api';

const base = `${environment.apiBaseUrl}/platform/feedback`;

function item(id: string, over: Partial<OperatorSubmission> = {}): OperatorSubmission {
  return {
    id,
    text: `Message ${id}`,
    category: null,
    status: 'new',
    submitter_name: `User ${id}`,
    submitter_email: `${id}@example.test`,
    member_role: 'owner',
    page_path: '/home',
    locale: 'en',
    created_at: '2026-11-18T10:00:00Z',
    attachments: [],
    tenant_id: 't1',
    tenant_name: 'Sanad',
    labels: [],
    app_version: '1',
    is_demo: false,
    ...over,
  };
}

describe('FeedbackTriageComponent', () => {
  let fixture: ComponentFixture<FeedbackTriageComponent>;
  let component: FeedbackTriageComponent;
  let http: HttpTestingController;
  let el: HTMLElement;
  const WS = '0b0e6c6e-5f0a-4a43-9d0e-1d2f3a4b5c6d';

  function flushList(items: OperatorSubmission[], next: string | null = null): void {
    http.expectOne((r) => r.url === base && r.method === 'GET').flush({ items, next_cursor: next });
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FeedbackTriageComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideTranslateService(),
        {
          provide: SessionService,
          useValue: { currentMember: signal({ id: 'u1' }), activeLocale: signal('ar') },
        },
      ],
    }).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(OperatorService).updateProfile({ digest_enabled: false, digest_locale: 'en' });
    fixture = TestBed.createComponent(FeedbackTriageComponent);
    component = fixture.componentInstance;
    el = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('loads and lists feedback across workspaces', () => {
    flushList([item('a'), item('b', { tenant_name: 'Rawaq', is_demo: true })]);
    const rows = el.querySelectorAll('[data-testid="feedback-row"]');
    expect(rows.length).toBe(2);
    expect(rows[1].textContent).toContain('Rawaq');
    expect(rows[1].textContent).toContain(enCatalog.platform.feedback.detail.demoBadge);
  });

  it('shows the empty state', () => {
    flushList([]);
    expect(el.querySelector('[data-testid="empty"]')).not.toBeNull();
  });

  it('shows an error with retry when the list fails', () => {
    http
      .expectOne((r) => r.url === base)
      .flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain(
      enCatalog.platform.feedback.loadError,
    );
    component.reload();
    flushList([item('a')]);
    expect(el.querySelectorAll('[data-testid="feedback-row"]').length).toBe(1);
  });

  it('applies status, category and demo filters and restarts the list', () => {
    flushList([item('a')]);
    component.setStatus('reviewed');
    let req = http.expectOne((r) => r.url === base);
    expect(req.request.params.get('status')).toBe('reviewed');
    req.flush({ items: [] });
    component.setCategory('bug');
    req = http.expectOne((r) => r.url === base);
    expect(req.request.params.get('status')).toBe('reviewed');
    expect(req.request.params.get('category')).toBe('bug');
    req.flush({ items: [] });
    component.setDemo('demo');
    req = http.expectOne((r) => r.url === base);
    expect(req.request.params.get('is_demo')).toBe('true');
    req.flush({ items: [] });
    expect(component.items().length).toBe(0);
  });

  it('filters by a valid workspace id and refuses a malformed one', () => {
    flushList([]);
    component.workspaceDraft.set('not-a-uuid');
    component.applyWorkspace();
    http.expectNone((r) => r.url === base);
    expect(component.workspaceInvalid()).toBeTrue();

    component.workspaceDraft.set(WS);
    component.applyWorkspace();
    const req = http.expectOne((r) => r.url === base);
    expect(req.request.params.get('tenant_id')).toBe(WS);
    req.flush({ items: [] });
  });

  it('clears all filters', () => {
    flushList([]);
    component.filterToWorkspace(WS);
    http.expectOne((r) => r.url === base).flush({ items: [] });
    component.clearFilters();
    const req = http.expectOne((r) => r.url === base);
    expect(req.request.params.has('tenant_id')).toBeFalse();
    expect(req.request.params.has('status')).toBeFalse();
    req.flush({ items: [] });
  });

  it('pages with the cursor and appends', () => {
    flushList([item('a')], 'c1');
    (el.querySelector('[data-testid="load-more"]') as HTMLButtonElement).click();
    const req = http.expectOne((r) => r.url === base);
    expect(req.request.params.get('cursor')).toBe('c1');
    req.flush({ items: [item('b')], next_cursor: null });
    fixture.detectChanges();
    expect(component.items().map((i) => i.id)).toEqual(['a', 'b']);
    expect(el.querySelector('[data-testid="load-more"]')).toBeNull();
  });

  it('opens the detail pane for the picked row and reflects status changes in the list', () => {
    flushList([item('a')]);
    (el.querySelector('.open-row') as HTMLButtonElement).click();
    fixture.detectChanges();
    http.expectOne(`${base}/a`).flush(item('a'));
    fixture.detectChanges();
    expect(el.querySelector('[data-testid="detail-email"]')?.textContent).toContain('a@example.test');

    (el.querySelector('[data-testid="move-reviewed"]') as HTMLButtonElement).click();
    http.expectOne(`${base}/a`).flush(item('a', { status: 'reviewed' }));
    fixture.detectChanges();
    expect(component.items()[0].status).toBe('reviewed');
  });

  it('turns the digest on for the caller with their language', () => {
    flushList([]);
    component.setDigest(true);
    const req = http.expectOne(`${base}/digest-preference`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ enabled: true, locale: 'ar' });
    req.flush({ digest_enabled: true, digest_locale: 'ar' });
    expect(component.digestEnabled()).toBeTrue();
  });

  it('keeps the old digest value and shows an error when saving fails', () => {
    flushList([]);
    component.setDigest(true);
    http.expectOne(`${base}/digest-preference`).flush({}, { status: 500, statusText: 'x' });
    fixture.detectChanges();
    expect(component.digestEnabled()).toBeFalse();
    expect(el.textContent).toContain(enCatalog.platform.feedback.digest.error);
  });
});
