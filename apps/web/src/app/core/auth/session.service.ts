import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, tap, throwError } from 'rxjs';

import { ApiService } from '../api/api.service';
import type { Me, Role, Session, WorkspaceSummary } from '../api/models';

const ACCESS_TOKEN_KEY = 'pp.access_token';
const REFRESH_TOKEN_KEY = 'pp.refresh_token';

/**
 * Holds the current session: the signed-in member, their role, and the active workspace.
 *
 * The active workspace is whatever the token says it is. Switching workspace goes through the
 * server, which re-issues the token — the client never decides its own tenancy.
 */
@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly api = inject(ApiService);

  private readonly member = signal<Me | null>(null);

  readonly currentMember = this.member.asReadonly();
  readonly isAuthenticated = computed(() => this.member() !== null);
  readonly role = computed<Role | null>(() => this.member()?.role ?? null);
  readonly tenant = computed(() => this.member()?.tenant ?? null);
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
    return this.api.me().pipe(tap((me) => this.member.set(me)));
  }

  get refreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  switchWorkspace(tenantId: string): Observable<Session> {
    const refresh = this.refreshToken;
    if (!refresh) {
      return throwError(() => new Error('cannot switch workspace without a refresh token'));
    }
    return this.api.setActiveWorkspace(tenantId, refresh).pipe(tap((s) => this.adopt(s)));
  }

  workspaces(): Observable<{ items: WorkspaceSummary[] }> {
    return this.api.myWorkspaces();
  }

  logout(): void {
    this.member.set(null);
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  adopt(session: Session): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, session.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, session.refresh_token);
    this.member.set(session.user);
  }
}
