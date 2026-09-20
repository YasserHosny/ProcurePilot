/**
 * Types mirroring specs/001-platform-foundation/contracts/auth-tenant.openapi.yaml.
 *
 * Hand-written for now. Task T032 calls for generating these into `packages/domain-types`
 * from the OpenAPI document so web and mobile share one source; that generation step lands
 * with the shared package. Until then this file is the single place the shapes are declared,
 * and it must stay in step with the contract.
 */

export type Role = 'owner' | 'buyer' | 'branch_manager' | 'approver' | 'viewer';

export type Locale = 'en' | 'ar';

/** Money is never a bare number — Constitution Principle VII. */
export interface Money {
  readonly amount: string; // decimal string; never a float
  readonly currency: string; // ISO 4217
}

export interface Tenant {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly region: string;
  readonly currency: string;
  readonly tax_model: string;
  readonly default_locale: Locale;
  readonly created_at: string;
}

export interface Me {
  readonly id: string;
  readonly email: string;
  readonly role: Role;
  readonly preferred_locale: Locale | null;
  readonly mfa_enabled: boolean;
  readonly tenant: Tenant;
}

export interface Session {
  readonly access_token: string;
  readonly refresh_token: string;
  readonly expires_in: number;
  readonly user: Me;
}

export interface WorkspaceSummary {
  readonly tenant_id: string;
  readonly name: string;
  readonly role: Role;
  readonly is_active: boolean;
}

export interface Member {
  readonly id: string;
  readonly email: string;
  readonly role: Role;
  readonly status: 'active' | 'removed';
  readonly mfa_enabled: boolean;
  readonly created_at: string;
}

export interface Invitation {
  readonly id: string;
  readonly email: string;
  readonly role: Role;
  readonly status: 'pending' | 'accepted' | 'revoked' | 'expired';
  readonly expires_at: string;
}

export interface ReferenceOption {
  readonly code: string;
  readonly label_en: string;
  readonly label_ar: string;
}

export interface ConfigOptions {
  readonly regions: readonly ReferenceOption[];
  readonly currencies: readonly ReferenceOption[];
  readonly tax_models: readonly ReferenceOption[];
}

/** The API's error envelope. Every failure carries a trace_id for support. */
export interface ApiError {
  readonly code: string;
  readonly message: string;
  readonly details?: Record<string, unknown>;
  readonly trace_id: string;
}

// --- Catalogue and Suppliers (Chunk 4.2) ---

export interface BaseUnit {
  readonly code: string;
  readonly label_en: string;
  readonly label_ar: string;
  readonly dimension: 'volume' | 'mass' | 'count';
}

export interface PackDefinition {
  readonly pack_count: number;
  readonly unit_size: string; // decimal string
  readonly base_quantity?: string; // read-only derived decimal string
}

export interface Product {
  readonly id: string;
  readonly tenant_name: string;
  readonly brand?: string | null;
  readonly canonical_name: string;
  readonly variant?: string | null;
  readonly gtin?: string | null;
  readonly base_unit: string;
  readonly pack: PackDefinition;
  readonly preferred_supplier_id?: string | null;
  readonly substitute_ids?: readonly string[];
  readonly status: 'active' | 'archived';
  readonly created_at: string;
}

export interface ProductCreate {
  readonly tenant_name: string;
  readonly brand?: string | null;
  readonly canonical_name?: string | null;
  readonly variant?: string | null;
  readonly gtin?: string | null;
  readonly base_unit: string;
  readonly pack: PackDefinition;
  readonly preferred_supplier_id?: string | null;
}

export interface ProductUpdate {
  readonly tenant_name?: string;
  readonly gtin?: string | null;
  readonly pack?: PackDefinition;
  readonly preferred_supplier_id?: string | null;
}

export interface Supplier {
  readonly id: string;
  readonly name: string;
  readonly payment_terms?: string | null;
  readonly lead_time_days?: number | null;
  readonly minimum_order_value?: Money | null;
  readonly delivery_fee?: Money | null;
  readonly reliability_score?: string | null;
  readonly status: 'active' | 'preferred' | 'blocked' | 'archived';
  readonly created_at: string;
}

export interface SupplierCreate {
  readonly name: string;
  readonly payment_terms?: string | null;
  readonly lead_time_days?: number | null;
  readonly minimum_order_value?: Money | null;
  readonly delivery_fee?: Money | null;
}

export interface SupplierUpdate {
  readonly name?: string;
  readonly payment_terms?: string | null;
  readonly lead_time_days?: number | null;
  readonly minimum_order_value?: Money | null;
  readonly delivery_fee?: Money | null;
  readonly status?: 'active' | 'preferred' | 'blocked' | 'archived';
}

export type RefreshScheduleStatus = 'active' | 'paused' | 'due';

export interface RefreshSchedule {
  readonly id: string;
  readonly workspace_product_id: string;
  readonly supplier_id: string;
  readonly cadence_days: number;
  readonly status: RefreshScheduleStatus;
  readonly next_refresh_at: string;
  readonly last_observed_at?: string | null;
  readonly last_requested_at?: string | null;
  readonly last_error?: string | null;
  readonly source_import_id?: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface RefreshScheduleCreate {
  readonly workspace_product_id: string;
  readonly supplier_id: string;
  readonly cadence_days: number;
}

export interface RefreshScheduleUpdate {
  readonly cadence_days?: number;
  readonly status?: RefreshScheduleStatus;
  readonly source_import_id?: string;
}

export interface Alias {
  readonly id: string;
  readonly workspace_product_id: string;
  readonly supplier_id?: string | null;
  readonly alias_text: string;
  readonly created_at: string;
}

export interface ImportError {
  readonly line: number;
  readonly column?: string | null;
  readonly reason: string;
}

export interface ImportPreview {
  readonly import_id: string;
  readonly kind: 'products' | 'suppliers';
  readonly row_count: number;
  readonly valid: boolean;
  readonly missing_columns?: readonly string[];
  readonly unrecognised_columns?: readonly string[];
  readonly duplicates?: readonly ImportError[];
  readonly errors: readonly ImportError[];
  readonly preview?: readonly Record<string, unknown>[];
}

export interface ImportResult {
  readonly import_id: string;
  readonly created: number;
  readonly skipped: number;
  readonly updated: number;
}

// --- Quotation Inbox and Extraction (Chunk 4.3) ---

export type PresignMimeType =
  | 'application/pdf'
  | 'image/png'
  | 'image/jpeg'
  | 'image/tiff'
  | 'text/csv'
  | 'application/vnd.ms-excel'
  | 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

export interface PresignRequest {
  readonly filename: string;
  readonly mime_type: PresignMimeType;
  readonly size_bytes: number;
  readonly content_hash?: string | null;
}

export interface PotentialDuplicate {
  readonly quotation_id: string;
  readonly document_id: string;
  readonly created_at: string;
  readonly supplier_name?: string | null;
  readonly stated_total_amount?: string | null;
  readonly stated_total_currency?: string | null;
}

export interface PresignResponse {
  readonly document_id: string;
  readonly storage_bucket: string;
  readonly storage_path: string;
  readonly upload_url: string;
  readonly upload_fields?: Record<string, string>;
  readonly expires_at: string;
  readonly potential_duplicates?: readonly PotentialDuplicate[];
}

export interface Document {
  readonly id: string;
  readonly storage_bucket: string;
  readonly storage_path: string;
  readonly mime_type: string;
  readonly content_hash?: string | null;
  readonly source_channel: 'upload';
  readonly status: 'uploaded' | 'failed_to_read';
  readonly created_at: string;
  readonly created_by?: string;
}

export interface DocumentDownloadResponse {
  readonly download_url: string;
}

export interface QuotationCreate {
  readonly document_id: string;
  readonly supplier_id?: string | null;
}

export type QuotationStatus =
  | 'pending'
  | 'extracting'
  | 'extracted'
  | 'in_review'
  | 'reviewed'
  | 'refused';

export type ArithmeticStatus = 'not_applicable' | 'reconciled' | 'mismatch';

export interface Quotation {
  readonly id: string;
  readonly document_id: string;
  readonly supplier_id?: string | null;
  readonly suggested_supplier_id?: string | null;
  readonly supplier_match_confidence?: string | null;
  readonly currency?: string | null;
  readonly issue_date?: string | null;
  readonly expiry_date?: string | null;
  readonly status: QuotationStatus;
  readonly previous_quotation_id?: string | null;
  readonly stated_total?: Money | null;
  readonly arithmetic_status?: ArithmeticStatus | null;
  readonly created_at: string;
  readonly reviewed_by?: string | null;
  readonly reviewed_at?: string | null;
  readonly deleted_at?: string | null;
  readonly reviewer_notes?: string | null;
}

export interface QuotationPack {
  readonly pack_count: number;
  readonly unit_size: string; // decimal string
  readonly unit?: string | null;
}

export interface QuotationLine {
  readonly id: string;
  readonly line_number: number;
  readonly original_text: string;
  readonly quantity?: string | null; // decimal string
  readonly pack?: QuotationPack | null;
  readonly unit_price?: Money | null;
  readonly vat_rate?: string | null; // decimal string 0 to 1
  readonly delivery_fee?: Money | null;
  readonly discount?: Money | null;
}

export type ExtractionMethod = 'structured_parse' | 'bedrock' | 'azure_di';

export interface SourceRegion {
  readonly page?: number;
  readonly bbox?: readonly [number, number, number, number] | readonly number[];
  readonly [key: string]: unknown;
}

export interface FieldExtraction {
  readonly id: string;
  readonly quotation_id: string;
  readonly entity_type: 'quotation' | 'quotation_line';
  readonly entity_id: string;
  readonly field_name: string;
  readonly extracted_value: unknown;
  readonly confidence: string; // decimal string 0.0000 to 1.0000
  readonly source_page?: number | null;
  readonly source_region?: Record<string, unknown> | null;
  readonly extraction_method: ExtractionMethod;
  readonly model_version: string;
  readonly corrected_value?: unknown | null;
  readonly corrected_by?: string | null;
  readonly corrected_at?: string | null;
}

export interface FieldCorrection {
  readonly field_extraction_id: string;
  readonly corrected_value: unknown;
}

export interface NewQuotationLine {
  readonly original_text: string;
  readonly quantity?: string | null;
  readonly unit_price_amount?: string | null;
  readonly unit_price_currency?: string | null;
}

export interface QuotationReviewPatch {
  readonly supplier_id?: string | null;
  readonly reviewer_notes?: string | null;
  readonly corrections?: readonly FieldCorrection[];
  readonly add_lines?: readonly NewQuotationLine[];
  readonly remove_line_ids?: readonly string[];
}

export interface QuotationDetail extends Quotation {
  readonly document: Document;
  readonly lines: readonly QuotationLine[];
  readonly field_extractions: readonly FieldExtraction[];
  readonly review_task?: ReviewTask | null;
  readonly uploaded_by_email?: string | null;
  readonly reviewed_by_email?: string | null;
  readonly suggested_supplier_name?: string | null;
}

export interface AuditTrailEntry {
  readonly id: number;
  readonly action: string;
  readonly actor_email: string | null;
  readonly outcome: string;
  readonly target: Record<string, unknown> | null;
  readonly trace_id: string | null;
  readonly occurred_at: string;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface Job {
  readonly id: string;
  readonly quotation_id: string;
  readonly status: JobStatus;
  readonly attempted_provider?: ExtractionMethod | null;
  readonly error?: Record<string, unknown> | null;
  readonly result_url?: string | null;
  readonly created_at: string;
  readonly started_at?: string | null;
  readonly completed_at?: string | null;
}

export type ReviewTaskStatus = 'open' | 'in_progress' | 'resolved';
export type ReviewTaskPriority = 'low' | 'normal' | 'high';
export type ReviewTaskReason =
  | 'low_confidence'
  | 'arithmetic_mismatch'
  | 'read_failure'
  | 'review_required'
  | 'no_supplier_match';

export interface ReviewTask {
  readonly id: string;
  readonly quotation_id: string;
  readonly status: ReviewTaskStatus;
  readonly priority: ReviewTaskPriority;
  readonly reason: ReviewTaskReason;
  readonly created_at: string;
  readonly resolved_at?: string | null;
  readonly supplier_name?: string | null;
  readonly stated_total?: Money | null;
}

// --- Matching and Normalisation (Chunk 4.4) ---

export type MatchOutcome =
  | 'same_product'
  | 'different_pack'
  | 'different_variant'
  | 'compatible_alternative'
  | 'no_match_new_product';

export type MatchTaskStatus = 'open' | 'in_progress' | 'resolved' | 'auto_accepted';
export type MatchTaskPriority = 'low' | 'normal' | 'high';
export type MatchTaskReason =
  | 'low_confidence'
  | 'close_candidates'
  | 'no_candidate'
  | 'alias_conflict'
  | 'auto_accepted';

export interface ProductSummary {
  readonly id: string;
  readonly tenant_name: string;
  readonly brand?: string | null;
  readonly canonical_name: string;
  readonly variant?: string | null;
  readonly gtin?: string | null;
  readonly base_unit: string;
  readonly status: 'active' | 'archived';
}

export interface QuotationLineSummary {
  readonly id: string;
  readonly line_number: number;
  readonly original_text: string;
  readonly quantity?: string | null;
  readonly pack?: QuotationPack | null;
  readonly unit_price?: Money | null;
  readonly vat_rate?: string | null;
  readonly delivery_fee?: Money | null;
  readonly discount?: Money | null;
  readonly quoted_line_total?: Money | null;
  readonly quoted_line_total_issue?: 'currency_mismatch' | null;
}

export interface FeatureScore {
  readonly brand_match: string;
  readonly variant_match: string;
  readonly pack_unit_match: string;
  readonly pack_size_plausibility: string;
  readonly price_plausibility: string;
}

export interface MatchReason {
  readonly alias_hit: boolean;
  readonly gtin_match: boolean;
  readonly supplier_code_match: boolean;
  readonly lexical_similarity: string;
  readonly semantic_similarity: string;
  readonly feature_score: FeatureScore;
}

export interface MatchCandidate {
  readonly id: string;
  readonly quotation_line_id: string;
  readonly candidate_product: ProductSummary;
  readonly confidence: string; // decimal string 0.0000 to 1.0000
  readonly reasons: MatchReason;
  readonly rank: number;
  readonly scoring_version: string;
  readonly embedding_model?: string | null;
  readonly created_at: string;
}

export interface MatchDecision {
  readonly id: string;
  readonly quotation_line_id: string;
  readonly matched_product: ProductSummary;
  readonly selected_match_candidate_id?: string | null;
  readonly outcome: MatchOutcome;
  readonly is_automatic: boolean;
  readonly decided_by?: string | null;
  readonly decided_at: string;
  readonly confidence: string;
  readonly alias_id?: string | null;
}

export interface QuotationMatchSummary {
  readonly id: string;
  readonly status: string;
  readonly document_id?: string | null;
  readonly source_filename?: string | null;
  readonly supplier_id?: string | null;
  readonly issue_date?: string | null;
  readonly reviewed_at?: string | null;
  readonly reviewed_by?: string | null;
  readonly reviewed_by_email?: string | null;
  readonly line_count: number;
  readonly open_match_task_count: number;
  readonly supplier_name?: string | null;
}

export interface MatchTask {
  readonly id: string;
  readonly quotation_id: string;
  readonly quotation: QuotationMatchSummary;
  readonly quotation_line: QuotationLineSummary;
  readonly status: MatchTaskStatus;
  readonly priority: MatchTaskPriority;
  readonly reason: MatchTaskReason;
  readonly candidates: readonly MatchCandidate[];
  readonly decision?: MatchDecision | null;
  readonly created_at: string;
  readonly resolved_at?: string | null;
  readonly supplier_name?: string | null;
}

export interface MatchQueueCandidateSummary {
  readonly product_name: string;
  readonly confidence: string;
}

export interface MatchQueueItem {
  readonly id: string;
  readonly quotation_id: string;
  readonly quotation: QuotationMatchSummary;
  readonly quotation_line: QuotationLineSummary;
  readonly status: MatchTaskStatus;
  readonly priority: MatchTaskPriority;
  readonly reason: MatchTaskReason;
  readonly top_candidate?: MatchQueueCandidateSummary | null;
  readonly created_at: string;
  readonly resolved_at?: string | null;
  readonly supplier_name?: string | null;
}

export type CatalogueRefreshReviewStatus =
  | 'pending_review'
  | 'processing'
  | 'approved'
  | 'rejected';

export interface CatalogueRefreshReviewRow {
  readonly provider_record_id?: string | null;
  readonly product_name: string;
  readonly unit_price_amount: string;
  readonly unit_price_currency: string;
  readonly base_unit: string;
  readonly observed_at?: string | null;
  readonly valid_from?: string | null;
  readonly valid_to?: string | null;
  readonly supplier_sku?: string | null;
}

export interface CatalogueRefreshReview {
  readonly id: string;
  readonly refresh_schedule_id: string;
  readonly source_import_id: string;
  readonly supplier_id: string;
  readonly status: CatalogueRefreshReviewStatus;
  readonly normalized_rows: readonly CatalogueRefreshReviewRow[];
  readonly errors: readonly (Record<string, unknown> | string)[];
  readonly row_count: number;
  readonly error_count: number;
  readonly created_at: string;
  readonly reviewed_at?: string | null;
  readonly reviewed_by?: string | null;
  readonly source_file_name: string;
  readonly source_file_format: 'csv' | 'xlsx';
}

export interface CatalogueRefreshReviewDecision {
  readonly review_id: string;
  readonly status: 'approved' | 'rejected';
  readonly catalogue_import_id?: string | null;
  readonly supplier_id?: string | null;
  readonly imported_rows?: number | null;
  readonly error_rows?: number | null;
}

export interface MatchResolutionRequest {
  readonly outcome: MatchOutcome;
  readonly selected_match_candidate_id?: string | null;
  readonly create_product?: ProductCreate | null;
}

export interface LandedCost {
  readonly id: string;
  readonly quotation_line_id: string;
  readonly match_decision_id: string;
  readonly quantity: string;
  readonly normalised_base_quantity: string;
  readonly base_unit: string;
  readonly unit_price: Money;
  readonly vat_amount: Money;
  readonly delivery_fee: Money;
  readonly discount: Money;
  readonly other_charges: Money;
  readonly total: Money;
  readonly raw_inputs: Record<string, unknown>;
  readonly rule_version: string;
  readonly valid_from: string;
  readonly valid_to?: string | null;
  readonly recorded_at: string;
  readonly created_at: string;
}

export interface QuotationLineMatchState {
  readonly line: QuotationLineSummary;
  readonly candidates: readonly MatchCandidate[];
  readonly task?: MatchTask | null;
  readonly decision?: MatchDecision | null;
  readonly landed_cost?: LandedCost | null;
}

export interface QuotationMatches {
  readonly quotation_id: string;
  readonly lines: readonly QuotationLineMatchState[];
}

// --- Smart Compare and Intelligence (Chunk 4.5) ---

export interface ProductRef {
  readonly id: string;
  readonly tenant_name: string;
}

export type StockSignal = 'in_stock' | 'low_stock' | 'out_of_stock' | 'unknown';

export interface Offer {
  readonly id: string;
  readonly workspace_product_id: string;
  readonly supplier_id: string;
  readonly supplier_name: string;
  readonly quotation_line_id: string;
  readonly match_decision_id: string;
  readonly landed_cost: Money;
  readonly normalised_unit_price: Money;
  readonly requested_quantity: string;
  readonly base_unit: string;
  readonly lead_time_days?: number | null;
  readonly reliability_score?: string | null;
  readonly stock_signal?: StockSignal | null;
  readonly match_confidence: string;
  readonly valid_from: string;
  readonly valid_to?: string | null;
  readonly is_expired: boolean;
  readonly rule_version: string;
  readonly recorded_at: string;
}

export type RecommendationConfidence = 'high' | 'medium' | 'low';
export type RecommendationRiskNote =
  | 'price_expiring_soon'
  | 'low_match_confidence'
  | 'low_supplier_reliability'
  | 'high_supplier_risk'
  | 'supplier_quality_risk'
  | 'elevated_supplier_risk'
  | (string & {});

export interface RecommendationWeights {
  readonly cost: string;
  readonly match_confidence: string;
  readonly reliability: string;
  readonly lead_time: string;
  readonly supplier_risk?: string;
  readonly [key: string]: string | undefined;
}

export interface RecommendationTieBreak {
  readonly applied: boolean;
  readonly rule: readonly string[];
}

export interface RecommendationEvidence {
  readonly weights: RecommendationWeights;
  readonly components: Record<string, string>;
  readonly winning_margin?: string | null;
  readonly tie_break: RecommendationTieBreak;
}

export interface Recommendation {
  readonly recommended_offer_id: string;
  readonly score: string;
  readonly confidence: RecommendationConfidence;
  readonly valid_from: string;
  readonly valid_to?: string | null;
  readonly risk_notes: readonly RecommendationRiskNote[];
  readonly evidence: RecommendationEvidence;
}

export interface OfferComparison {
  readonly product: ProductRef;
  readonly requested_quantity: string;
  readonly offers: readonly Offer[];
  readonly recommendation: Recommendation | null;
}

export interface PriceHistoryPoint {
  readonly landed_cost_id: string;
  readonly workspace_product_id: string;
  readonly supplier_id: string;
  readonly supplier_name: string;
  readonly recorded_at: string;
  readonly valid_from: string;
  readonly valid_to?: string | null;
  readonly normalised_unit_price: Money;
  readonly landed_cost_total: Money;
  readonly quantity: string;
  readonly base_unit: string;
}

export interface PriceHistoryMetric {
  readonly value: Money;
  readonly source_landed_cost_ids: readonly string[];
}

export interface PriceHistorySummary {
  readonly last_paid: PriceHistoryMetric | null;
  readonly average_paid_rolling_window: PriceHistoryMetric | null;
  readonly best_price: PriceHistoryMetric | null;
}

export interface PriceHistoryResponse {
  readonly product: ProductRef;
  readonly window_months: number;
  readonly points: readonly PriceHistoryPoint[];
  readonly summary: PriceHistorySummary;
  readonly next_cursor: string | null;
}

export interface BasketItemRequest {
  readonly workspace_product_id: string;
  readonly quantity: string;
}

export interface OptimisationWeights {
  readonly price: number;
  readonly preferred_supplier: number;
  readonly risk: number;
  readonly lead_time: number;
  readonly quality: number;
}

export type RiskTolerance = 'low' | 'medium' | 'high';
export type UrgencyLevel = 'normal' | 'urgent';

export interface BasketOptimiseRequest {
  readonly supplier_ids: readonly [string, string] | readonly string[];
  readonly items: readonly BasketItemRequest[];
  readonly risk_tolerance?: RiskTolerance;
  readonly urgency?: UrgencyLevel;
  readonly excluded_supplier_ids?: readonly string[];
  readonly weights?: OptimisationWeights;
}

export interface AllocatedBasketLine {
  readonly workspace_product_id: string;
  readonly quantity: string;
  readonly offer_id: string;
  readonly landed_cost: Money;
}

export interface SupplierAllocation {
  readonly supplier_id: string;
  readonly lines: readonly AllocatedBasketLine[];
  readonly total_landed_cost: Money;
}

export interface SingleSupplierBaseline {
  readonly supplier_id: string;
  readonly feasible: boolean;
  readonly total_landed_cost: Money | null;
  readonly violated_constraints?: readonly ViolatedOptimisationConstraint[];
}

export interface InfeasibleBasketItem {
  readonly workspace_product_id: string;
  readonly requested_quantity: string;
  readonly reason: 'no_offer_from_named_suppliers';
  readonly missing_supplier_ids: readonly string[];
}

export interface OptimisationConstraint {
  readonly kind: string;
  readonly supplier_id?: string | null;
  readonly workspace_product_id?: string | null;
  readonly description?: string;
  readonly money?: Money | null;
  readonly source_ids?: readonly string[];
  readonly parameters?: Record<string, unknown>;
  /** @deprecated legacy alias */
  readonly type?: string;
}

export interface ViolatedOptimisationConstraint extends OptimisationConstraint {
  readonly reason?: string;
  readonly details?: Record<string, unknown>;
}

export interface BasketSplitResult {
  readonly feasible: boolean;
  readonly allocation: readonly SupplierAllocation[];
  readonly total_landed_cost: Money | null;
  readonly single_supplier_baselines?: readonly SingleSupplierBaseline[];
  readonly infeasible_items: readonly InfeasibleBasketItem[];
  readonly applied_constraints?: readonly OptimisationConstraint[];
  readonly violated_constraints?: readonly ViolatedOptimisationConstraint[];
  readonly risk_notes?: readonly string[];
  readonly confidence?: 'high' | 'medium' | 'low';
  readonly source_landed_cost_ids?: readonly string[];
  readonly solver_version?: string | null;
  readonly computed_at: string;
  readonly valid_until?: string | null;
}

export type BasketSplitJobStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface BasketSplitJob {
  readonly id: string;
  readonly supplier_ids: readonly string[];
  readonly items: readonly BasketItemRequest[];
  readonly status: BasketSplitJobStatus;
  readonly result?: BasketSplitResult | null;
  readonly error?: Record<string, unknown> | null;
  readonly result_url: string;
  readonly created_at: string;
  readonly started_at?: string | null;
  readonly completed_at?: string | null;
}

// --- R2.4 Supplier IQ & Scorecards ---------------------------------------

export type ScorecardConfidence = 'high' | 'medium' | 'low';

export interface SupplierScoreMetric {
  readonly value: string | null;
  readonly sample_count: number;
  readonly source_ids?: readonly string[];
  readonly confidence: ScorecardConfidence;
  readonly insufficient_evidence: boolean;
  readonly window_start?: string;
  readonly window_end?: string;
}

export interface SupplierRiskSubScore {
  readonly name: string;
  readonly score: string;
  readonly weight: string;
  readonly evidence?: Record<string, unknown>;
}

export interface SupplierRiskScore {
  readonly total: string;
  readonly confidence: ScorecardConfidence;
  readonly sub_scores: readonly SupplierRiskSubScore[];
  readonly rule_version: string;
}

export interface SupplierScorecard {
  readonly supplier_id: string;
  readonly window_start: string;
  readonly window_end: string;
  readonly metrics: Record<string, SupplierScoreMetric>;
  readonly risk_score: SupplierRiskScore;
  readonly source_counts: Record<string, number>;
  readonly confidence: ScorecardConfidence;
  readonly insufficient_evidence: boolean;
  readonly computed_at: string;
  readonly rule_version: string;
}

// --- R2.4 Commercial Terms ------------------------------------------------

export interface SupplierQuantityTier {
  readonly workspace_product_id?: string | null;
  readonly min_quantity: string;
  readonly unit_price: Money;
}

export interface SupplierCommercialTermCreate {
  readonly effective_from: string;
  readonly effective_to?: string | null;
  readonly minimum_order_value?: Money | null;
  readonly delivery_fee?: Money | null;
  readonly free_delivery_threshold?: Money | null;
  readonly quantity_tiers?: readonly SupplierQuantityTier[];
}

export interface SupplierCommercialTerm extends SupplierCommercialTermCreate {
  readonly id: string;
  readonly supplier_id: string;
  readonly rule_version: string;
  readonly created_at: string;
}

// --- Alerts & Anomalies --------------------------------------------------

export type AlertKind =
  | 'recommended_price_expiring'
  | 'preferred_supplier_offer_disappeared'
  | 'price_swing'
  | 'price_spike'
  | 'likely_duplicate_quotation_line'
  | 'decimal_or_quantity_anomaly'
  | 'delivery_cost_anomaly'
  | 'supplier_quality_trend_change';

export type AlertSeverity = 'info' | 'warning' | 'critical';

export type AlertAction =
  | 'compare_product'
  | 'review_supplier'
  | 'view_price_history'
  | 'inspect_scorecard'
  | 'review_quotation'
  | 'view_delivery_issues';

export interface Alert {
  readonly id: string;
  readonly kind: AlertKind;
  readonly workspace_product_id: string;
  readonly supplier_id?: string | null;
  readonly severity: AlertSeverity;
  readonly confidence?: ScorecardConfidence;
  readonly evidence: Record<string, unknown>;
  readonly action: AlertAction;
  readonly created_from_current_data_at: string;
  readonly dismissed: boolean;
}

export interface AlertDismissal {
  readonly alert_id: string;
  readonly dismissed_at: string;
}

// --- value proof, exports & billing (Chunk 4.6) ---------------------------

export type SavingStatus = 'pending' | 'verified';

export type BaselinePolicy = 'last_paid' | 'rolling_average_6m' | 'none_available';

export type PurchaseDeliveryResult =
  | 'ordered'
  | 'partially_delivered'
  | 'delivered'
  | 'cancelled'
  | 'disputed';

export interface PurchaseOutcomeCreate {
  readonly workspace_product_id: string;
  readonly supplier_id?: string | null;
  readonly quotation_line_id?: string | null;
  readonly match_decision_id?: string | null;
  readonly landed_cost_id?: string | null;
  readonly quantity: string;
  readonly base_unit: string;
  readonly unit_price: Money;
  readonly total_paid: Money;
  readonly delivery_result: PurchaseDeliveryResult;
  readonly ordered_at?: string | null;
  readonly delivered_at?: string | null;
  readonly notes?: string | null;
}

export interface PurchaseRecord {
  readonly id: string;
  readonly workspace_product_id: string;
  readonly supplier_id?: string | null;
  readonly quotation_line_id?: string | null;
  readonly match_decision_id?: string | null;
  readonly landed_cost_id?: string | null;
  readonly quantity: string;
  readonly base_unit: string;
  readonly unit_price: Money;
  readonly total_paid: Money;
  readonly delivery_result: PurchaseDeliveryResult;
  readonly ordered_at?: string | null;
  readonly delivered_at?: string | null;
  readonly recorded_by: string;
  readonly recorded_at: string;
  readonly notes?: string | null;
}

export interface SavingRecord {
  readonly id: string;
  readonly purchase_record_id: string;
  readonly workspace_product_id: string;
  readonly supplier_id?: string | null;
  readonly status: SavingStatus;
  readonly baseline_policy: BaselinePolicy;
  readonly baseline_source_landed_cost_ids: readonly string[];
  readonly baseline_unit_price?: Money | null;
  readonly baseline_value?: Money | null;
  readonly actual_value: Money;
  readonly delta?: Money | null;
  readonly calculation_version: string;
  readonly calculation_inputs: Record<string, unknown>;
  readonly recorded_by: string;
  readonly recorded_at: string;
  readonly verified_by?: string | null;
  readonly verified_at?: string | null;
}

export interface PurchaseOutcomeCreated {
  readonly purchase_record: PurchaseRecord;
  readonly saving_record: SavingRecord;
}

export interface SavingList {
  readonly items: readonly SavingRecord[];
  readonly next_cursor: string | null;
}

export interface SavingCalculationEvidence {
  readonly baseline_policy: BaselinePolicy;
  readonly baseline_value: Money | null;
  readonly actual_value: Money;
  readonly delta: Money | null;
  readonly source_landed_cost_ids: readonly string[];
  readonly calculation_inputs?: Record<string, unknown>;
}

export interface SavingEvidence {
  readonly saving_record: SavingRecord;
  readonly purchase_record: PurchaseRecord;
  readonly quotation?: Record<string, unknown> | null;
  readonly match_decision?: Record<string, unknown> | null;
  readonly competing_offers: readonly Record<string, unknown>[];
  readonly calculation: SavingCalculationEvidence;
}

export type ExportFormat = 'xlsx' | 'pdf' | 'csv';

export type ExportStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface ExportFilters {
  readonly period_start: string;
  readonly period_end: string;
  readonly supplier_id?: string | null;
  readonly branch_id?: string | null;
}

export interface ExportCreate {
  readonly kind?: 'savings_ledger' | 'spend_by_supplier' | 'alerts_summary';
  readonly format: ExportFormat;
  readonly filters: ExportFilters;
  readonly locale?: 'en' | 'ar';
}

export interface ExportJob {
  readonly id: string;
  readonly kind: 'savings_ledger';
  readonly format: ExportFormat;
  readonly filters: ExportFilters;
  readonly status: ExportStatus;
  readonly row_count?: number | null;
  readonly download_url?: string | null;
  readonly error?: Record<string, unknown> | null;
  readonly created_at: string;
  readonly started_at?: string | null;
  readonly completed_at?: string | null;
}

export interface PlanLimits {
  readonly active_catalogue_products: number;
}

export interface Plan {
  readonly code: string;
  readonly name: string;
  readonly status: 'active' | 'archived';
  readonly monthly_price: Money;
  readonly limits: PlanLimits;
  readonly features: Record<string, unknown>;
}

export interface BillingAccount {
  readonly id: string;
  readonly plan: Plan;
  readonly provider: 'stub';
  readonly provider_customer_id: string;
  readonly provider_subscription_id?: string | null;
  readonly status: 'active' | 'past_due' | 'cancelled';
  readonly current_period_start?: string | null;
  readonly current_period_end?: string | null;
  readonly assigned_at: string;
}

export interface LimitCheck {
  readonly resource: 'active_catalogue_products';
  readonly plan_code: string;
  readonly limit: number | null;
  readonly used: number;
  readonly allowed: boolean;
  readonly remaining: number | null;
}

// --- Organisation Model (007) ----------------------------------------------

export type BudgetScope = 'organisation' | 'branch' | 'cost_centre';

export type BudgetPeriod = 'monthly' | 'quarterly' | 'annual';

export interface Branch {
  readonly id: string;
  readonly name: string;
  readonly address?: string | null;
  readonly region?: string | null;
  readonly is_active: boolean;
  readonly created_at: string;
  readonly updated_at?: string;
}

export interface BranchCreate {
  readonly name: string;
  readonly address?: string | null;
  readonly region?: string | null;
}

export interface BranchUpdate {
  readonly name?: string;
  readonly address?: string | null;
  readonly region?: string | null;
  readonly is_active?: boolean;
  readonly confirm_dependents?: boolean;
}

export interface BranchList {
  readonly items: readonly Branch[];
  readonly next_cursor: string | null;
}

export type OrphanReason = 'branch_deactivated' | 'owner_removed';

export interface CostCentre {
  readonly id: string;
  readonly name: string;
  readonly code: string;
  readonly budget_owner_membership_id?: string | null;
  readonly branch_id?: string | null;
  readonly is_orphaned: boolean;
  /** Computed at read time by the API — never stored. Null whenever is_orphaned is false. */
  readonly orphan_reason?: OrphanReason | null;
  readonly is_archived: boolean;
  readonly created_at: string;
  readonly updated_at?: string;
}

export interface CostCentreCreate {
  readonly name: string;
  readonly code: string;
  readonly budget_owner_membership_id?: string | null;
  readonly branch_id?: string | null;
}

export interface CostCentreUpdate {
  readonly name?: string;
  readonly code?: string;
  readonly budget_owner_membership_id?: string | null;
  readonly branch_id?: string | null;
  readonly is_archived?: boolean;
}

export interface CostCentreList {
  readonly items: readonly CostCentre[];
  readonly next_cursor: string | null;
}

export interface Budget {
  readonly id: string;
  readonly amount: Money; // nested Money on read
  readonly period: BudgetPeriod;
  readonly period_start: string;
  readonly scope: BudgetScope;
  readonly branch_id?: string | null;
  readonly cost_centre_id?: string | null;
  readonly created_by?: string;
  readonly created_at: string;
}

export interface BudgetCreate {
  readonly amount: string; // flat decimal string on create — deliberate contract asymmetry
  readonly currency: string; // ISO 4217
  readonly period: BudgetPeriod;
  readonly period_start: string;
  readonly scope: BudgetScope;
  readonly branch_id?: string | null;
  readonly cost_centre_id?: string | null;
}

export interface BudgetCreated extends Budget {
  readonly overlap_warning: boolean;
}

export interface BudgetList {
  readonly items: readonly Budget[];
  readonly next_cursor: string | null;
}

export interface BranchRoleAssignment {
  readonly id: string;
  readonly membership_id: string;
  readonly branch_id: string;
  readonly created_at: string;
}

export interface BranchRoleAssignmentCreate {
  readonly membership_id: string;
  readonly branch_id: string;
}

// --- requests + approvals (008) ---------------------------------------------

export type PurchaseRequestStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'withdrawn';
export type ApprovalStepStatus = 'pending' | 'approved' | 'rejected';
export type ApprovalStepSource = 'threshold_match' | 'delegate' | 'owner_fallback';

export interface BudgetStatus {
  readonly remaining_amount: Money;
  readonly exceeds: boolean;
}

export interface PurchaseRequestLine {
  readonly id: string;
  readonly workspace_product_id: string;
  readonly quantity: string;
  readonly note?: string | null;
  readonly estimated_unit_price?: Money | null;
  readonly estimated_unit_price_source_landed_cost_id?: string | null;
}

export interface PurchaseRequestLineInput {
  readonly workspace_product_id: string;
  readonly quantity: string;
  readonly note?: string | null;
}

export interface ApprovalStep {
  readonly id: string;
  readonly assigned_membership_id: string;
  readonly source: ApprovalStepSource;
  readonly status: ApprovalStepStatus;
  readonly comment?: string | null;
  readonly decided_by_membership_id?: string | null;
  readonly decided_at?: string | null;
}

export interface PurchaseRequest {
  readonly id: string;
  readonly branch_id: string;
  readonly cost_centre_id?: string | null;
  readonly requested_by_membership_id: string;
  readonly required_by_date: string;
  readonly status: PurchaseRequestStatus;
  readonly lines: readonly PurchaseRequestLine[];
  readonly estimated_total?: Money | null;
  readonly has_incomplete_estimate: boolean;
  readonly budget_status?: BudgetStatus | null;
  readonly approval_step?: ApprovalStep | null;
  readonly submitted_at?: string | null;
  readonly withdrawn_at?: string | null;
  readonly created_at: string;
  readonly updated_at?: string;
}

export interface PurchaseRequestCreate {
  readonly branch_id: string;
  readonly cost_centre_id?: string | null;
  readonly required_by_date: string;
  readonly lines: readonly PurchaseRequestLineInput[];
}

export interface PurchaseRequestUpdate {
  readonly branch_id?: string;
  readonly cost_centre_id?: string | null;
  readonly required_by_date?: string;
  readonly lines?: readonly PurchaseRequestLineInput[];
}

export interface PurchaseRequestList {
  readonly items: readonly PurchaseRequest[];
  readonly next_cursor: string | null;
}

export interface ApprovalDecisionInput {
  readonly comment?: string | null;
}

export interface ThresholdRule {
  readonly id: string;
  readonly branch_id?: string | null;
  readonly min_amount: string;
  readonly max_amount?: string | null;
  readonly currency: string;
  readonly approver_membership_id: string;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at?: string;
}

export interface ThresholdRuleCreate {
  readonly branch_id?: string | null;
  readonly min_amount: string;
  readonly max_amount?: string | null;
  readonly currency: string;
  readonly approver_membership_id: string;
}

export interface ThresholdRuleUpdate {
  readonly branch_id?: string | null;
  readonly min_amount?: string;
  readonly max_amount?: string | null;
  readonly currency?: string;
  readonly approver_membership_id?: string;
}

export interface ThresholdRuleList {
  readonly items: readonly ThresholdRule[];
  readonly next_cursor: string | null;
}

export interface ApprovalDelegation {
  readonly id: string;
  readonly delegator_membership_id: string;
  readonly delegate_membership_id: string;
  readonly starts_on: string;
  readonly ends_on: string;
  readonly created_at: string;
}

export interface ApprovalDelegationCreate {
  readonly delegator_membership_id?: string | null;
  readonly delegate_membership_id: string;
  readonly starts_on: string;
  readonly ends_on: string;
}

export interface ApprovalDelegationList {
  readonly items: readonly ApprovalDelegation[];
}
