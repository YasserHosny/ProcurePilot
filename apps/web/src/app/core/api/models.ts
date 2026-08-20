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

export interface PresignResponse {
  readonly document_id: string;
  readonly storage_bucket: string;
  readonly storage_path: string;
  readonly upload_url: string;
  readonly upload_fields?: Record<string, string>;
  readonly expires_at: string;
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

export interface QuotationReviewPatch {
  readonly supplier_id?: string | null;
  readonly corrections?: readonly FieldCorrection[];
}

export interface QuotationDetail extends Quotation {
  readonly document: Document;
  readonly lines: readonly QuotationLine[];
  readonly field_extractions: readonly FieldExtraction[];
  readonly review_task?: ReviewTask | null;
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
  | 'review_required';

export interface ReviewTask {
  readonly id: string;
  readonly quotation_id: string;
  readonly status: ReviewTaskStatus;
  readonly priority: ReviewTaskPriority;
  readonly reason: ReviewTaskReason;
  readonly created_at: string;
  readonly resolved_at?: string | null;
}

