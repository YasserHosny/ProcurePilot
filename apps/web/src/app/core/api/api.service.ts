import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import type {
  Alert,
  AlertDismissal,
  AlertKind,
  Alias,
  ApprovalDecisionInput,
  ApprovalDelegation,
  ApprovalDelegationCreate,
  ApprovalDelegationList,
  AuditTrailEntry,
  BaseUnit,
  BasketOptimiseRequest,
  BasketSplitJob,
  BillingAccount,
  Branch,
  BranchCreate,
  BranchList,
  BranchRoleAssignment,
  BranchRoleAssignmentCreate,
  BranchUpdate,
  BudgetCreate,
  BudgetCreated,
  BudgetList,
  BudgetScope,
  ConfigOptions,
  CostCentre,
  CostCentreCreate,
  CostCentreList,
  CostCentreUpdate,
  Document,
  DocumentDownloadResponse,
  ExportCreate,
  ExportJob,
  ImportPreview,
  ImportResult,
  Invitation,
  Job,
  LandedCost,
  LimitCheck,
  MatchDecision,
  MatchResolutionRequest,
  MatchTask,
  MatchTaskPriority,
  MatchTaskReason,
  MatchTaskStatus,
  Me,
  Member,
  Offer,
  OfferComparison,
  PresignRequest,
  PresignResponse,
  PriceHistoryResponse,
  Product,
  ProductCreate,
  ProductUpdate,
  PurchaseOutcomeCreate,
  PurchaseOutcomeCreated,
  PurchaseRequest,
  PurchaseRequestCreate,
  PurchaseRequestList,
  PurchaseRequestStatus,
  PurchaseRequestUpdate,
  Quotation,
  QuotationCreate,
  QuotationDetail,
  QuotationMatches,
  QuotationReviewPatch,
  ReviewTask,
  ReviewTaskPriority,
  ReviewTaskStatus,
  Role,
  SavingEvidence,
  SavingList,
  SavingRecord,
  SavingStatus,
  Session,
  Supplier,
  SupplierCreate,
  SupplierUpdate,
  Tenant,
  ThresholdRule,
  ThresholdRuleCreate,
  ThresholdRuleList,
  ThresholdRuleUpdate,
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

  getDocumentDownloadUrl(documentId: string): Observable<DocumentDownloadResponse> {
    return this.http.get<DocumentDownloadResponse>(`${this.base}/documents/${documentId}/download`);
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
    body?: { previous_quotation_id?: string | null; acknowledge_mismatch?: boolean },
    idempotencyKey?: string,
  ): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(
      `${this.base}/quotations/${quotationId}/confirm`,
      body ?? {},
      { headers },
    );
  }

  refuseQuotation(
    quotationId: string,
    body?: { reason?: string | null },
    idempotencyKey?: string,
  ): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(
      `${this.base}/quotations/${quotationId}/refuse`,
      body ?? {},
      { headers },
    );
  }

  archiveQuotation(quotationId: string, idempotencyKey?: string): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(
      `${this.base}/quotations/${quotationId}/archive`,
      {},
      { headers },
    );
  }

  restoreQuotation(quotationId: string, idempotencyKey?: string): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(
      `${this.base}/quotations/${quotationId}/restore`,
      {},
      { headers },
    );
  }

  retryExtraction(quotationId: string, idempotencyKey?: string): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(
      `${this.base}/quotations/${quotationId}/retry-extraction`,
      {},
      { headers },
    );
  }

  replaceDocument(
    quotationId: string,
    documentId: string,
    idempotencyKey?: string,
  ): Observable<Quotation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Quotation>(
      `${this.base}/quotations/${quotationId}/replace-document`,
      { document_id: documentId },
      { headers },
    );
  }

  exportQuotation(quotationId: string): Observable<Blob> {
    return this.http.get(`${this.base}/quotations/${quotationId}/export?format=csv`, {
      responseType: 'blob',
    });
  }

  getAuditTrail(quotationId: string): Observable<{ items: AuditTrailEntry[] }> {
    return this.http.get<{ items: AuditTrailEntry[] }>(
      `${this.base}/quotations/${quotationId}/audit-trail`,
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
    search?: string;
    date_from?: string;
    date_to?: string;
    sort_by?: 'created_at' | 'stated_total' | 'priority' | 'status';
    sort_order?: 'asc' | 'desc';
  }): Observable<{ items: ReviewTask[]; next_cursor: string | null }> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    if (params?.priority) query.set('priority', params.priority);
    if (params?.search) query.set('search', params.search);
    if (params?.date_from) query.set('date_from', params.date_from);
    if (params?.date_to) query.set('date_to', params.date_to);
    if (params?.sort_by) query.set('sort_by', params.sort_by);
    if (params?.sort_order) query.set('sort_order', params.sort_order);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<{ items: ReviewTask[]; next_cursor: string | null }>(
      `${this.base}/review-tasks${qs}`,
    );
  }

  // --- matching & normalisation (Chunk 4.4) -------------------------------

  getQuotationMatches(quotationId: string): Observable<QuotationMatches> {
    return this.http.get<QuotationMatches>(`${this.base}/quotations/${quotationId}/matches`);
  }

  getMatchTasks(params?: {
    cursor?: string;
    limit?: number;
    status?: MatchTaskStatus | 'all';
    priority?: MatchTaskPriority;
    reason?: MatchTaskReason;
    quotation_id?: string;
  }): Observable<{ items: MatchTask[]; next_cursor: string | null }> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    if (params?.priority) query.set('priority', params.priority);
    if (params?.reason) query.set('reason', params.reason);
    if (params?.quotation_id) query.set('quotation_id', params.quotation_id);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<{ items: MatchTask[]; next_cursor: string | null }>(
      `${this.base}/match-tasks${qs}`,
    );
  }

  resolveMatch(
    lineId: string,
    body: MatchResolutionRequest,
    idempotencyKey?: string,
  ): Observable<MatchDecision> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<MatchDecision>(
      `${this.base}/quotation-lines/${lineId}/match`,
      body,
      { headers },
    );
  }

  getLandedCost(lineId: string): Observable<LandedCost> {
    return this.http.get<LandedCost>(`${this.base}/quotation-lines/${lineId}/landed-cost`);
  }

  // --- smart compare & intelligence (Chunk 4.5) ----------------------------

  getOffers(params: {
    product_id: string;
    quantity: string;
    include_expired?: boolean;
    cursor?: string;
    limit?: number;
  }): Observable<{ items: Offer[]; next_cursor: string | null }> {
    const query = new URLSearchParams();
    query.set('product_id', params.product_id);
    query.set('quantity', params.quantity);
    if (params.include_expired !== undefined) {
      query.set('include_expired', String(params.include_expired));
    }
    if (params.cursor) query.set('cursor', params.cursor);
    if (params.limit) query.set('limit', String(params.limit));
    return this.http.get<{ items: Offer[]; next_cursor: string | null }>(
      `${this.base}/offers?${query.toString()}`,
    );
  }

  compareOffers(params: {
    product_id: string;
    quantity: string;
  }): Observable<OfferComparison> {
    const query = new URLSearchParams();
    query.set('product_id', params.product_id);
    query.set('quantity', params.quantity);
    return this.http.get<OfferComparison>(
      `${this.base}/offers/compare?${query.toString()}`,
    );
  }

  getPriceHistory(
    productId: string,
    params?: {
      supplier_id?: string;
      window_months?: number;
      cursor?: string;
      limit?: number;
    },
  ): Observable<PriceHistoryResponse> {
    const query = new URLSearchParams();
    if (params?.supplier_id) query.set('supplier_id', params.supplier_id);
    if (params?.window_months !== undefined) {
      query.set('window_months', String(params.window_months));
    }
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<PriceHistoryResponse>(
      `${this.base}/products/${productId}/price-history${qs}`,
    );
  }

  optimiseBasket(
    body: BasketOptimiseRequest,
    idempotencyKey?: string,
  ): Observable<BasketSplitJob> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<BasketSplitJob>(`${this.base}/baskets/optimise`, body, { headers });
  }

  getBasketSplitJob(id: string): Observable<BasketSplitJob> {
    return this.http.get<BasketSplitJob>(`${this.base}/baskets/${id}`);
  }

  getAlerts(params?: {
    kind?: AlertKind;
    cursor?: string;
    limit?: number;
  }): Observable<{ items: Alert[]; next_cursor: string | null }> {
    const query = new URLSearchParams();
    if (params?.kind) query.set('kind', params.kind);
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<{ items: Alert[]; next_cursor: string | null }>(
      `${this.base}/alerts${qs}`,
    );
  }

  dismissAlert(id: string, idempotencyKey?: string): Observable<AlertDismissal> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<AlertDismissal>(
      `${this.base}/alerts/${encodeURIComponent(id)}/dismiss`,
      {},
      { headers },
    );
  }

  // --- value proof, exports & billing (Chunk 4.6) ---------------------------

  recordPurchase(
    body: PurchaseOutcomeCreate,
    idempotencyKey?: string,
  ): Observable<PurchaseOutcomeCreated> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<PurchaseOutcomeCreated>(`${this.base}/purchases`, body, { headers });
  }

  getSavings(params?: {
    status?: SavingStatus;
    period_start?: string;
    period_end?: string;
    supplier_id?: string;
    branch_id?: string | null;
    cursor?: string;
    limit?: number;
  }): Observable<SavingList> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.period_start) query.set('period_start', params.period_start);
    if (params?.period_end) query.set('period_end', params.period_end);
    if (params?.supplier_id) query.set('supplier_id', params.supplier_id);
    if (params?.branch_id !== undefined && params?.branch_id !== null) {
      query.set('branch_id', params.branch_id);
    }
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<SavingList>(`${this.base}/savings${qs}`);
  }

  getSaving(id: string): Observable<SavingRecord> {
    return this.http.get<SavingRecord>(`${this.base}/savings/${encodeURIComponent(id)}`);
  }

  getSavingEvidence(id: string): Observable<SavingEvidence> {
    return this.http.get<SavingEvidence>(
      `${this.base}/savings/${encodeURIComponent(id)}/evidence`,
    );
  }

  verifySaving(id: string, idempotencyKey?: string): Observable<SavingRecord> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<SavingRecord>(
      `${this.base}/savings/${encodeURIComponent(id)}/verify`,
      {},
      { headers },
    );
  }

  createExport(body: ExportCreate, idempotencyKey?: string): Observable<ExportJob> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<ExportJob>(`${this.base}/exports`, body, { headers });
  }

  getExportJob(id: string): Observable<ExportJob> {
    return this.http.get<ExportJob>(`${this.base}/exports/${encodeURIComponent(id)}`);
  }

  getBillingAccount(): Observable<BillingAccount> {
    return this.http.get<BillingAccount>(`${this.base}/billing/account`);
  }

  checkActiveCatalogueProductsLimit(): Observable<LimitCheck> {
    return this.http.get<LimitCheck>(
      `${this.base}/billing/limits/active-catalogue-products`,
    );
  }

  // --- organisation model (007) ---------------------------------------------

  listBranches(params?: {
    is_active?: boolean;
    cursor?: string;
    limit?: number;
  }): Observable<BranchList> {
    const query = new URLSearchParams();
    if (params?.is_active !== undefined) query.set('is_active', String(params.is_active));
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<BranchList>(`${this.base}/organisation/branches${qs}`);
  }

  createBranch(body: BranchCreate, idempotencyKey?: string): Observable<Branch> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<Branch>(`${this.base}/organisation/branches`, body, { headers });
  }

  updateBranch(branchId: string, body: BranchUpdate): Observable<Branch> {
    return this.http.patch<Branch>(
      `${this.base}/organisation/branches/${branchId}`,
      body,
    );
  }

  listCostCentres(params?: {
    branch_id?: string;
    is_archived?: boolean;
    cursor?: string;
    limit?: number;
  }): Observable<CostCentreList> {
    const query = new URLSearchParams();
    if (params?.branch_id) query.set('branch_id', params.branch_id);
    if (params?.is_archived !== undefined) {
      query.set('is_archived', String(params.is_archived));
    }
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<CostCentreList>(`${this.base}/organisation/cost-centres${qs}`);
  }

  createCostCentre(body: CostCentreCreate, idempotencyKey?: string): Observable<CostCentre> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<CostCentre>(`${this.base}/organisation/cost-centres`, body, {
      headers,
    });
  }

  updateCostCentre(
    costCentreId: string,
    body: CostCentreUpdate,
  ): Observable<CostCentre> {
    return this.http.patch<CostCentre>(
      `${this.base}/organisation/cost-centres/${costCentreId}`,
      body,
    );
  }

  listBudgets(params?: {
    scope?: BudgetScope;
    branch_id?: string;
    cost_centre_id?: string;
    cursor?: string;
    limit?: number;
  }): Observable<BudgetList> {
    const query = new URLSearchParams();
    if (params?.scope) query.set('scope', params.scope);
    if (params?.branch_id) query.set('branch_id', params.branch_id);
    if (params?.cost_centre_id) query.set('cost_centre_id', params.cost_centre_id);
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<BudgetList>(`${this.base}/organisation/budgets${qs}`);
  }

  createBudget(body: BudgetCreate, idempotencyKey?: string): Observable<BudgetCreated> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<BudgetCreated>(`${this.base}/organisation/budgets`, body, {
      headers,
    });
  }

  createBranchRoleAssignment(
    body: BranchRoleAssignmentCreate,
    idempotencyKey?: string,
  ): Observable<BranchRoleAssignment> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<BranchRoleAssignment>(
      `${this.base}/organisation/branch-role-assignments`,
      body,
      { headers },
    );
  }

  removeBranchRoleAssignment(assignmentId: string): Observable<void> {
    return this.http.delete<void>(
      `${this.base}/organisation/branch-role-assignments/${assignmentId}`,
    );
  }

  // --- requests + approvals (008) --------------------------------------------

  listRequests(params?: {
    status?: PurchaseRequestStatus;
    branch_id?: string;
    cursor?: string;
    limit?: number;
  }): Observable<PurchaseRequestList> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.branch_id) query.set('branch_id', params.branch_id);
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<PurchaseRequestList>(`${this.base}/requests${qs}`);
  }

  getRequest(requestId: string): Observable<PurchaseRequest> {
    return this.http.get<PurchaseRequest>(`${this.base}/requests/${requestId}`);
  }

  createRequest(
    body: PurchaseRequestCreate,
    idempotencyKey?: string,
  ): Observable<PurchaseRequest> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<PurchaseRequest>(`${this.base}/requests`, body, { headers });
  }

  updateRequest(requestId: string, body: PurchaseRequestUpdate): Observable<PurchaseRequest> {
    return this.http.patch<PurchaseRequest>(`${this.base}/requests/${requestId}`, body);
  }

  submitRequest(requestId: string, idempotencyKey?: string): Observable<PurchaseRequest> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<PurchaseRequest>(
      `${this.base}/requests/${requestId}/submit`,
      null,
      { headers },
    );
  }

  withdrawRequest(requestId: string): Observable<PurchaseRequest> {
    return this.http.post<PurchaseRequest>(`${this.base}/requests/${requestId}/withdraw`, null);
  }

  approveRequest(
    requestId: string,
    body: ApprovalDecisionInput,
  ): Observable<PurchaseRequest> {
    return this.http.post<PurchaseRequest>(`${this.base}/requests/${requestId}/approve`, body);
  }

  rejectRequest(
    requestId: string,
    body: ApprovalDecisionInput,
  ): Observable<PurchaseRequest> {
    return this.http.post<PurchaseRequest>(`${this.base}/requests/${requestId}/reject`, body);
  }

  listPendingApprovals(params?: {
    cursor?: string;
    limit?: number;
  }): Observable<PurchaseRequestList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<PurchaseRequestList>(`${this.base}/approvals/pending${qs}`);
  }

  listThresholdRules(params?: {
    cursor?: string;
    limit?: number;
  }): Observable<ThresholdRuleList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<ThresholdRuleList>(`${this.base}/approvals/threshold-rules${qs}`);
  }

  createThresholdRule(
    body: ThresholdRuleCreate,
    idempotencyKey?: string,
  ): Observable<ThresholdRule> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<ThresholdRule>(`${this.base}/approvals/threshold-rules`, body, {
      headers,
    });
  }

  updateThresholdRule(ruleId: string, body: ThresholdRuleUpdate): Observable<ThresholdRule> {
    return this.http.patch<ThresholdRule>(
      `${this.base}/approvals/threshold-rules/${ruleId}`,
      body,
    );
  }

  deleteThresholdRule(ruleId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/approvals/threshold-rules/${ruleId}`);
  }

  listApprovalDelegations(params?: { membership_id?: string }): Observable<ApprovalDelegationList> {
    const query = new URLSearchParams();
    if (params?.membership_id) query.set('membership_id', params.membership_id);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<ApprovalDelegationList>(`${this.base}/approvals/delegations${qs}`);
  }

  createApprovalDelegation(
    body: ApprovalDelegationCreate,
    idempotencyKey?: string,
  ): Observable<ApprovalDelegation> {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
    return this.http.post<ApprovalDelegation>(`${this.base}/approvals/delegations`, body, {
      headers,
    });
  }

  cancelApprovalDelegation(delegationId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/approvals/delegations/${delegationId}`);
  }
}
