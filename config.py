"""
config.py
Centralized configuration. All secrets are pulled from environment variables
(.env locally, Azure Key Vault / AKS secrets in production) — never hardcoded.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class PostgresConfig:
    host: str = os.getenv("PG_HOST", "localhost")
    port: int = int(os.getenv("PG_PORT", 5432))
    db: str = os.getenv("PG_DB", "edtech_india")
    user: str = os.getenv("PG_USER", "postgres")
    password: str = os.getenv("PG_PASSWORD", "postgres")

    @property
    def uri(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class MongoConfig:
    uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db: str = os.getenv("MONGO_DB", "edtech_unstructured")


@dataclass(frozen=True)
class AzureConfig:
    storage_conn_str: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    openai_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    embedding_deployment: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    language_endpoint: str = os.getenv("AZURE_LANGUAGE_ENDPOINT", "")
    language_key: str = os.getenv("AZURE_LANGUAGE_KEY", "")


@dataclass(frozen=True)
class WhatsAppConfig:
    verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    graph_api_version: str = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v20.0")
    app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")  # for X-Hub-Signature-256 verification


@dataclass(frozen=True)
class RedisConfig:
    url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cache_ttl_seconds: int = int(os.getenv("REDIS_CACHE_TTL", 300))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", 60))


@dataclass(frozen=True)
class AuthConfig:
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expiry_minutes: int = int(os.getenv("JWT_EXPIRY_MINUTES", 60))
    refresh_token_expiry_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRY_DAYS", 30))
    # JSON string: {"client_id": {"secret": "...", "state": "Bihar"}, ...}
    # "state": null/absent means the client can see all states (admin-level client).
    client_credentials_json: str = os.getenv("CLIENT_CREDENTIALS_JSON", "{}")


@dataclass(frozen=True)
class NotificationConfig:
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", 587))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    from_email: str = os.getenv("ALERT_FROM_EMAIL", "")
    to_emails: str = os.getenv("ALERT_TO_EMAILS", "")  # comma-separated
    high_risk_threshold: float = float(os.getenv("HIGH_RISK_THRESHOLD", 0.7))


@dataclass(frozen=True)
class TracingConfig:
    enabled: bool = os.getenv("OTEL_ENABLED", "false").lower() == "true"
    otlp_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    service_name: str = os.getenv("OTEL_SERVICE_NAME", "edtech-india-api")


PG = PostgresConfig()
MONGO = MongoConfig()
AZURE = AzureConfig()
REDIS = RedisConfig()
WHATSAPP = WhatsAppConfig()
AUTH = AuthConfig()
NOTIFY = NotificationConfig()
TRACING = TracingConfig()
