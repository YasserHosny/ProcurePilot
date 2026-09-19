from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

type ApiEnvironment = Literal["local", "staging", "production"]
type Locale = Literal["en", "ar"]
type LogLevel = Literal["debug", "info", "warning", "error", "critical"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    api_host: str = Field(validation_alias="API_HOST")
    api_port: int = Field(validation_alias="API_PORT")
    api_env: ApiEnvironment = Field(validation_alias="API_ENV")
    api_log_level: LogLevel = Field(validation_alias="API_LOG_LEVEL")
    api_cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        validation_alias="API_CORS_ORIGINS"
    )

    supabase_url: str = Field(validation_alias="SUPABASE_URL")
    supabase_anon_key: SecretStr = Field(validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: SecretStr = Field(validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    # Optional: Supabase signs access tokens with asymmetric keys (ES256) and publishes the
    # public half via JWKS. The shared secret is only needed by deployments still issuing HS256.
    supabase_jwt_secret: SecretStr | None = Field(
        default=None, validation_alias="SUPABASE_JWT_SECRET"
    )
    supabase_jwt_audience: str = Field(validation_alias="SUPABASE_JWT_AUDIENCE")
    supabase_jwt_issuer: str = Field(validation_alias="SUPABASE_JWT_ISSUER")

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")

    platform_invitation_ttl_days: int = Field(validation_alias="PLATFORM_INVITATION_TTL_DAYS", gt=0)
    member_invitation_ttl_days: int = Field(validation_alias="MEMBER_INVITATION_TTL_DAYS", gt=0)

    rate_limit_auth: str = Field(validation_alias="RATE_LIMIT_AUTH")
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    extraction_queue_name: str = Field(
        default="quotation-extraction", validation_alias="EXTRACTION_QUEUE_NAME"
    )
    basket_split_queue_name: str = Field(
        default="basket-split", validation_alias="BASKET_SPLIT_QUEUE_NAME"
    )
    export_queue_name: str = Field(default="exports", validation_alias="EXPORT_QUEUE_NAME")
    digest_queue_name: str = Field(default="digests", validation_alias="DIGEST_QUEUE_NAME")
    extraction_provider_mode: Literal["stub", "bedrock", "azure_di"] = Field(
        default="stub", validation_alias="EXTRACTION_PROVIDER_MODE"
    )
    extraction_confidence_threshold: float = Field(
        default=0.85, validation_alias="EXTRACTION_CONFIDENCE_THRESHOLD", ge=0, le=1
    )
    quotation_documents_bucket: str = Field(
        default="quotation-documents", validation_alias="QUOTATION_DOCUMENTS_BUCKET"
    )
    quality_issue_photos_bucket: str = Field(
        default="quality-issue-photos", validation_alias="QUALITY_ISSUE_PHOTOS_BUCKET"
    )
    supabase_exports_bucket: str = Field(
        default="exports", validation_alias="SUPABASE_EXPORTS_BUCKET"
    )
    export_download_url_ttl_seconds: int = Field(
        default=300, validation_alias="EXPORT_DOWNLOAD_URL_TTL_SECONDS", ge=60, le=3600
    )
    export_retention_days: int = Field(default=90, validation_alias="EXPORT_RETENTION_DAYS", ge=1)
    export_row_cap: int = Field(default=10_000, validation_alias="EXPORT_ROW_CAP", ge=1)

    # T035 (012-reporting-hardening, FR-020): per-tenant-member request-rate limits on the
    # mutation endpoints that spend worker/storage resources, keyed by verified tenant+member
    # claims rather than IP (see shared/rate_limit.py) — an office NAT'd behind one IP must not
    # share a single bucket across members, and one tenant's traffic must not exhaust another's.
    rate_limit_export_create: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_EXPORT_CREATE"
    )
    rate_limit_schedule_mutation: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_SCHEDULE_MUTATION"
    )
    rate_limit_digest_mutation: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_DIGEST_MUTATION"
    )
    rate_limit_ingestion_config_mutation: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_INGESTION_CONFIG_MUTATION"
    )
    rate_limit_inbound_email_webhook: str = Field(
        default="60/minute", validation_alias="RATE_LIMIT_INBOUND_EMAIL_WEBHOOK"
    )
    # Business-rule caps (distinct from the request-rate limits above): each recurring schedule
    # or subscription is itself a standing worker cost, so the count of *active* rows per member
    # is capped independently of how fast they were created.
    active_schedule_cap_per_member: int = Field(
        default=20, validation_alias="ACTIVE_SCHEDULE_CAP_PER_MEMBER", ge=1
    )
    active_digest_subscription_cap_per_member: int = Field(
        default=10, validation_alias="ACTIVE_DIGEST_SUBSCRIPTION_CAP_PER_MEMBER", ge=1
    )

    # R3.0 automated ingestion (013-automated-ingestion). R1 research left the SES-vs-Mailgun
    # infrastructure choice as a "pending implementation spike" — "stub" keeps the webhook
    # endpoint fully wired and testable (shared-secret verification only) without picking a
    # provider or pulling in a provider SDK before that decision is made, mirroring
    # EXTRACTION_PROVIDER_MODE's own stub/real split.
    ingestion_email_provider: Literal["stub", "mailgun", "ses"] = Field(
        default="stub", validation_alias="INGESTION_EMAIL_PROVIDER"
    )
    ingestion_webhook_shared_secret: SecretStr | None = Field(
        default=None, validation_alias="INGESTION_WEBHOOK_SHARED_SECRET"
    )
    mailgun_signing_key: SecretStr | None = Field(
        default=None, validation_alias="MAILGUN_SIGNING_KEY"
    )
    # R3.0 security review (T042): the HMAC alone proves the payload was signed by Mailgun, not
    # that it is fresh — a captured valid webhook call could otherwise be replayed indefinitely
    # to drain a tenant's daily quota and create unbounded raw-email storage objects. Mailgun's
    # own docs recommend rejecting a timestamp older than a few minutes; 900s (15 min) matches
    # Mailgun's documented retry/delivery window with headroom for normal clock skew.
    mailgun_max_timestamp_skew_seconds: int = Field(
        default=900, validation_alias="MAILGUN_MAX_TIMESTAMP_SKEW_SECONDS", ge=1
    )
    # The base domain tenant forwarding addresses are minted under. Deployment-specific, so it
    # lives here rather than hardcoded into a DB CHECK constraint (see
    # docs/quality — tenant_email_config's address-format constraint validates shape only).
    ingestion_email_domain: str = Field(
        default="ingest.procurepilot.local", validation_alias="INGESTION_EMAIL_DOMAIN"
    )
    ingestion_raw_bucket: str = Field(
        default="ingestion-raw", validation_alias="INGESTION_RAW_BUCKET"
    )
    ingestion_max_attachment_bytes: int = Field(
        default=10_485_760, validation_alias="INGESTION_MAX_ATTACHMENT_BYTES", ge=1
    )
    ingestion_max_email_bytes: int = Field(
        default=52_428_800, validation_alias="INGESTION_MAX_EMAIL_BYTES", ge=1
    )
    email_ingestion_stale_lock_seconds: int = Field(
        default=600, validation_alias="EMAIL_INGESTION_STALE_LOCK_SECONDS", ge=1
    )
    # Wave 3 (T015/T018, research R8).
    capture_max_bytes: int = Field(default=10_485_760, validation_alias="CAPTURE_MAX_BYTES", ge=1)
    catalogue_import_max_bytes: int = Field(
        default=26_214_400, validation_alias="CATALOGUE_IMPORT_MAX_BYTES", ge=1
    )
    rate_limit_capture_upload: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_CAPTURE_UPLOAD"
    )
    rate_limit_catalogue_import: str = Field(
        default="10/minute", validation_alias="RATE_LIMIT_CATALOGUE_IMPORT"
    )

    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, validation_alias="SMTP_USER")
    smtp_password: SecretStr | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_tls: bool = Field(default=True, validation_alias="SMTP_TLS")
    smtp_from: str | None = Field(default=None, validation_alias="SMTP_FROM")

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    matching_auto_accept_threshold: float = Field(
        default=0.9200, validation_alias="MATCHING_AUTO_ACCEPT_THRESHOLD", ge=0, le=1
    )
    matching_auto_reject_threshold: float = Field(
        default=0.2500, validation_alias="MATCHING_AUTO_REJECT_THRESHOLD", ge=0, le=1
    )
    matching_review_margin: float = Field(
        default=0.0500, validation_alias="MATCHING_REVIEW_MARGIN", ge=0, le=1
    )
    matching_trigram_threshold: float = Field(
        default=0.30, validation_alias="MATCHING_TRIGRAM_THRESHOLD", ge=0, le=1
    )
    matching_embedding_model: str = Field(
        default="stub-hash-v1", validation_alias="MATCHING_EMBEDDING_MODEL"
    )

    web_api_base_url: str = Field(validation_alias="WEB_API_BASE_URL")
    web_default_locale: Locale = Field(validation_alias="WEB_DEFAULT_LOCALE")

    sentry_dsn: SecretStr | None = Field(default=None, validation_alias="SENTRY_DSN")
    posthog_api_key: SecretStr | None = Field(default=None, validation_alias="POSTHOG_API_KEY")

    # Accounting integration (R3.1, 014-accounting-integration):
    # Provider mode defaults to "stub" so tests, local development, and CI can run
    # without a real accounting developer account. "quickbooks" and "xero" use
    # provider OAuth2 and read-only REST calls.
    accounting_provider_mode: Literal["stub", "quickbooks", "xero"] = Field(
        default="stub", validation_alias="ACCOUNTING_PROVIDER_MODE"
    )
    quickbooks_client_id: str | None = Field(
        default=None, validation_alias="QUICKBOOKS_CLIENT_ID"
    )
    quickbooks_client_secret: SecretStr | None = Field(
        default=None, validation_alias="QUICKBOOKS_CLIENT_SECRET"
    )
    quickbooks_redirect_uri: str | None = Field(
        default=None, validation_alias="QUICKBOOKS_REDIRECT_URI"
    )
    quickbooks_environment: Literal["sandbox", "production"] = Field(
        default="sandbox", validation_alias="QUICKBOOKS_ENVIRONMENT"
    )
    xero_client_id: str | None = Field(default=None, validation_alias="XERO_CLIENT_ID")
    xero_client_secret: SecretStr | None = Field(
        default=None, validation_alias="XERO_CLIENT_SECRET"
    )
    xero_redirect_uri: str | None = Field(default=None, validation_alias="XERO_REDIRECT_URI")
    xero_environment: Literal["sandbox", "production"] = Field(
        default="sandbox", validation_alias="XERO_ENVIRONMENT"
    )
    # R3.1 security review (T039): access_token/refresh_token were stored as plain `text` with
    # no encryption at rest — research.md R4 named this as an "encrypted-column-at-the-
    # database-layer" requirement, but only the RLS/column-grant restriction (accounting_
    # connection's own migration) was ever built; the encryption half never was. A DB-level
    # compromise (a leaked pg_dump, a stolen service_role credential, disk access) would expose
    # live third-party financial credentials in plaintext. Fernet (authenticated symmetric
    # encryption from `cryptography`, already a transitive dependency via python-jose) is applied
    # at the application layer — not via Postgres's pgcrypto — specifically so the key itself
    # never has to travel over the database connection as a query parameter, where it could end
    # up in query logs or pg_stat_statements. Optional, matching every other QuickBooks setting's
    # own None-by-default shape (stub mode's fake tokens need no real protection); required in
    # any deployment actually running accounting_provider_mode="quickbooks" against live tokens.
    accounting_token_encryption_key: SecretStr | None = Field(
        default=None, validation_alias="ACCOUNTING_TOKEN_ENCRYPTION_KEY"
    )
    # R3.1 security review (T039): router.py had zero rate limiting on either mutation endpoint —
    # every other module's own mutation endpoints follow this same config-driven-limit
    # convention (see rate_limit_capture_upload/rate_limit_catalogue_import above). Sync is the
    # expensive one (a real outbound QuickBooks API call chain, and the advisory lock only stops
    # concurrent syncs, not rapid sequential ones), so its default is conservative like
    # catalogue import's own; resolve is a lightweight mutation, matching the email-config
    # mutations' own default.
    rate_limit_accounting_sync: str = Field(
        default="10/minute", validation_alias="RATE_LIMIT_ACCOUNTING_SYNC"
    )
    rate_limit_accounting_discrepancy_resolve: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_ACCOUNTING_DISCREPANCY_RESOLVE"
    )
    rate_limit_order_mutation: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_ORDER_MUTATION"
    )

    # POS & inventory integration (R3.2, 015-pos-inventory-integration):
    # Provider mode defaults to "stub" so tests, local development, and CI can run
    # without a real Square developer account. "square" uses live OAuth2 and REST calls
    # against Square's Orders and Inventory APIs.
    pos_provider_mode: Literal["stub", "square"] = Field(
        default="stub", validation_alias="POS_PROVIDER_MODE"
    )
    square_application_id: str | None = Field(
        default=None, validation_alias="SQUARE_APPLICATION_ID"
    )
    square_application_secret: SecretStr | None = Field(
        default=None, validation_alias="SQUARE_APPLICATION_SECRET"
    )
    square_redirect_uri: str | None = Field(
        default=None, validation_alias="SQUARE_REDIRECT_URI"
    )
    square_environment: Literal["sandbox", "production"] = Field(
        default="sandbox", validation_alias="SQUARE_ENVIRONMENT"
    )
    pos_token_encryption_key: SecretStr | None = Field(
        default=None, validation_alias="POS_TOKEN_ENCRYPTION_KEY"
    )
    rate_limit_pos_sync: str = Field(
        default="10/minute", validation_alias="RATE_LIMIT_POS_SYNC"
    )
    rate_limit_pos_match: str = Field(
        default="30/minute", validation_alias="RATE_LIMIT_POS_MATCH"
    )
    # A bare POS item name carries none of the deterministic (GTIN), brand, variant, or pack
    # signals that quotation-line matching's score_candidate() formula is weighted around — that
    # formula caps out well below matching_auto_accept_threshold (0.92) even for a perfect name
    # match, since deterministic_signal alone accounts for 30% of the score and is always 0 here.
    # POS matching therefore compares the raw lexical/semantic similarity (the only signals a bare
    # name actually carries) against its own threshold, not the composite quotation score.
    pos_matching_auto_accept_threshold: float = Field(
        default=0.90, validation_alias="POS_MATCHING_AUTO_ACCEPT_THRESHOLD"
    )

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> tuple[str, ...] | object:
        if isinstance(value, str):
            origins = tuple(origin.strip() for origin in value.split(",") if origin.strip())
            if not origins:
                raise ValueError("API_CORS_ORIGINS must contain at least one origin")
            return origins
        return value

    @field_validator(
        "sentry_dsn",
        "posthog_api_key",
        "quickbooks_client_secret",
        "xero_client_secret",
        "accounting_token_encryption_key",
        "square_application_secret",
        "pos_token_encryption_key",
        mode="before",
    )
    @classmethod
    def empty_secret_to_none(cls, value: object) -> object | None:
        if value == "":
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
