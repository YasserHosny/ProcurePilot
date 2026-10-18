import { HttpContext, HttpErrorResponse } from '@angular/common/http';
import { Injectable, NgZone, computed, inject, signal } from '@angular/core';
import { Observable, defer, finalize, of, shareReplay, switchMap, tap, throwError } from 'rxjs';

import { ApiService } from '../api/api.service';
import type { Me, Role, Session, WorkspaceSummary } from '../api/models';
import { REBUILD_ON_REPLAY } from './http-context';

const ACCESS_TOKEN_KEY = 'pp.access_token';
const REFRESH_TOKEN_KEY = 'pp.refresh_token';

/** Renew this long before `exp`, so a request in flight never carries a token about to lapse. */
export const REFRESH_LEAD_MS = 60_000;

/**
 * True only when the server has definitively refused the refresh token. A 429, a 5xx or a
 * network failure says nothing about the session, so it must not cost the person their sign-in.
 */
export function refreshWasRejected(error: unknown): boolean {
  return error instanceof HttpErrorResponse && [400, 401, 403, 422].includes(error.status);
}

/** The token's `exp` in epoch milliseconds, or null if it is not a readable JWT. */
export function tokenExpiry(token: string | null): number | null {
  if (!token) return null;
  const payload = token.split('.')[1];
  if (!payload) return null;
  try {
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    return typeof exp === 'number' ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/**
 * Holds the current session: the signed-in member, their role, and the active workspace.
 *
 * The active workspace is whatever the token says it is. Switching workspace goes through the
 * server, which re-issues the token — the client never decides its own tenancy.
 */
@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly api = inject(ApiService);
  private readonly zone = inject(NgZone);
  private inFlightRefresh: Observable<Session> | null = null;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private switching = false;

  private readonly member = signal<Me | null>(null);

  readonly currentMember = this.member.asReadonly();
  readonly isAuthenticated = computed(() => this.member() !== null);
  readonly role = computed<Role | null>(() => this.member()?.role ?? null);
  readonly tenant = computed(() => this.member()?.tenant ?? null);
  readonly homeCurrency = computed(() => this.tenant()?.currency ?? undefined);
  readonly activeLocale = computed(
    () => this.member()?.preferred_locale ?? this.member()?.tenant.default_locale ?? 'en',
  );

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  hasRole(...roles: readonly Role[]): boolean {
    const current = this.role();
    return current !== null && roles.includes(current);
  }

  login(email: string, password: string): Observable<Session> {
    return this.api.login(email, password).pipe(tap((s) => this.adopt(s)));
  }

  /** Restores the member on app start when a token survived a reload. */
  restore(): Observable<Me> {
    return this.api.me().pipe(
      tap((me) => {
        this.member.set(me);
        this.scheduleRefresh();
      }),
    );
  }

  /** True when the stored access token is missing, unreadable, or within the refresh lead. */
  accessTokenNeedsRefresh(now = Date.now()): boolean {
    const exp = tokenExpiry(this.accessToken);
    return exp === null || exp - now <= REFRESH_LEAD_MS;
  }

  /**
   * Exchanges the refresh token for a new session (demo finding 29: the Supabase access token
   * lasts an hour and nothing renewed it, so everyone was signed out hourly).
   *
   * Callers that arrive while a refresh is in flight share it: Supabase rotates the refresh
   * token on use, so parallel refreshes would race each other with a token already spent.
   *
   * The workspace is not sent: the access-token hook re-reads the persisted active workspace,
   * so the renewed token carries the same tenant claim. Tenancy stays the server's decision.
   */
  refresh(): Observable<Session> {
    if (this.inFlightRefresh) return this.inFlightRefresh;
    const refreshToken = this.refreshToken;
    if (!refreshToken) {
      return throwError(() => new Error('cannot refresh the session without a refresh token'));
    }
    const request = this.api.refreshSession(refreshToken).pipe(
      tap((s) => this.adopt(s)),
      finalize(() => {
        if (this.inFlightRefresh === request) this.inFlightRefresh = null;
      }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    this.inFlightRefresh = request;
    return request;
  }

  get refreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  /**
   * Switches workspace. The server re-issues the session from the refresh token in the body,
   * which rotates it — so this must never race a refresh for the same token:
   * - a refresh already in flight is awaited, and an expiring access token is renewed first,
   *   so the switch sends the CURRENT refresh token;
   * - the proactive timer stands down while the switch is out (the switch's own adopt re-arms it);
   * - if the PUT still gets a 401 and the interceptor refreshes, the replay re-reads the refresh
   *   token instead of resending the one that refresh just spent.
   */
  switchWorkspace(tenantId: string): Observable<Session> {
    if (!this.refreshToken) {
      return throwError(() => new Error('cannot switch workspace without a refresh token'));
    }
    const context = new HttpContext().set(REBUILD_ON_REPLAY, (req) =>
      req.clone({
        body: { ...(req.body as Record<string, unknown>), refresh_token: this.refreshToken },
      }),
    );
    return defer(() => {
      this.switching = true;
      const ready: Observable<unknown> =
        this.inFlightRefresh ?? (this.accessTokenNeedsRefresh() ? this.refresh() : of(null));
      return ready.pipe(
        switchMap(() => this.api.setActiveWorkspace(tenantId, this.refreshToken ?? '', context)),
        tap((s) => this.adopt(s)),
        finalize(() => (this.switching = false)),
      );
    });
  }

  workspaces(): Observable<{ items: WorkspaceSummary[] }> {
    return this.api.myWorkspaces();
  }

  logout(): void {
    this.clearRefreshTimer();
    this.inFlightRefresh = null;
    this.member.set(null);
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  adopt(session: Session): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, session.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, session.refresh_token);
    this.member.set(session.user);
    this.scheduleRefresh();
  }

  updateTenant(tenant: import('../api/models').Tenant): void {
    const current = this.member();
    if (current) this.member.set({ ...current, tenant });
  }

  /**
   * Renews the session shortly before the access token expires. A failure here is left alone:
   * the next request's 401 retries the refresh and signs out only if that fails too.
   *
   * The timer runs outside Angular's zone so an hour-long pending task never holds the app
   * "unstable"; the refresh itself re-enters the zone.
   */
  private scheduleRefresh(): void {
    this.clearRefreshTimer();
    const exp = tokenExpiry(this.accessToken);
    if (exp === null || !this.refreshToken) return;
    const delay = Math.max(0, exp - REFRESH_LEAD_MS - Date.now());
    this.zone.runOutsideAngular(() => {
      this.refreshTimer = setTimeout(() => {
        this.refreshTimer = null;
        // A workspace switch is spending the refresh token; its adopt() re-arms this timer.
        if (this.switching) return;
        // Another tab may already have renewed the shared token; just re-arm for it.
        if (!this.accessTokenNeedsRefresh()) {
          this.scheduleRefresh();
          return;
        }
        this.zone.run(() => this.refresh().subscribe({ error: () => undefined }));
      }, delay);
    });
  }

  private clearRefreshTimer(): void {
    if (this.refreshTimer !== null) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
  }
}
