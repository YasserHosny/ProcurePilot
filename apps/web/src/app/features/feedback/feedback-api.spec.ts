import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';

import { I18nService } from '../../core/i18n';
import { FeedbackApiService, type Submission } from './feedback-api';

const submission: Submission = {
  id: '11111111-1111-4111-8111-111111111111',
  text: 'Hello',
  category: null,
  status: 'new',
  member_role: 'buyer',
  page_path: '/home',
  locale: 'en',
  created_at: '2026-11-18T10:00:00Z',
  can_withdraw: true,
  attachments: [],
};

describe('FeedbackApiService', () => {
  let api: FeedbackApiService;
  let http: HttpTestingController;
  const locale = signal<'en' | 'ar'>('ar');

  beforeEach(() => {
    locale.set('ar');
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: I18nService, useValue: { currentLocale: locale } },
      ],
    });
    api = TestBed.inject(FeedbackApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('posts multipart form data with the Idempotency-Key and the UI language', () => {
    const png = new File([new Uint8Array(4)], 'a.png', { type: 'image/png' });
    const audio = new File([new Uint8Array(4)], 'v.webm', { type: 'audio/webm' });
    let result: Submission | undefined;
    api
      .submit({ text: 'Broken', category: 'bug', images: [png], audio }, 'key-1')
      .subscribe((s) => (result = s));

    const req = http.expectOne('/api/v1/feedback');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('Idempotency-Key')).toBe('key-1');
    expect(req.request.headers.get('Accept-Language')).toBe('ar');
    const body = req.request.body as FormData;
    expect(body.get('text')).toBe('Broken');
    expect(body.get('category')).toBe('bug');
    expect(body.getAll('images').length).toBe(1);
    expect((body.get('images') as File).name).toBe('a.png');
    expect((body.get('audio') as File).name).toBe('v.webm');
    req.flush(submission, { status: 201, statusText: 'Created' });
    expect(result).toEqual(submission);
  });

  it('omits category and attachments that were not chosen', () => {
    api.submit({ text: 'Idea', category: null, images: [], audio: null }, 'key-2').subscribe();
    const req = http.expectOne('/api/v1/feedback');
    const body = req.request.body as FormData;
    expect(body.has('category')).toBeFalse();
    expect(body.has('images')).toBeFalse();
    expect(body.has('audio')).toBeFalse();
    req.flush(submission, { status: 201, statusText: 'Created' });
  });

  it('retries once with the same key when the connection drops', fakeAsync(() => {
    let result: Submission | undefined;
    api
      .submit({ text: 'x', category: null, images: [], audio: null }, 'key-3')
      .subscribe((s) => (result = s));
    http.expectOne('/api/v1/feedback').error(new ProgressEvent('error'), { status: 0 });
    tick(1000);
    const retry = http.expectOne('/api/v1/feedback');
    expect(retry.request.headers.get('Idempotency-Key')).toBe('key-3');
    retry.flush(submission, { status: 200, statusText: 'OK' });
    expect(result).toEqual(submission);
  }));

  it('fails after the one retry also drops', fakeAsync(() => {
    let status: number | undefined;
    api.submit({ text: 'x', category: null, images: [], audio: null }, 'key-4').subscribe({
      error: (e: { status: number }) => (status = e.status),
    });
    http.expectOne('/api/v1/feedback').error(new ProgressEvent('error'), { status: 0 });
    tick(1000);
    http.expectOne('/api/v1/feedback').error(new ProgressEvent('error'), { status: 0 });
    expect(status).toBe(0);
  }));

  it('does not retry a refusal such as the cooldown', () => {
    let status: number | undefined;
    api.submit({ text: 'x', category: null, images: [], audio: null }, 'key-5').subscribe({
      error: (e: { status: number }) => (status = e.status),
    });
    http.expectOne('/api/v1/feedback').flush(
      {
        code: 'feedback.cooldown',
        message: 'wait',
        details: { retry_after_seconds: 12 },
        trace_id: 't',
      },
      { status: 429, statusText: 'Too Many Requests' },
    );
    expect(status).toBe(429);
  });

  it("lists the caller's own submissions with cursor and limit", () => {
    api.listMine({ cursor: 'abc', limit: 10 }).subscribe();
    const req = http.expectOne((r) => r.url === '/api/v1/feedback/mine');
    expect(req.request.params.get('cursor')).toBe('abc');
    expect(req.request.params.get('limit')).toBe('10');
    req.flush({ items: [submission], next_cursor: null });
  });

  it('lists the workspace inbox with filters', () => {
    api.listWorkspace({ status: 'new', category: 'bug' }).subscribe();
    const req = http.expectOne((r) => r.url === '/api/v1/feedback');
    expect(req.request.params.get('status')).toBe('new');
    expect(req.request.params.get('category')).toBe('bug');
    expect(req.request.params.has('cursor')).toBeFalse();
    req.flush({ items: [], next_cursor: null });
  });

  it('reads, withdraws and signs attachment links', () => {
    api.get('abc').subscribe();
    http.expectOne('/api/v1/feedback/abc').flush(submission);

    api.withdraw('abc').subscribe();
    const del = http.expectOne('/api/v1/feedback/abc');
    expect(del.request.method).toBe('DELETE');
    del.flush(null, { status: 204, statusText: 'No Content' });

    let url = '';
    api.attachmentUrl('abc', 'att').subscribe((r) => (url = r.url));
    http
      .expectOne('/api/v1/feedback/abc/attachments/att/url')
      .flush({ url: 'https://files.example/x', expires_in: 300 });
    expect(url).toBe('https://files.example/x');
  });

  it('generates a fresh UUID key for every composition', () => {
    const a = api.newIdempotencyKey();
    const b = api.newIdempotencyKey();
    expect(a).toMatch(/^[0-9a-f-]{36}$/);
    expect(a).not.toBe(b);
  });
});
