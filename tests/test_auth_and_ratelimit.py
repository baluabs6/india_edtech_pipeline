import os
import sys

os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("CLIENT_CREDENTIALS_JSON", '{"bihar-dept": {"secret": "pw123", "state": "Bihar"}}')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from auth import jwt_auth  # noqa: E402


def test_authenticate_client_accepts_correct_secret():
    entry = jwt_auth.authenticate_client("bihar-dept", "pw123")
    assert entry == {"secret": "pw123", "state": "Bihar"}


def test_authenticate_client_rejects_wrong_secret():
    assert jwt_auth.authenticate_client("bihar-dept", "wrong") is None


def test_authenticate_client_rejects_unknown_client():
    assert jwt_auth.authenticate_client("nonexistent", "anything") is None


def test_access_token_round_trip():
    token = jwt_auth.issue_access_token("bihar-dept", state="Bihar")
    claims = jwt_auth.decode_token(token, expected_type="access")
    assert claims["sub"] == "bihar-dept"
    assert claims["state"] == "Bihar"
    assert claims["type"] == "access"


def test_refresh_token_round_trip_and_ttl():
    token, jti, ttl = jwt_auth.build_refresh_token("bihar-dept", state="Bihar")
    claims = jwt_auth.decode_token(token, expected_type="refresh")
    assert claims["jti"] == jti
    assert ttl == 30 * 86400  # default REFRESH_TOKEN_EXPIRY_DAYS


def test_refresh_token_rejected_when_access_expected():
    token, _, _ = jwt_auth.build_refresh_token("bihar-dept", state="Bihar")
    assert jwt_auth.decode_token(token, expected_type="access") is None


def test_tampered_token_rejected():
    token = jwt_auth.issue_access_token("bihar-dept", state="Bihar")
    tampered = token[:-2] + "xx"
    assert jwt_auth.decode_token(tampered) is None


def test_rate_limit_tier_selection():
    # Mirrors the lookup logic in app.py without importing the full Sanic app
    # (which needs live DB/Redis/Azure clients at import time).
    RATE_LIMIT_TIERS = {"/v1/ask": ("ask", 20), "/v1/auth": ("auth", 10)}
    DEFAULT_TIER = ("default", 60)

    def tier_for_path(path):
        for prefix, tier in RATE_LIMIT_TIERS.items():
            if path.startswith(prefix):
                return tier
        return DEFAULT_TIER

    assert tier_for_path("/v1/ask") == ("ask", 20)
    assert tier_for_path("/v1/ask/feedback") == ("ask", 20)
    assert tier_for_path("/v1/auth/token") == ("auth", 10)
    assert tier_for_path("/v1/students/at-risk") == ("default", 60)
