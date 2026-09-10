import hmac
import json
import logging
import time
import uuid

import jwt

from config import AUTH

logger = logging.getLogger(__name__)

REFRESH_TOKEN_REDIS_PREFIX = "refresh_token:"


def _load_client_credentials() -> dict:
    try:
        return json.loads(AUTH.client_credentials_json or "{}")
    except json.JSONDecodeError:
        logger.error("CLIENT_CREDENTIALS_JSON is not valid JSON — no JWT clients configured")
        return {}


def authenticate_client(client_id: str, client_secret: str) -> dict | None:
    """Returns the client's config dict ({"secret":..., "state":...}) if credentials match."""
    creds = _load_client_credentials()
    entry = creds.get(client_id)
    # Constant-time comparison: these secrets belong to state education
    # departments and gate access to a whole state's student data, so a
    # timing side-channel on `==` (which short-circuits on the first
    # mismatched byte) is a real risk here, not a theoretical one.
    if entry and hmac.compare_digest(entry.get("secret", ""), client_secret):
        return entry
    return None


def issue_access_token(client_id: str, state: str | None) -> str:
    now = int(time.time())
    payload = {
        "sub": client_id,
        "state": state,  # None => unrestricted (admin-equivalent client)
        "type": "access",
        "iat": now,
        "exp": now + AUTH.jwt_expiry_minutes * 60,
    }
    return jwt.encode(payload, AUTH.jwt_secret, algorithm="HS256")


def build_refresh_token(client_id: str, state: str | None) -> tuple[str, str, int]:
    """Returns (token, jti, ttl_seconds). Caller is responsible for storing
    `jti` in Redis with the given TTL — kept out of this module so jwt_auth
    stays free of an infra dependency and easy to unit test."""
    now = int(time.time())
    jti = str(uuid.uuid4())
    ttl_seconds = AUTH.refresh_token_expiry_days * 86400
    payload = {
        "sub": client_id,
        "state": state,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    token = jwt.encode(payload, AUTH.jwt_secret, algorithm="HS256")
    return token, jti, ttl_seconds


def decode_token(token: str, expected_type: str | None = None) -> dict | None:
    """Returns the decoded payload, or None if invalid/expired/wrong type."""
    try:
        payload = jwt.decode(token, AUTH.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        logger.info("JWT rejected: %s", e)
        return None

    if expected_type and payload.get("type") != expected_type:
        logger.info("JWT type mismatch: expected %s, got %s", expected_type, payload.get("type"))
        return None
    return payload
