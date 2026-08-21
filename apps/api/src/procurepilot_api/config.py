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
    extraction_provider_mode: Literal["stub", "bedrock", "azure_di"] = Field(
        default="stub", validation_alias="EXTRACTION_PROVIDER_MODE"
    )
    extraction_confidence_threshold: float = Field(
        default=0.85, validation_alias="EXTRACTION_CONFIDENCE_THRESHOLD", ge=0, le=1
    )
    quotation_documents_bucket: str = Field(
        default="quotation-documents", validation_alias="QUOTATION_DOCUMENTS_BUCKET"
    )
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

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> tuple[str, ...] | object:
        if isinstance(value, str):
            origins = tuple(origin.strip() for origin in value.split(",") if origin.strip())
            if not origins:
                raise ValueError("API_CORS_ORIGINS must contain at least one origin")
            return origins
        return value

    @field_validator("sentry_dsn", "posthog_api_key", mode="before")
    @classmethod
    def empty_secret_to_none(cls, value: object) -> object | None:
        if value == "":
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
