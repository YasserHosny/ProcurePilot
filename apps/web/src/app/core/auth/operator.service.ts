import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, map, of, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface OperatorProfile {
  readonly digest_enabled: boolean;
  readonly digest_locale: 'en' | 'ar';
}

/**
 * Whether the signed-in user is a platform operator, from `GET /platform/feedback/me`
 * (404 = not an operator). A UX hint only: the server re-checks on every operator request.
 */
@Injectable({ providedIn: 'root' })
export class OperatorService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  private readonly state = signal<{ user: string; profile: OperatorProfile | null } | null>(null);

  readonly profile = computed(() => {
    const state = this.state();
    return state && state.user === this.userKey() ? state.profile : null;
  });
  readonly isOperator = computed(() => this.profile() !== null);

  /** Resolves the operator profile (null when not an operator). Cached per signed-in user. */
  load(): Observable<OperatorProfile | null> {
    const user = this.userKey();
    const cached = this.state();
    if (cached && cached.user === user) return of(cached.profile);
    return this.http.get<OperatorProfile>(`${environment.apiBaseUrl}/platform/feedback/me`).pipe(
      map((profile): OperatorProfile | null | undefined => profile),
      catchError((err: unknown) => {
        // 404 is the definitive "not an operator" and is cached. Anything else is treated the
        // same for the UI but not cached, so a transient failure is retried on next navigation.
        if (err instanceof HttpErrorResponse && err.status === 404) return of(null);
        return of(undefined);
      }),
      tap((profile) => {
        if (profile !== undefined) this.state.set({ user, profile });
      }),
      map((profile) => profile ?? null),
    );
  }

  /** Keeps the cached digest preference in step after the operator changes it. */
  updateProfile(profile: OperatorProfile): void {
    this.state.set({ user: this.userKey(), profile });
  }

  private userKey(): string {
    return this.session.currentMember()?.id ?? '';
  }
}
