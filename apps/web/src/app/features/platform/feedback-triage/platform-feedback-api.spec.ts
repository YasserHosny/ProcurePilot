import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../../environments/environment';
import { PlatformFeedbackApiService, nextStatuses } from './platform-feedback-api';

describe('PlatformFeedbackApiService', () => {
  let api: PlatformFeedbackApiService;
  let http: HttpTestingController;
  const base = `${environment.apiBaseUrl}/platform/feedback`;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(PlatformFeedbackApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('lists with only the filters that are set, using contract parameter names', () => {
    api.list({ status: 'new', category: 'bug', tenantId: 't-1', isDemo: false }, 'cur', 10).subscribe();
    const req = http.expectOne((r) => r.url === base);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('status')).toBe('new');
    expect(req.request.params.get('category')).toBe('bug');
    expect(req.request.params.get('tenant_id')).toBe('t-1');
    expect(req.request.params.get('is_demo')).toBe('false');
    expect(req.request.params.get('cursor')).toBe('cur');
    expect(req.request.params.get('limit')).toBe('10');
    req.flush({ items: [] });
  });

  it('omits unset filters', () => {
    api.list({ status: null, isDemo: null }).subscribe();
    const req = http.expectOne((r) => r.url === base);
    expect(req.request.params.keys().sort()).toEqual(['limit']);
    req.flush({ items: [] });
  });

  it('gets one submission', () => {
    api.get('abc').subscribe();
    const req = http.expectOne(`${base}/abc`);
    expect(req.request.method).toBe('GET');
    req.flush({});
  });

  it('patches status and labels', () => {
    api.update('abc', { status: 'reviewed', labels: ['x'] }).subscribe();
    const req = http.expectOne(`${base}/abc`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ status: 'reviewed', labels: ['x'] });
    req.flush({});
  });

  it('fetches a signed attachment url', () => {
    api.attachmentUrl('abc', 'att').subscribe();
    const req = http.expectOne(`${base}/abc/attachments/att/url`);
    expect(req.request.method).toBe('GET');
    req.flush({ url: 'https://x', expires_in: 300 });
  });

  it('puts the digest preference', () => {
    api.setDigestPreference(true, 'ar').subscribe();
    const req = http.expectOne(`${base}/digest-preference`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ enabled: true, locale: 'ar' });
    req.flush({ digest_enabled: true, digest_locale: 'ar' });
  });

  it('only offers forward status moves', () => {
    expect(nextStatuses('new')).toEqual(['reviewed', 'resolved']);
    expect(nextStatuses('reviewed')).toEqual(['resolved']);
    expect(nextStatuses('resolved')).toEqual([]);
  });
});
