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
    # Business-rule caps (distinct from the request-rate limits above): each recurring schedule
    # or subscription is itself a standing worker cost, so the count of *active* rows per member
    # is capped independently of how fast they were created.
    active_schedule_cap_per_member: int = Field(
        default=20, validation_alias="ACTIVE_SCHEDULE_CAP_PER_MEMBER", ge=1
    )
    active_digest_subscription_cap_per_member: int = Field(
        default=10, validation_alias="ACTIVE_DIGEST_SUBSCRIPTION_CAP_PER_MEMBER", ge=1
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
    # without a real Intuit/QuickBooks developer account. "quickbooks" uses live
    # OAuth2 and REST calls against QuickBooks Online.
    accounting_provider_mode: Literal["stub", "quickbooks"] = Field(
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

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> tuple[str, ...] | object:
        if isinstance(value, str):
            origins = tuple(origin.strip() for origin in value.split(",") if origin.strip())
            if not origins:
                raise ValueError("API_CORS_ORIGINS must contain at least one origin")
            return origins
        return value

    @field_validator("sentry_dsn", "posthog_api_key", "quickbooks_client_secret", mode="before")
    @classmethod
    def empty_secret_to_none(cls, value: object) -> object | None:
        if value == "":
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
