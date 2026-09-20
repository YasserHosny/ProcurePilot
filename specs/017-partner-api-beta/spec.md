# Feature Specification: Partner API Beta

**Feature Branch**: `017-partner-api-beta`  
**Roadmap Release**: R3.4, Phase 3 Connected Operations  
**Status**: First increment implemented

## User Stories

### User Story 1 - Read order evidence from an external system (Priority: P1)

An authorised integration consumer reads a tenant's purchase orders and a single order's
confirmation and receipt evidence without using the web UI.

**Acceptance Scenarios**

1. **Given** a valid Supabase JWT for tenant A, **When** the consumer requests the partner order
   list, **Then** only tenant A orders are returned with cursor pagination capped at 100.
2. **Given** a valid JWT for tenant A and an order ID belonging to tenant B, **When** the consumer
   requests that order, **Then** the API returns the standard not-found response.
3. **Given** a valid JWT, **When** the consumer reads an order, **Then** lifecycle evidence,
   quantities, status, and all monetary values include their existing explicit domain fields.

### User Story 2 - Read the tenant catalogue (Priority: P1)

An authorised integration consumer reads the tenant's normalised catalogue using the same
provider-neutral product projection as the web API.

**Acceptance Scenarios**

1. **Given** a valid JWT, **When** the consumer requests catalogue products, **Then** results are
   tenant-scoped, filterable by status and query text, and cursor-paginated.
2. **Given** no bearer token or an invalid token, **When** the consumer requests any partner
   resource, **Then** the request is rejected by the existing authentication envelope.

## Requirements

- **FR-001**: The partner beta MUST expose read-only order list, order detail, and catalogue
  product list endpoints under `/api/v1/partner`.
- **FR-002**: Partner routes MUST resolve tenancy only through the verified Supabase JWT and the
  existing `CurrentMember` dependency; tenant IDs MUST NOT be accepted from request paths,
  queries, or headers.
- **FR-003**: Cross-tenant reads MUST behave as not found through the existing tenant-scoped
  services and database RLS policies.
- **FR-004**: Pagination limits MUST be at least 1 and at most 100, using the existing cursor
  convention.
- **FR-005**: The beta MUST NOT expose mutation routes, API-key tenancy, provider-specific
  schemas, or webhook delivery in this increment.
- **FR-006**: All responses MUST reuse domain projections with explicit currencies and source
  evidence rather than flattening money or provenance into untyped fields.

## Out of Scope

API-key exchange, outbound webhooks, freshness scheduling, write operations, and provider-specific
connector payloads are separate R3.4 increments.
