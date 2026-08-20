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

