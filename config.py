import os
import sys
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "*********n").lower()
IS_PRODUCTION = ENVIRONMENT == "production"


@dataclass(frozen=True)
class PostgresConfig:
    host: str = os.getenv("PG_HOST", "********t")
    port: int = int(os.getenv("PG_PORT", ***2))
    db: str = os.getenv("PG_DB", "***********a")
    user: str = os.getenv("PG_USER", "*******s")
    password: str = os.getenv("PG_PASSWORD", "*******s")

    @property
    def uri(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class MongoConfig:
    uri: str = os.getenv("MONGO_URI", "************************7")
    db: str = os.getenv("MONGO_DB", "******************d")


@dataclass(frozen=True)
class AzureConfig:
    storage_conn_str: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    openai_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "**********i")
    embedding_deployment: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "*********************l")
    language_endpoint: str = os.getenv("AZURE_LANGUAGE_ENDPOINT", "")
    language_key: str = os.getenv("AZURE_LANGUAGE_KEY", "")


@dataclass(frozen=True)
class WhatsAppConfig:
    verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    graph_api_version: str = os.getenv("WHATSAPP_GRAPH_API_VERSION", "****0")
    app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")  # for X-Hub-Signature-256 verification
    # Explicit, opt-in-only escape hatch for local/dev boxes that don't have
    # a Meta app secret configured. Defaults to False everywhere, including
    # development, so it has to be turned on deliberately, never inherited
    # silently — the old behavior was "no secret set -> skip verification",
    # which fails OPEN in production if the secret is ever missing.
    allow_unsigned_webhook: bool = os.getenv("ALLOW_UNSIGNED_WEBHOOK", "****e").lower() == "true"


@dataclass(frozen=True)
class RedisConfig:
    url: str = os.getenv("REDIS_URL", "***********************0")
    cache_ttl_seconds: int = int(os.getenv("REDIS_CACHE_TTL", **0))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", *0))


@dataclass(frozen=True)
class AuthConfig:
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expiry_minutes: int = int(os.getenv("JWT_EXPIRY_MINUTES", *0))
    refresh_token_expiry_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRY_DAYS", *0))
    # JSON string: {"client_id": {"secret": "...", "state": "Bihar"}, ...}
    # "state": null/absent means the client can see all states (admin-level client).
    client_credentials_json: str = os.getenv("CLIENT_CREDENTIALS_JSON", "*}")
    # HMAC key used to pseudonymize student_id in /v1/export/anonymized.
    # Deliberately separate from jwt_secret so rotating one never silently
    # rotates (and re-identifies past exports under) the other.
    export_hash_secret: str = os.getenv("EXPORT_HASH_SECRET", "")


@dataclass(frozen=True)
class NotificationConfig:
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", **7))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    from_email: str = os.getenv("ALERT_FROM_EMAIL", "")
    to_emails: str = os.getenv("ALERT_TO_EMAILS", "")  # comma-separated
    high_risk_threshold: float = float(os.getenv("HIGH_RISK_THRESHOLD", **7))


@dataclass(frozen=True)
class TracingConfig:
    enabled: bool = os.getenv("OTEL_ENABLED", "****e").lower() == "true"
    otlp_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    service_name: str = os.getenv("OTEL_SERVICE_NAME", "***************i")


PG = PostgresConfig()
MONGO = MongoConfig()
AZURE = AzureConfig()
REDIS = RedisConfig()
WHATSAPP = WhatsAppConfig()
AUTH = AuthConfig()
NOTIFY = NotificationConfig()
TRACING = TracingConfig()


def _fail_fast_on_insecure_config() -> None:
    """
    Refuses to start rather than run with a secret that can be forged or
    guessed. Every one of these previously had a default that let the app
    boot "successfully" while actually being wide open — that's worse than
    crashing at startup, because a crash gets noticed immediately and a
    silent insecure default doesn't.

    Skippable only via ENVIRONMENT=development, and even then each skip is
    logged loudly so it's never mistaken for "fully configured".
    """
    problems = []

    if not AUTH.jwt_secret or len(AUTH.jwt_secret) < 32:
        problems.append(
            "JWT_SECRET is unset or too short (< 32 chars). An empty/weak "
            "secret means JWTs can be forged, including admin-equivalent "
            "(all-states) tokens."
        )
    if not AUTH.export_hash_secret or len(AUTH.export_hash_secret) < 32:
        problems.append(
            "EXPORT_HASH_SECRET is unset or too short (< 32 chars). Without "
            "a real secret, the 'anonymized' export's student_id hashes are "
            "reversible by brute force over the small sequential ID space."
        )
    if PG.password in ("", "*******s") and PG.host not in ("********t", "********1"):
        problems.append(
            "PG_PASSWORD is unset/default while PG_HOST points at a non-local "
            "host — refusing to connect a real database with a default password."
        )

    if not problems:
        return

    message = "Insecure configuration detected:\n" + "\n".join(f"  - {p}" for p in problems)

    if IS_PRODUCTION:
        raise RuntimeError(
            message + "\n\nRefusing to start. Set these via Key Vault/AKS secrets, "
            "or set ENVIRONMENT=development for local work with relaxed checks."
        )
    else:
        print(f"WARNING (ENVIRONMENT={ENVIRONMENT}, checks relaxed):\n{message}", file=sys.stderr)


_fail_fast_on_insecure_config()
