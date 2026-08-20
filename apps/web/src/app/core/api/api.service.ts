import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import type {
  ConfigOptions,
  Invitation,
  Me,
  Member,
  Role,
  Session,
  Tenant,
  WorkspaceSummary,
} from './models';

/**
 * Typed client for the endpoints in contracts/auth-tenant.openapi.yaml.
 *
 * Tenancy is never sent by the client: the server resolves it from the verified token.
 * There is deliberately no tenant_id parameter anywhere in this class.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  // --- auth ---------------------------------------------------------------

  signup(body: {
    invitation_token: string;
    email: string;
    password: string;
    business_name: string;
    region: string;
    currency: string;
    tax_model: string;
    default_locale?: 'en' | 'ar';
  }): Observable<Session> {
    return this.http.post<Session>(`${this.base}/auth/signup`, body);
  }

  login(email: string, password: string): Observable<Session> {
    return this.http.post<Session>(`${this.base}/auth/login`, { email, password });
  }

  logout(): Observable<void> {
    return this.http.post<void>(`${this.base}/auth/logout`, {});
  }

  requestPasswordReset(email: string): Observable<void> {
    return this.http.post<void>(`${this.base}/auth/password-reset`, { email });
  }

  // --- identity -----------------------------------------------------------

  me(): Observable<Me> {
    return this.http.get<Me>(`${this.base}/me`);
  }

  updateMe(body: { preferred_locale: 'en' | 'ar' }): Observable<Me> {
    return this.http.patch<Me>(`${this.base}/me`, body);
  }

  myWorkspaces(): Observable<{ items: WorkspaceSummary[] }> {
    return this.http.get<{ items: WorkspaceSummary[] }>(`${this.base}/me/workspaces`);
  }

  /**
   * Switching re-issues the session so the tenant_id claim follows (research R3).
   *
   * The refresh token is required: the claim is injected at token issuance, so a new access
   * token has to be minted, and that is only done in exchange for a refresh token. Omitting it
   * returns 422.
   */
  setActiveWorkspace(tenantId: string, refreshToken: string): Observable<Session> {
    return this.http.put<Session>(`${this.base}/me/active-workspace`, {
      tenant_id: tenantId,
      refresh_token: refreshToken,
    });
  }

  // --- workspace ----------------------------------------------------------

  tenant(): Observable<Tenant> {
    return this.http.get<Tenant>(`${this.base}/tenant`);
  }

  updateTenant(body: { name?: string; default_locale?: 'en' | 'ar' }): Observable<Tenant> {
    return this.http.patch<Tenant>(`${this.base}/tenant`, body);
  }

  // --- members and invitations --------------------------------------------

  members(cursor?: string): Observable<{ items: Member[]; next_cursor: string | null }> {
    const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
    return this.http.get<{ items: Member[]; next_cursor: string | null }>(
      `${this.base}/members${query}`,
    );
  }

  changeMemberRole(memberId: string, role: Role): Observable<Member> {
    return this.http.patch<Member>(`${this.base}/members/${memberId}`, { role });
  }

  removeMember(memberId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/members/${memberId}`);
  }

  invitations(): Observable<{ items: Invitation[] }> {
    return this.http.get<{ items: Invitation[] }>(`${this.base}/invitations`);
  }

  invite(email: string, role: Role): Observable<Invitation> {
    return this.http.post<Invitation>(`${this.base}/invitations`, { email, role });
  }

  revokeInvitation(invitationId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/invitations/${invitationId}`);
  }

  acceptInvitation(token: string, password?: string): Observable<Session> {
    return this.http.post<Session>(`${this.base}/invitations/accept`, { token, password });
  }

  // --- reference ----------------------------------------------------------

  configOptions(): Observable<ConfigOptions> {
    return this.http.get<ConfigOptions>(`${this.base}/reference/config-options`);
  }
}
