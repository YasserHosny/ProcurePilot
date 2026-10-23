import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import type { Session } from '../api/models';
import { authInterceptor } from './auth.interceptor';
import { restoreSessionOnStartup } from './session-initializer';
import { REFRESH_LEAD_MS, SessionService } from './session.service';

/** A JWT-shaped token whose payload carries `exp` (seconds). Signature is irrelevant client-side. */
function jwt(expSecondsFromNow: number, marker = 'x', tenantId?: string): string {
  const exp = Math.floor(Date.now() / 1000) + expSecondsFromNow;
  const payload = btoa(JSON.stringify({ exp, marker, tenant_id: tenantId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `header.${payload}.sig`;
}

function session(access: string, refresh: string): Session {
  return {
    access_token: access,
    refresh_token: refresh,
    expires_in: 3600,
    user: {
      id: 'member',
      email: 'buyer@example.com',
      role: 'buyer',
      preferred_locale: null,
      mfa_enabled: false,
      tenant: {
        id: 'tenant-a',
        name: 'Pilot',
        slug: 'pilot',
        region: 'EG',
        currency: 'EGP',
        tax_model: 'standard',
        default_locale: 'en',
        created_at: '',
      },
    },
  } as unknown as Session;
}

describe('authInterceptor token refresh (demo finding 29)', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let sessionService: SessionService;
  let navigate: jasmine.Spy;

  const expired = jwt(-10, 'old');
  const renewed = jwt(3600, 'new');

  beforeEach(() => {
    localStorage.clear();
    navigate = jasmine.createSpy('navigate').and.resolveTo(true);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate } },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    sessionService = TestBed.inject(SessionService);
    localStorage.setItem('pp.access_token', expired);
    localStorage.setItem('pp.refresh_token', 'refresh-1');
  });

  afterEach(() => {
    sessionService.logout();
    backend.verify();
    localStorage.clear();
  });

  it('on a 401 refreshes once and replays the request with the new token', async () => {
    const result = firstValueFrom(http.get<{ ok: boolean }>('/api/v1/requests'));

    const first = backend.expectOne('/api/v1/requests');
    expect(first.request.headers.get('Authorization')).toBe(`Bearer ${expired}`);
    first.flush({ code: 'auth.unauthenticated' }, { status: 401, statusText: 'Unauthorized' });

    const refresh = backend.expectOne('/api/v1/auth/refresh');
    expect(refresh.request.method).toBe('POST');
    expect(refresh.request.body).toEqual({ refresh_token: 'refresh-1' });
    // The client never names a tenant: the workspace comes back inside the token.
    expect(Object.keys(refresh.request.body as object)).toEqual(['refresh_token']);
    refresh.flush(session(renewed, 'refresh-2'));

    const replay = backend.expectOne('/api/v1/requests');
    expect(replay.request.headers.get('Authorization')).toBe(`Bearer ${renewed}`);
    replay.flush({ ok: true });

    expect(await result).toEqual({ ok: true });
    expect(localStorage.getItem('pp.access_token')).toBe(renewed);
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-2');
    expect(sessionService.tenant()?.id).toBe('tenant-a');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('parallel 401s share a single refresh, then all replay', async () => {
    const results = Promise.all([
      firstValueFrom(http.get('/api/v1/a')),
      firstValueFrom(http.get('/api/v1/b')),
      firstValueFrom(http.get('/api/v1/c')),
    ]);

    for (const url of ['/api/v1/a', '/api/v1/b', '/api/v1/c']) {
      backend.expectOne(url).flush(null, { status: 401, statusText: 'Unauthorized' });
    }

    const refreshes = backend.match('/api/v1/auth/refresh');
    expect(refreshes.length).toBe(1);
    refreshes[0].flush(session(renewed, 'refresh-2'));

    for (const url of ['/api/v1/a', '/api/v1/b', '/api/v1/c']) {
      const replay = backend.expectOne(url);
      expect(replay.request.headers.get('Authorization')).toBe(`Bearer ${renewed}`);
      replay.flush(url);
    }
    expect(await results).toEqual(['/api/v1/a', '/api/v1/b', '/api/v1/c']);
  });

  it('a 401 that lands after a refresh already finished replays without refreshing again', async () => {
    const early = firstValueFrom(http.get('/api/v1/early'));
    const late = firstValueFrom(http.get('/api/v1/late'));

    backend.expectOne('/api/v1/early').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne('/api/v1/auth/refresh').flush(session(renewed, 'refresh-2'));
    backend.expectOne('/api/v1/early').flush('early');

    // Sent with the old token before the refresh completed; its 401 arrives afterwards.
    backend.expectOne('/api/v1/late').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectNone('/api/v1/auth/refresh');
    const lateReplay = backend.expectOne('/api/v1/late');
    expect(lateReplay.request.headers.get('Authorization')).toBe(`Bearer ${renewed}`);
    lateReplay.flush('late');

    expect(await early).toBe('early');
    expect(await late).toBe('late');
  });

  it('signs out and routes to sign-in when the refresh fails', async () => {
    const result = firstValueFrom(http.get('/api/v1/requests'));

    backend.expectOne('/api/v1/requests').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend
      .expectOne('/api/v1/auth/refresh')
      .flush({ code: 'auth.unauthenticated' }, { status: 401, statusText: 'Unauthorized' });

    await expectAsync(result).toBeRejected();
    expect(localStorage.getItem('pp.access_token')).toBeNull();
    expect(localStorage.getItem('pp.refresh_token')).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/auth/sign-in']);
    backend.expectNone('/api/v1/requests');
  });

  it('signs out instead of looping when the replayed request is refused again', async () => {
    const result = firstValueFrom(http.get('/api/v1/requests'));

    backend.expectOne('/api/v1/requests').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne('/api/v1/auth/refresh').flush(session(renewed, 'refresh-2'));
    // e.g. the membership was removed: a fresh token still cannot reach the workspace.
    backend.expectOne('/api/v1/requests').flush(null, { status: 401, statusText: 'Unauthorized' });

    await expectAsync(result).toBeRejected();
    backend.expectNone('/api/v1/auth/refresh');
    expect(navigate).toHaveBeenCalledWith(['/auth/sign-in']);
    expect(localStorage.getItem('pp.access_token')).toBeNull();
  });

  it('does not try to refresh a failed sign-in', async () => {
    const result = firstValueFrom(http.post('/api/v1/auth/login', {}));
    backend.expectOne('/api/v1/auth/login').flush(null, { status: 401, statusText: 'Unauthorized' });

    await expectAsync(result).toBeRejected();
    backend.expectNone('/api/v1/auth/refresh');
  });

  it('an expired password-reset link neither refreshes nor signs the visitor out (PP-28)', async () => {
    const result = firstValueFrom(http.post('/api/v1/auth/password-update', {}));
    backend
      .expectOne('/api/v1/auth/password-update')
      .flush({ code: 'auth.unauthenticated' }, { status: 401, statusText: 'Unauthorized' });

    await expectAsync(result).toBeRejected();
    backend.expectNone('/api/v1/auth/refresh');
    expect(navigate).not.toHaveBeenCalled();
    expect(localStorage.getItem('pp.access_token')).toBe(expired);
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
  });

  it('a 401 from outside our API neither refreshes nor signs out', async () => {
    const result = firstValueFrom(http.get('/i18n/en.json'));
    const req = backend.expectOne('/i18n/en.json');
    expect(req.request.headers.has('Authorization')).toBeFalse();
    req.flush(null, { status: 401, statusText: 'Unauthorized' });

    await expectAsync(result).toBeRejected();
    backend.expectNone('/api/v1/auth/refresh');
    expect(navigate).not.toHaveBeenCalled();
    expect(localStorage.getItem('pp.access_token')).toBe(expired);
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
  });

  it('never sends the bearer token to a presigned storage URL', async () => {
    const url = 'https://storage.example.test/bucket/quote.pdf?X-Amz-Signature=abc';
    const result = firstValueFrom(http.put(url, new Blob(['x'])));
    const req = backend.expectOne(url);
    expect(req.request.headers.has('Authorization')).toBeFalse();
    req.flush(null, { status: 401, statusText: 'Unauthorized' }); // e.g. the URL expired

    await expectAsync(result).toBeRejected();
    expect(navigate).not.toHaveBeenCalled();
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
  });

  it('sends the token to the Storage upload URL our API issued, without touching the session on 401', async () => {
    // documents/service.py `_signed_upload_url`: a Storage object URL authorised by the JWT.
    localStorage.setItem('pp.access_token', renewed);
    const api = TestBed.inject(ApiService);
    const url = 'http://127.0.0.1:54321/storage/v1/object/quotation-documents/t/d/quote.pdf';

    const ok = firstValueFrom(api.uploadFileToStorage(url, new File(['x'], 'quote.pdf')));
    const put = backend.expectOne(url);
    expect(put.request.headers.get('Authorization')).toBe(`Bearer ${renewed}`);
    put.flush(null);
    await ok;

    const fields = firstValueFrom(api.uploadFileToStorage(url, new File(['x'], 'q.pdf'), { k: 'v' }));
    const post = backend.expectOne(url);
    expect(post.request.headers.get('Authorization')).toBe(`Bearer ${renewed}`);
    post.flush(null, { status: 401, statusText: 'Unauthorized' });

    await expectAsync(fields).toBeRejected();
    backend.expectNone('/api/v1/auth/refresh');
    expect(navigate).not.toHaveBeenCalled();
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
  });

  it('does not treat a lookalike path as our API', async () => {
    const result = firstValueFrom(http.get('/api/v1-other/thing'));
    const req = backend.expectOne('/api/v1-other/thing');
    expect(req.request.headers.has('Authorization')).toBeFalse();
    req.flush(null);
    await result;
  });

  it('a rate-limited refresh fails the request but keeps the session', async () => {
    const result = firstValueFrom(http.get('/api/v1/requests'));

    backend.expectOne('/api/v1/requests').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend
      .expectOne('/api/v1/auth/refresh')
      .flush({ code: 'rate_limited' }, { status: 429, statusText: 'Too Many Requests' });

    await expectAsync(result).toBeRejected();
    expect(navigate).not.toHaveBeenCalled();
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
  });

  describe('workspace switch', () => {
    const switchUrl = '/api/v1/me/active-workspace';

    it('with an expired access token, refreshes first and sends the rotated refresh token', async () => {
      const switched = firstValueFrom(sessionService.switchWorkspace('tenant-b'));

      // No doomed PUT with the expired token and the about-to-be-spent refresh token.
      backend.expectNone(switchUrl);
      const refresh = backend.expectOne('/api/v1/auth/refresh');
      expect(refresh.request.body).toEqual({ refresh_token: 'refresh-1' });
      refresh.flush(session(renewed, 'refresh-2'));

      const put = backend.expectOne(switchUrl);
      expect(put.request.headers.get('Authorization')).toBe(`Bearer ${renewed}`);
      expect(put.request.body).toEqual({ tenant_id: 'tenant-b', refresh_token: 'refresh-2' });
      put.flush(session(jwt(3600, 'b'), 'refresh-3'));

      await switched;
      expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-3');
      expect(navigate).not.toHaveBeenCalled();
    });

    it('during an in-flight refresh, waits for it instead of spending the same token', async () => {
      const pending = firstValueFrom(http.get('/api/v1/requests'));
      backend.expectOne('/api/v1/requests').flush(null, { status: 401, statusText: 'Unauthorized' });
      const refresh = backend.expectOne('/api/v1/auth/refresh');

      const switched = firstValueFrom(sessionService.switchWorkspace('tenant-b'));
      backend.expectNone(switchUrl);
      refresh.flush(session(renewed, 'refresh-2'));

      backend.expectOne('/api/v1/requests').flush('ok');
      const put = backend.expectOne(switchUrl);
      expect(put.request.body).toEqual({ tenant_id: 'tenant-b', refresh_token: 'refresh-2' });
      put.flush(session(jwt(3600, 'b'), 'refresh-3'));
      backend.expectNone('/api/v1/auth/refresh');

      expect(await pending).toBe('ok');
      await switched;
      expect(navigate).not.toHaveBeenCalled();
    });

    it('when the PUT itself gets a 401, the replay carries the refresh token the refresh just issued', async () => {
      localStorage.setItem('pp.access_token', jwt(1800, 'revoked-server-side'));
      const switched = firstValueFrom(sessionService.switchWorkspace('tenant-b'));

      const first = backend.expectOne(switchUrl);
      expect(first.request.body).toEqual({ tenant_id: 'tenant-b', refresh_token: 'refresh-1' });
      first.flush(null, { status: 401, statusText: 'Unauthorized' });

      backend.expectOne('/api/v1/auth/refresh').flush(session(renewed, 'refresh-2'));

      const replay = backend.expectOne(switchUrl);
      expect(replay.request.headers.get('Authorization')).toBe(`Bearer ${renewed}`);
      expect(replay.request.body).toEqual({ tenant_id: 'tenant-b', refresh_token: 'refresh-2' });
      replay.flush(session(jwt(3600, 'b'), 'refresh-3'));

      await switched;
      expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-3');
      expect(navigate).not.toHaveBeenCalled();
    });

    it('the proactive refresh stands down while a switch is out', fakeAsync(() => {
      sessionService.adopt(session(jwt(300, 'a'), 'refresh-1'));
      tick(1_000);
      sessionService.switchWorkspace('tenant-b').subscribe();
      const put = backend.expectOne(switchUrl);

      tick(300_000); // the timer for the old token fires mid-switch
      backend.expectNone('/api/v1/auth/refresh');

      put.flush(session(jwt(3600, 'b'), 'refresh-2'));
      expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-2');
      sessionService.logout();
    }));
  });

  it('passes other errors through untouched', async () => {
    const result = firstValueFrom(http.get('/api/v1/requests'));
    backend.expectOne('/api/v1/requests').flush(null, { status: 403, statusText: 'Forbidden' });

    await expectAsync(result).toBeRejected();
    backend.expectNone('/api/v1/auth/refresh');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('on start, renews an expired stored token instead of calling /me with it', async () => {
    const restored = firstValueFrom(TestBed.runInInjectionContext(() => restoreSessionOnStartup()));

    backend.expectNone('/api/v1/me');
    backend.expectOne('/api/v1/auth/refresh').flush(session(renewed, 'refresh-2'));

    expect(await restored).toBeNull();
    expect(sessionService.isAuthenticated()).toBeTrue();
    expect(localStorage.getItem('pp.access_token')).toBe(renewed);
  });

  it('on start, a failed renewal leaves the person signed out, not broken', async () => {
    const restored = firstValueFrom(TestBed.runInInjectionContext(() => restoreSessionOnStartup()));

    backend
      .expectOne('/api/v1/auth/refresh')
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(await restored).toBeNull();
    expect(sessionService.isAuthenticated()).toBeFalse();
    expect(localStorage.getItem('pp.refresh_token')).toBeNull();
  });

  it('on start, a rate-limited renewal keeps the tokens for the next load', async () => {
    const restored = firstValueFrom(TestBed.runInInjectionContext(() => restoreSessionOnStartup()));

    backend
      .expectOne('/api/v1/auth/refresh')
      .flush(null, { status: 429, statusText: 'Too Many Requests' });

    expect(await restored).toBeNull();
    expect(sessionService.isAuthenticated()).toBeFalse();
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
  });

  it('on start, a still-valid token restores through /me without refreshing', async () => {
    localStorage.setItem('pp.access_token', jwt(1800));
    const restored = firstValueFrom(TestBed.runInInjectionContext(() => restoreSessionOnStartup()));

    backend.expectNone('/api/v1/auth/refresh');
    backend.expectOne('/api/v1/me').flush(session('unused', 'unused').user);

    expect(await restored).toBeNull();
    expect(sessionService.isAuthenticated()).toBeTrue();
  });

  it('refreshes proactively shortly before the access token expires', fakeAsync(() => {
    const lifetimeSeconds = 300;
    sessionService.adopt(session(jwt(lifetimeSeconds), 'refresh-1'));

    tick(lifetimeSeconds * 1000 - REFRESH_LEAD_MS - 1_000);
    backend.expectNone('/api/v1/auth/refresh');

    tick(2_000);
    backend.expectOne('/api/v1/auth/refresh').flush(session(renewed, 'refresh-2'));
    expect(localStorage.getItem('pp.access_token')).toBe(renewed);

    sessionService.logout();
  }));

  it('a late timer, visibility wake and interceptor share one refresh after hours idle', fakeAsync(() => {
    sessionService.adopt(session(jwt(300), 'refresh-1'));
    const now = Date.now();
    spyOn(Date, 'now').and.returnValue(now + 8 * 60 * 60 * 1000);
    spyOnProperty(document, 'visibilityState', 'get').and.returnValue('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    const refresh = backend.expectOne('/api/v1/auth/refresh');
    http.get('/api/v1/orders').subscribe();
    backend.expectOne('/api/v1/orders').flush(null, { status: 401, statusText: 'Unauthorized' });
    tick(300_000);
    backend.expectNone('/api/v1/auth/refresh');
    refresh.flush(session(jwt(3600), 'refresh-2'));
    backend.expectOne('/api/v1/orders').flush([]);
    document.dispatchEvent(new Event('visibilitychange'));
    backend.expectNone('/api/v1/auth/refresh');
    expect(sessionService.isAuthenticated()).toBeTrue();
    expect(navigate).not.toHaveBeenCalled();
    sessionService.logout();
  }));

  it('a rejected stale refresh retries once with storage without signing out', fakeAsync(() => {
    http.get('/api/v1/orders').subscribe();
    backend.expectOne('/api/v1/orders').flush(null, { status: 401, statusText: 'Unauthorized' });
    const stale = backend.expectOne('/api/v1/auth/refresh');
    expect(stale.request.body).toEqual({ refresh_token: 'refresh-1' });
    localStorage.setItem('pp.refresh_token', 'refresh-from-other-tab');
    stale.flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-from-other-tab');
    const retry = backend.expectOne('/api/v1/auth/refresh');
    expect(retry.request.body).toEqual({ refresh_token: 'refresh-from-other-tab' });
    retry.flush(session(jwt(3600), 'refresh-3'));
    backend.expectOne('/api/v1/orders').flush([]);
    expect(sessionService.isAuthenticated()).toBeTrue();
    expect(navigate).not.toHaveBeenCalled();
    sessionService.logout();
  }));

  it('a genuinely rejected refresh with the same stored token signs out', fakeAsync(() => {
    let failed = false;
    http.get('/api/v1/orders').subscribe({ error: () => (failed = true) });
    backend.expectOne('/api/v1/orders').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne('/api/v1/auth/refresh').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectNone('/api/v1/auth/refresh');
    expect(failed).toBeTrue();
    expect(localStorage.getItem('pp.access_token')).toBeNull();
    expect(localStorage.getItem('pp.refresh_token')).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/auth/sign-in']);
  }));

  it('a 401 during a workspace switch waits for it but is not replayed in the new workspace', fakeAsync(() => {
    sessionService.adopt(session(jwt(1800, 'a', 'tenant-a'), 'refresh-1'));
    sessionService.switchWorkspace('tenant-b').subscribe();
    const put = backend.expectOne('/api/v1/me/active-workspace');
    let failed: unknown = null;
    http.post('/api/v1/orders', {}).subscribe({ error: (e: unknown) => (failed = e) });
    backend.expectOne('/api/v1/orders').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectNone('/api/v1/auth/refresh');
    put.flush(session(jwt(3600, 'b', 'tenant-b'), 'refresh-2'));
    backend.expectNone('/api/v1/orders');
    expect(failed).toBeTruthy();
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-2');
    expect(sessionService.isAuthenticated()).toBeTrue();
    expect(navigate).not.toHaveBeenCalled();
    sessionService.logout();
  }));

  it('a 401 that lands after a switch already finished is not replayed in the new workspace', fakeAsync(() => {
    sessionService.adopt(session(jwt(1800, 'a', 'tenant-a'), 'refresh-1'));
    let failed = false;
    http.post('/api/v1/orders', {}).subscribe({ error: () => (failed = true) });
    const order = backend.expectOne('/api/v1/orders');
    sessionService.switchWorkspace('tenant-b').subscribe();
    backend.expectOne('/api/v1/me/active-workspace').flush(session(jwt(3600, 'b', 'tenant-b'), 'refresh-2'));
    order.flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectNone('/api/v1/orders');
    backend.expectNone('/api/v1/auth/refresh');
    expect(failed).toBeTrue();
    expect(sessionService.isAuthenticated()).toBeTrue();
    expect(navigate).not.toHaveBeenCalled();
    sessionService.logout();
  }));

  it('a refresh in the same workspace still replays the request', fakeAsync(() => {
    localStorage.setItem('pp.access_token', jwt(-10, 'old', 'tenant-a'));
    http.get('/api/v1/orders').subscribe();
    backend.expectOne('/api/v1/orders').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne('/api/v1/auth/refresh').flush(session(jwt(3600, 'new', 'tenant-a'), 'refresh-2'));
    backend.expectOne('/api/v1/orders').flush([]);
    expect(navigate).not.toHaveBeenCalled();
    sessionService.logout();
  }));

  it('a rejected wake refresh signs out and leaves the protected screen', fakeAsync(() => {
    sessionService.adopt(session(jwt(300), 'refresh-1'));
    const now = Date.now();
    spyOn(Date, 'now').and.returnValue(now + 8 * 60 * 60 * 1000);
    spyOnProperty(document, 'visibilityState', 'get').and.returnValue('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    backend.expectOne('/api/v1/auth/refresh').flush(null, { status: 400, statusText: 'Bad Request' });
    expect(localStorage.getItem('pp.refresh_token')).toBeNull();
    expect(sessionService.isAuthenticated()).toBeFalse();
    expect(navigate).toHaveBeenCalledWith(['/auth/sign-in']);
  }));

  it('a refresh reads storage when subscribed rather than when created', fakeAsync(() => {
    const pending = sessionService.refresh();
    localStorage.setItem('pp.refresh_token', 'latest-refresh');
    pending.subscribe();
    const refresh = backend.expectOne('/api/v1/auth/refresh');
    expect(refresh.request.body).toEqual({ refresh_token: 'latest-refresh' });
    refresh.flush(session(jwt(3600), 'refresh-3'));
    sessionService.logout();
  }));

  it('a rejected stale refresh retries at most once', fakeAsync(() => {
    http.get('/api/v1/orders').subscribe({ error: () => undefined });
    backend.expectOne('/api/v1/orders').flush(null, { status: 401, statusText: 'Unauthorized' });
    const stale = backend.expectOne('/api/v1/auth/refresh');
    localStorage.setItem('pp.refresh_token', 'refresh-2');
    stale.flush(null, { status: 400, statusText: 'Bad Request' });
    backend.expectOne('/api/v1/auth/refresh').flush(null, { status: 400, statusText: 'Bad Request' });
    backend.expectNone('/api/v1/auth/refresh');
    expect(localStorage.getItem('pp.refresh_token')).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/auth/sign-in']);
  }));

  for (const status of [0, 429, 500, 503]) {
    it(`a wake refresh failure with status ${status} preserves tokens`, fakeAsync(() => {
      sessionService.adopt(session(jwt(300), 'refresh-1'));
      const now = Date.now();
      spyOn(Date, 'now').and.returnValue(now + 8 * 60 * 60 * 1000);
      spyOnProperty(document, 'visibilityState', 'get').and.returnValue('visible');
      document.dispatchEvent(new Event('visibilitychange'));
      const refresh = backend.expectOne('/api/v1/auth/refresh');
      if (status === 0) refresh.error(new ProgressEvent('error'));
      else refresh.flush(null, { status, statusText: 'Transient failure' });
      expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
      expect(sessionService.isAuthenticated()).toBeTrue();
      expect(navigate).not.toHaveBeenCalled();
      sessionService.logout();
    }));
  }

  it('a transient startup /me error preserves the stored session', fakeAsync(() => {
    localStorage.setItem('pp.access_token', jwt(1800));
    TestBed.runInInjectionContext(() => restoreSessionOnStartup()).subscribe();
    backend.expectOne('/api/v1/me').flush(null, { status: 503, statusText: 'Unavailable' });
    expect(localStorage.getItem('pp.refresh_token')).toBe('refresh-1');
    expect(navigate).not.toHaveBeenCalled();
  }));

  it('sign-out cancels the proactive refresh', fakeAsync(() => {
    sessionService.adopt(session(jwt(300), 'refresh-1'));
    sessionService.logout();

    tick(300_000);
    backend.expectNone('/api/v1/auth/refresh');
  }));
});
