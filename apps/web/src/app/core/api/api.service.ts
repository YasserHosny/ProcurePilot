import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import type {
  Alias,
  BaseUnit,
  ConfigOptions,
  Document,
  ImportPreview,
  ImportResult,
  Invitation,
  Job,
  Me,
  Member,
  PresignRequest,
  PresignResponse,
  Product,
  ProductCreate,
  ProductUpdate,
  Quotation,
  QuotationCreate,
  QuotationDetail,
  QuotationReviewPatch,
  ReviewTask,
  ReviewTaskPriority,
  ReviewTaskStatus,
  Role,
  Session,
  Supplier,
  SupplierCreate,
  SupplierUpdate,
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

  baseUnits(): Observable<{ items: BaseUnit[] }> {
    return this.http.get<{ items: BaseUnit[] }>(`${this.base}/reference/base-units`);
  }

  // --- products -----------------------------------------------------------

  products(params?: {
    cursor?: string;
    limit?: number;
    status?: 'active' | 'archived' | 'all';
    q?: string;
  }): Observable<{ items: Product[]; next_cursor: string | null }> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    if (params?.q) query.set('q', params.q);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<{ items: Product[]; next_cursor: string | null }>(
      `${this.base}/products${qs}`,
    );
  }

  product(productId: string): Observable<Product> {
    return this.http.get<Product>(`${this.base}/products/${productId}`);
  }

  createProduct(body: ProductCreate, idempotencyKey?: string): Observable<Product> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Product>(`${this.base}/products`, body, { headers });
  }

  updateProduct(productId: string, body: ProductUpdate): Observable<Product> {
    return this.http.patch<Product>(`${this.base}/products/${productId}`, body);
  }

  archiveProduct(productId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/products/${productId}`);
  }

  approveSubstitute(productId: string, substituteProductId: string): Observable<void> {
    return this.http.post<void>(`${this.base}/products/${productId}/substitutes`, {
      substitute_product_id: substituteProductId,
    });
  }

  // --- suppliers ----------------------------------------------------------

  suppliers(params?: {
    cursor?: string;
    limit?: number;
    status?: 'active' | 'preferred' | 'blocked' | 'archived' | 'all';
  }): Observable<{ items: Supplier[]; next_cursor: string | null }> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<{ items: Supplier[]; next_cursor: string | null }>(
      `${this.base}/suppliers${qs}`,
    );
  }

  supplier(supplierId: string): Observable<Supplier> {
    return this.http.get<Supplier>(`${this.base}/suppliers/${supplierId}`);
  }

  createSupplier(body: SupplierCreate, idempotencyKey?: string): Observable<Supplier> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Supplier>(`${this.base}/suppliers`, body, { headers });
  }

  updateSupplier(supplierId: string, body: SupplierUpdate): Observable<Supplier> {
    return this.http.patch<Supplier>(`${this.base}/suppliers/${supplierId}`, body);
  }

  archiveSupplier(supplierId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/suppliers/${supplierId}`);
  }

  // --- aliases ------------------------------------------------------------

  aliases(): Observable<{ items: Alias[] }> {
    return this.http.get<{ items: Alias[] }>(`${this.base}/aliases`);
  }

  createAlias(body: {
    workspace_product_id: string;
    supplier_id?: string | null;
    alias_text: string;
  }): Observable<Alias> {
    return this.http.post<Alias>(`${this.base}/aliases`, body);
  }

  deleteAlias(aliasId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/aliases/${aliasId}`);
  }

  // --- imports ------------------------------------------------------------

  uploadImport(kind: 'products' | 'suppliers', file: File): Observable<ImportPreview> {
    const formData = new FormData();
    formData.append('kind', kind);
    formData.append('file', file);
    return this.http.post<ImportPreview>(`${this.base}/imports`, formData);
  }

  commitImport(
    importId: string,
    onDuplicate: 'skip' | 'update' = 'skip',
  ): Observable<ImportResult> {
    return this.http.post<ImportResult>(`${this.base}/imports/${importId}/commit`, {
      on_duplicate: onDuplicate,
    });
  }

  // --- documents & quotation inbox (Chunk 4.3) -----------------------------

  presignDocument(body: PresignRequest, idempotencyKey?: string): Observable<PresignResponse> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<PresignResponse>(`${this.base}/documents/presign`, body, { headers });
  }

  uploadFileToStorage(
    uploadUrl: string,
    file: File,
    uploadFields?: Record<string, string>,
  ): Observable<void> {
    if (uploadFields && Object.keys(uploadFields).length > 0) {
      const formData = new FormData();
      for (const [k, v] of Object.entries(uploadFields)) {
        formData.append(k, v);
      }
      formData.append('file', file);
      return this.http.post<void>(uploadUrl, formData);
    }
    return this.http.put<void>(uploadUrl, file, {
      headers: {
        'Content-Type': file.type || 'application/octet-stream',
      },
    });
  }

  getDocument(documentId: string): Observable<Document> {
    return this.http.get<Document>(`${this.base}/documents/${documentId}`);
  }

  createQuotation(body: QuotationCreate, idempotencyKey?: string): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(`${this.base}/quotations`, body, { headers });
  }

  getQuotation(quotationId: string): Observable<QuotationDetail> {
    return this.http.get<QuotationDetail>(`${this.base}/quotations/${quotationId}`);
  }

  patchQuotation(
    quotationId: string,
    body: QuotationReviewPatch,
    idempotencyKey?: string,
  ): Observable<QuotationDetail> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.patch<QuotationDetail>(`${this.base}/quotations/${quotationId}`, body, {
      headers,
    });
  }

  extractQuotation(quotationId: string, idempotencyKey?: string): Observable<Job> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Job>(`${this.base}/quotations/${quotationId}/extract`, {}, { headers });
  }

  confirmQuotation(
    quotationId: string,
    body?: { previous_quotation_id?: string | null },
    idempotencyKey?: string,
  ): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(
      `${this.base}/quotations/${quotationId}/confirm`,
      body ?? {},
      { headers },
    );
  }

  getJob(jobId: string): Observable<Job> {
    return this.http.get<Job>(`${this.base}/jobs/${jobId}`);
  }

  getReviewTasks(params?: {
    cursor?: string;
    limit?: number;
    status?: ReviewTaskStatus | 'all';
    priority?: ReviewTaskPriority;
  }): Observable<{ items: ReviewTask[]; next_cursor: string | null }> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    if (params?.priority) query.set('priority', params.priority);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<{ items: ReviewTask[]; next_cursor: string | null }>(
      `${this.base}/review-tasks${qs}`,
    );
  }
}

