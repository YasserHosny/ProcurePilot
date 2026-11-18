import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../../packages/i18n/en.json';
import { environment } from '../../../../../environments/environment';
import type { OperatorSubmission } from '../platform-feedback-api';
import { FeedbackDetailComponent } from './feedback-detail.component';

const base = `${environment.apiBaseUrl}/platform/feedback`;

function submission(over: Partial<OperatorSubmission> = {}): OperatorSubmission {
  return {
    id: 'f1',
    text: 'The basket page freezes',
    category: 'bug',
    status: 'new',
    submitter_name: 'Mona Ali',
    submitter_email: 'mona@example.test',
    member_role: 'buyer',
    page_path: '/offers/basket-split',
    locale: 'en',
    created_at: '2026-11-18T10:00:00Z',
    attachments: [
      { id: 'a1', kind: 'image', content_type: 'image/png', size_bytes: 10, display_order: 0 },
      { id: 'a2', kind: 'audio', content_type: 'audio/webm', size_bytes: 10, display_order: 0 },
    ],
    tenant_id: 't1',
    tenant_name: 'Sanad Restaurants',
    labels: ['ux'],
    app_version: '1.2.3',
    is_demo: false,
    status_changed_at: null,
    ...over,
  };
}

describe('FeedbackDetailComponent', () => {
  let fixture: ComponentFixture<FeedbackDetailComponent>;
  let http: HttpTestingController;
  let el: HTMLElement;

  function open(item: OperatorSubmission = submission()): void {
    fixture.componentRef.setInput('feedbackId', item.id);
    fixture.detectChanges();
    http.expectOne(`${base}/${item.id}`).flush(item);
    for (const att of item.attachments) {
      http
        .expectOne(`${base}/${item.id}/attachments/${att.id}/url`)
        .flush({ url: `https://files.example.test/${att.id}?sig=1`, expires_in: 300 });
    }
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FeedbackDetailComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideTranslateService(),
      ],
    }).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(FeedbackDetailComponent);
    el = fixture.nativeElement as HTMLElement;
  });

  afterEach(() => http.verify());

  it('shows the submitter name and email', () => {
    open();
    expect(el.querySelector('[data-testid="detail-name"]')?.textContent).toContain('Mona Ali');
    expect(el.querySelector('[data-testid="detail-email"]')?.textContent).toContain(
      'mona@example.test',
    );
    expect(el.querySelector('[data-testid="detail-text"]')?.textContent).toContain(
      'The basket page freezes',
    );
  });

  it('renders screenshots and audio from signed URLs', () => {
    open();
    const img = el.querySelector('img');
    expect(img?.getAttribute('src')).toBe('https://files.example.test/a1?sig=1');
    const audio = el.querySelector('audio');
    expect(audio?.getAttribute('src')).toBe('https://files.example.test/a2?sig=1');
  });

  it('shows a message for an attachment whose URL cannot be fetched', () => {
    fixture.componentRef.setInput('feedbackId', 'f1');
    fixture.detectChanges();
    http.expectOne(`${base}/f1`).flush(submission());
    http
      .expectOne(`${base}/f1/attachments/a1/url`)
      .flush({}, { status: 404, statusText: 'Not Found' });
    http.expectOne(`${base}/f1/attachments/a2/url`).flush({ url: 'https://x.test/a2', expires_in: 300 });
    fixture.detectChanges();
    expect(el.querySelector('img')).toBeNull();
    expect(el.textContent).toContain(enCatalog.platform.feedback.detail.attachmentError);
  });

  it('offers only forward status moves', () => {
    open(submission({ status: 'reviewed' }));
    expect(el.querySelector('[data-testid="move-reviewed"]')).toBeNull();
    expect(el.querySelector('[data-testid="move-new"]')).toBeNull();
    expect(el.querySelector('[data-testid="move-resolved"]')).not.toBeNull();
  });

  it('offers no move once resolved', () => {
    open(submission({ status: 'resolved' }));
    expect(el.querySelector('[data-testid^="move-"]')).toBeNull();
    expect(el.textContent).toContain(enCatalog.platform.feedback.actions.final);
  });

  it('patches the status and emits the saved record', () => {
    open();
    const emitted: OperatorSubmission[] = [];
    fixture.componentInstance.updated.subscribe((s) => emitted.push(s));
    el.querySelector<HTMLButtonElement>('[data-testid="move-reviewed"]')!.click();
    const req = http.expectOne(`${base}/f1`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ status: 'reviewed' });
    req.flush(submission({ status: 'reviewed' }));
    fixture.detectChanges();
    expect(emitted[0].status).toBe('reviewed');
    expect(el.querySelector('[data-testid="move-reviewed"]')).toBeNull();
  });

  it('refreshes and explains when the server refuses a backward or stale move', () => {
    open();
    el.querySelector<HTMLButtonElement>('[data-testid="move-reviewed"]')!.click();
    http
      .expectOne(`${base}/f1`)
      .flush(
        { code: 'feedback.invalid_transition', message: 'no', trace_id: 't' },
        { status: 409, statusText: 'Conflict' },
      );
    http.expectOne(`${base}/f1`).flush(submission({ status: 'resolved' }));
    fixture.detectChanges();
    expect(el.querySelector('[data-testid="action-error"]')?.textContent).toContain(
      enCatalog.platform.feedback.actions.invalidTransition,
    );
    expect(el.querySelector('[data-testid^="move-"]')).toBeNull();
  });

  it('adds a trimmed label by sending the full list', () => {
    open();
    fixture.componentInstance.labelDraft.set('  pricing ');
    fixture.componentInstance.addLabel();
    const req = http.expectOne(`${base}/f1`);
    expect(req.request.body).toEqual({ labels: ['ux', 'pricing'] });
    req.flush(submission({ labels: ['ux', 'pricing'] }));
    fixture.detectChanges();
    expect(fixture.componentInstance.labelDraft()).toBe('');
    expect(el.textContent).toContain('pricing');
  });

  it('rejects duplicate, over-long and surplus labels without calling the API', () => {
    open(submission({ labels: ['ux', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i'] }));
    const c = fixture.componentInstance;
    c.labelDraft.set('UX');
    c.addLabel();
    expect(c.labelProblem()).toBe('duplicate');
    c.labelDraft.set('x'.repeat(41));
    c.addLabel();
    expect(c.labelProblem()).toBe('tooLong');
    c.labelDraft.set('new-one');
    c.addLabel();
    expect(c.labelProblem()).toBe('max');
  });

  it('removes a label', () => {
    open();
    fixture.componentInstance.removeLabel('ux');
    const req = http.expectOne(`${base}/f1`);
    expect(req.request.body).toEqual({ labels: [] });
    req.flush(submission({ labels: [] }));
  });

  it('shows a retry when the record cannot be loaded', () => {
    fixture.componentRef.setInput('feedbackId', 'f9');
    fixture.detectChanges();
    http.expectOne(`${base}/f9`).flush({}, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain(
      enCatalog.platform.feedback.detail.loadError,
    );
  });

  it('asks the filter-workspace output for the item workspace', () => {
    open();
    let emitted = '';
    fixture.componentInstance.filterWorkspace.subscribe((id) => (emitted = id));
    el.querySelector<HTMLButtonElement>('.link-button')!.click();
    expect(emitted).toBe('t1');
  });
});
