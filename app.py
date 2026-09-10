import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from functools import partial

import joblib
from sanic import Sanic, Blueprint, response
from sanic.request import Request
from sanic.response import json as json_response

from config import REDIS, WHATSAPP, AUTH, NOTIFY
from cache.redis_client import RedisCache
from db_connectors.postgres_client import PostgresClient
from db_connectors.mongo_client import MongoDataStore
from genai.rag_pipeline import AzureOpenAIProvider, RAGIndexer
from genai.language_utils import LanguageDetector
from integrations.whatsapp_client import WhatsAppClient
from ml.dropout_risk_model import score_students, explain_prediction
from ml import model_registry
from auth import jwt_auth
from tracing.otel_setup import get_tracer
from pydantic import ValidationError
from schemas import TokenRequest, RefreshRequest, AskRequest, AskFeedbackRequest, StudentsAtRiskQuery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("edtech-india-api")
tracer = get_tracer()

app = Sanic("EdTechIndiaAPI")
app.config.RESPONSE_TIMEOUT = 120
v1 = Blueprint("v1", url_prefix="/v1")

API_KEY = os.getenv("API_KEY")  # Key Vault-backed secret; treated as an admin/all-states key

METRICS = {"requests_total": 0, "errors_total": 0, "latency_sum_ms": 0.0, "cache_hits": 0}


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------
@app.before_server_start
async def setup(app_ctx, _):
    logger.info("Starting up: connecting to Postgres/Mongo/Redis, loading model")
    app_ctx.ctx.pg_client = PostgresClient()
    app_ctx.ctx.mongo_store = MongoDataStore()
    app_ctx.ctx.rag_engine = RAGIndexer(AzureOpenAIProvider(), app_ctx.ctx.mongo_store, app_ctx.ctx.pg_client)
    app_ctx.ctx.redis = RedisCache(REDIS.url)
    app_ctx.ctx.language_detector = LanguageDetector()
    app_ctx.ctx.whatsapp_client = WhatsAppClient()

    try:
        app_ctx.ctx.dropout_model = joblib.load("dropout_model.joblib")
    except FileNotFoundError:
        app_ctx.ctx.dropout_model = None
        logger.warning("dropout_model.joblib not found — /v1/students/at-risk will 503 until trained")


@app.after_server_stop
async def teardown(app_ctx, _):
    logger.info("Shutting down connections")
    app_ctx.ctx.pg_client.engine.dispose()
    app_ctx.ctx.mongo_store.client.close()
    await app_ctx.ctx.redis.close()


# --------------------------------------------------------------------------
# Middleware: auth (API key OR scoped JWT) + tiered rate limiting + metrics/logging
# --------------------------------------------------------------------------
UNAUTHENTICATED_PATHS = ("/health", "/webhook/whatsapp", "/v1/auth/token", "/v1/auth/refresh")

# Per-endpoint rate-limit tiers: a client hammering the expensive LLM-backed
# /v1/ask endpoint shouldn't also burn through the allowance for cheap
# /v1/students reads, and the unauthenticated auth endpoints need their own
# tight cap to slow down credential brute-forcing.
RATE_LIMIT_TIERS = {
    "/v1/ask": ("ask", 20),
    "/v1/auth": ("auth", 10),
}
DEFAULT_TIER = ("default", REDIS.rate_limit_per_minute)


def _tier_for_path(path: str) -> tuple[str, int]:
    for prefix, tier in RATE_LIMIT_TIERS.items():
        if path.startswith(prefix):
            return tier
    return DEFAULT_TIER


@app.on_request
async def authenticate_rate_limit_and_time(request: Request):
    request.ctx.start_time = time.time()
    request.ctx.state_scope = None  # None = unrestricted (admin key or no auth configured)

    if request.path == "/health":
        return

    if request.path.startswith("/webhook/whatsapp"):
        return  # verified separately via HMAC signature, not our own auth scheme

    tier_name, tier_limit = _tier_for_path(request.path)

    if request.path.startswith(UNAUTHENTICATED_PATHS):
        # No identity yet (that's what this endpoint issues) — rate limit by
        # IP instead, so brute-forcing client_secret guesses is still capped.
        limited = await request.app.ctx.redis.is_rate_limited(
            request.ip, limit=tier_limit, window_seconds=60, tier=tier_name
        )
        if limited:
            METRICS["errors_total"] += 1
            return json_response({"error": "rate limit exceeded, try again shortly"}, status=429)
        return

    supplied_key = request.headers.get("x-api-key")
    auth_header = request.headers.get("authorization", "")

    if API_KEY and supplied_key == API_KEY:
        identity = supplied_key  # admin key: no state restriction
    elif auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        claims = jwt_auth.decode_token(token, expected_type="access")
        if claims is None:
            METRICS["errors_total"] += 1
            return json_response({"error": "invalid or expired access token"}, status=401)
        request.ctx.state_scope = claims.get("state")  # row-level isolation applied downstream
        identity = claims["sub"]
    else:
        METRICS["errors_total"] += 1
        return json_response({"error": "unauthorized — supply X-API-Key or Authorization: Bearer <token>"}, status=401)

    limited = await request.app.ctx.redis.is_rate_limited(
        identity, limit=tier_limit, window_seconds=60, tier=tier_name
    )
    if limited:
        METRICS["errors_total"] += 1
        return json_response({"error": "rate limit exceeded, try again shortly"}, status=429)


@app.on_response
async def log_and_count(request: Request, resp):
    duration_ms = (time.time() - getattr(request.ctx, "start_time", time.time())) * 1000
    METRICS["requests_total"] += 1
    METRICS["latency_sum_ms"] += duration_ms
    if resp.status >= 400:
        METRICS["errors_total"] += 1

    logger.info(json.dumps({
        "path": request.path, "method": request.method,
        "status": resp.status, "duration_ms": round(duration_ms, 2),
    }))


# --------------------------------------------------------------------------
# Infra routes (unversioned)
# --------------------------------------------------------------------------
@app.get("/health")
async def health(request: Request):
    loop = asyncio.get_event_loop()
    pg_ok, redis_ok = True, True

    try:
        await loop.run_in_executor(None, partial(request.app.ctx.pg_client.query, "SELECT 1"))
    except Exception as e:  # noqa: BLE001 - health check must never raise
        logger.error("Postgres health check failed: %s", e)
        pg_ok = False

    try:
        await request.app.ctx.redis.client.ping()
    except Exception as e:  # noqa: BLE001
        logger.error("Redis health check failed: %s", e)
        redis_ok = False

    status = "ok" if (pg_ok and redis_ok) else "degraded"
    return json_response({"status": status, "postgres": pg_ok, "redis": redis_ok})


@app.get("/metrics")
async def metrics(request: Request):
    avg_latency = (
        METRICS["latency_sum_ms"] / METRICS["requests_total"] if METRICS["requests_total"] else 0
    )
    return json_response({
        "requests_total": METRICS["requests_total"],
        "errors_total": METRICS["errors_total"],
        "cache_hits": METRICS["cache_hits"],
        "avg_latency_ms": round(avg_latency, 2),
    })


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
@v1.post("/auth/token")
async def issue_token(request: Request):
    try:
        body = TokenRequest.model_validate(request.json or {})
    except ValidationError as e:
        return json_response({"error": "invalid request", "details": e.errors()}, status=400)

    entry = jwt_auth.authenticate_client(body.client_id, body.client_secret)
    if entry is None:
        return json_response({"error": "invalid client credentials"}, status=401)

    state = entry.get("state")
    access_token = jwt_auth.issue_access_token(body.client_id, state=state)
    refresh_token, jti, ttl = jwt_auth.build_refresh_token(body.client_id, state=state)
    await request.app.ctx.redis.store_refresh_jti(jti, body.client_id, ttl_seconds=ttl)

    return json_response({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in_minutes": AUTH.jwt_expiry_minutes,
        "refresh_expires_in_days": AUTH.refresh_token_expiry_days,
        "state_scope": state,
    })


@v1.post("/auth/refresh")
async def refresh_token_endpoint(request: Request):
    """
    Exchanges a still-valid refresh token for a new access token, and
    rotates the refresh token itself (old one is revoked, a new one is
    issued). Rotation means a leaked-and-reused refresh token fails the
    second time it's used — whichever party uses it first "wins" and the
    other is locked out, which is the signal that the token was compromised.
    """
    try:
        body = RefreshRequest.model_validate(request.json or {})
    except ValidationError as e:
        return json_response({"error": "invalid request", "details": e.errors()}, status=400)

    claims = jwt_auth.decode_token(body.refresh_token, expected_type="refresh")
    if claims is None:
        return json_response({"error": "invalid or expired refresh token"}, status=401)

    jti = claims.get("jti")
    owner = await request.app.ctx.redis.get_refresh_jti_owner(jti)
    if owner is None or owner != claims["sub"]:
        return json_response({"error": "refresh token has been revoked or already used"}, status=401)

    # Rotate: revoke the used token, issue a fresh pair.
    await request.app.ctx.redis.revoke_refresh_jti(jti)

    state = claims.get("state")
    client_id = claims["sub"]
    new_access_token = jwt_auth.issue_access_token(client_id, state=state)
    new_refresh_token, new_jti, ttl = jwt_auth.build_refresh_token(client_id, state=state)
    await request.app.ctx.redis.store_refresh_jti(new_jti, client_id, ttl_seconds=ttl)

    return json_response({
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "Bearer",
        "expires_in_minutes": AUTH.jwt_expiry_minutes,
        "refresh_expires_in_days": AUTH.refresh_token_expiry_days,
        "state_scope": state,
    })


# --------------------------------------------------------------------------
# Students / risk scoring
# --------------------------------------------------------------------------
@v1.get("/students/at-risk")
async def students_at_risk(request: Request):
    with tracer.start_as_current_span("students_at_risk"):
        try:
            query = StudentsAtRiskQuery.model_validate({"limit": request.args.get("limit", 10)})
        except ValidationError as e:
            return json_response({"error": "invalid request", "details": e.errors()}, status=400)

        ctx = request.app.ctx
        limit = query.limit
        state = request.ctx.state_scope  # None for admin key, else the JWT client's state

        cache_key = ctx.redis.make_key("students-at-risk", limit, state or "all")
        cached = await ctx.redis.get_json(cache_key)
        if cached is not None:
            METRICS["cache_hits"] += 1
            return json_response(cached)

        loop = asyncio.get_event_loop()

        # Fast path: read precomputed scores from the nightly batch job.
        precomputed = await loop.run_in_executor(
            None, partial(ctx.pg_client.get_precomputed_risk_scores, limit=limit, state=state)
        )
        if not precomputed.empty:
            result = precomputed.to_dict(orient="records")
        else:
            # Fallback: no batch run yet — score live (slower, matches the original behavior).
            if ctx.dropout_model is None:
                return json_response({"error": "Model not trained yet. Run ml/dropout_risk_model.py first."}, status=503)
            dataset = await loop.run_in_executor(None, partial(ctx.pg_client.get_training_dataset, state=state))
            ranked = await loop.run_in_executor(None, score_students, ctx.dropout_model, dataset)
            cols = ["student_id", "dropout_risk_score", "attendance_pct", "avg_test_score", "state", "district"]
            result = ranked[cols].head(limit).to_dict(orient="records")

        await ctx.redis.set_json(cache_key, result, ttl_seconds=REDIS.cache_ttl_seconds)
        return json_response(result)


@v1.get("/students/<student_id:int>/explain")
async def student_explain(request: Request, student_id: int):
    ctx = request.app.ctx
    if ctx.dropout_model is None:
        return json_response({"error": "Model not trained yet."}, status=503)

    loop = asyncio.get_event_loop()
    row = await loop.run_in_executor(None, ctx.pg_client.get_student_by_id, student_id)
    if row.empty:
        return json_response({"error": "student not found"}, status=404)

    if request.ctx.state_scope and row.iloc[0]["state"] != request.ctx.state_scope:
        return json_response({"error": "not found"}, status=404)  # don't leak cross-state existence

    contributions = await loop.run_in_executor(None, explain_prediction, ctx.dropout_model, row)
    return json_response({"student_id": student_id, "risk_contributions": contributions})


@v1.delete("/students/<student_id:int>")
async def student_delete(request: Request, student_id: int):
    """Right-to-deletion: removes the student's record and any cached risk score.

    Also purges the students-at-risk cache namespace, not just the Postgres
    row — otherwise a cached /students/at-risk page (up to REDIS_CACHE_TTL
    seconds old) could keep serving this student's data after "deletion"."""
    ctx = request.app.ctx
    loop = asyncio.get_event_loop()

    row = await loop.run_in_executor(None, ctx.pg_client.get_student_by_id, student_id)
    if row.empty:
        return json_response({"error": "student not found"}, status=404)
    if request.ctx.state_scope and row.iloc[0]["state"] != request.ctx.state_scope:
        return json_response({"error": "not found"}, status=404)

    deleted = await loop.run_in_executor(None, ctx.pg_client.delete_student, student_id)
    await ctx.redis.invalidate_namespace("students-at-risk")
    return json_response({"deleted": deleted > 0})


# --------------------------------------------------------------------------
# Aggregated risk summaries
# --------------------------------------------------------------------------
@v1.get("/schools/<school_id:int>/risk-summary")
async def school_risk_summary(request: Request, school_id: int):
    ctx = request.app.ctx
    loop = asyncio.get_event_loop()
    summary = await loop.run_in_executor(None, ctx.pg_client.school_risk_summary, school_id)
    if summary.empty:
        return json_response({"error": "school not found"}, status=404)
    row = summary.iloc[0]
    if request.ctx.state_scope and row["state"] != request.ctx.state_scope:
        return json_response({"error": "not found"}, status=404)
    return json_response(row.where(row.notnull(), None).to_dict())


@v1.get("/districts/<state>/<district>/risk-summary")
async def district_risk_summary(request: Request, state: str, district: str):
    if request.ctx.state_scope and state != request.ctx.state_scope:
        return json_response({"error": "not found"}, status=404)
    loop = asyncio.get_event_loop()
    summary = await loop.run_in_executor(None, request.app.ctx.pg_client.district_risk_summary, state, district)
    if summary.empty:
        return json_response({"error": "no data for this state/district"}, status=404)
    row = summary.iloc[0]
    return json_response(row.where(row.notnull(), None).to_dict())


# --------------------------------------------------------------------------
# Governance: anonymized export
# --------------------------------------------------------------------------
@v1.get("/export/anonymized")
async def export_anonymized(request: Request):
    state = request.args.get("state") or request.ctx.state_scope
    if request.ctx.state_scope and state != request.ctx.state_scope:
        return json_response({"error": "cannot export outside your assigned state"}, status=403)

    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, partial(request.app.ctx.pg_client.get_anonymized_export, state=state))
    return json_response(df.to_dict(orient="records"))


# --------------------------------------------------------------------------
# Model registry: version history + rollback (admin key only — rolling back
# the live model is an operational action, not something a state-scoped
# client should be able to trigger).
# --------------------------------------------------------------------------
@v1.get("/models/versions")
async def model_versions(request: Request):
    loop = asyncio.get_event_loop()
    versions = await loop.run_in_executor(None, model_registry.list_versions)
    return json_response(versions)


@v1.post("/models/rollback")
async def model_rollback(request: Request):
    if request.ctx.state_scope is not None:
        # A state-scoped JWT client is never allowed to change the live
        # model for everyone — only the admin API key can.
        return json_response({"error": "rollback requires the admin API key"}, status=403)

    body = request.json or {}
    version = body.get("version")
    if not version:
        return json_response({"error": "'version' is required"}, status=400)

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, model_registry.rollback_to, version)
    if not success:
        return json_response({"error": f"version '{version}' not found"}, status=404)

    # The now-stale in-memory model must be reloaded for this to take effect
    # without a full pod restart.
    request.app.ctx.dropout_model = await loop.run_in_executor(
        None, joblib.load, model_registry.CURRENT_MODEL_PATH
    )
    return json_response({"status": "rolled back", "version": version})


# --------------------------------------------------------------------------
# RAG Q&A
# --------------------------------------------------------------------------
@v1.post("/ask")
async def ask(request: Request):
    with tracer.start_as_current_span("ask"):
        ctx = request.app.ctx
        try:
            body = AskRequest.model_validate(request.json or {})
        except ValidationError as e:
            return json_response({"error": "invalid request", "details": e.errors()}, status=400)

        question, top_k = body.question, body.top_k
        loop = asyncio.get_event_loop()

        language_code = body.language
        if not language_code:
            language_code = await loop.run_in_executor(None, ctx.language_detector.detect, question)
        language_name = ctx.language_detector.language_name(language_code)

        cache_key = ctx.redis.make_key("ask", question.strip().lower(), top_k, language_code)
        cached = await ctx.redis.get_json(cache_key)
        if cached is not None:
            METRICS["cache_hits"] += 1
            return json_response(cached)

        try:
            answer = await loop.run_in_executor(
                None, partial(ctx.rag_engine.query, question, top_k=top_k,
                              language_name=language_name, language_code=language_code)
            )
        except RuntimeError as e:
            return json_response({"error": str(e)}, status=503)

        result = {"question": question, "answer": answer, "language": language_code}
        await ctx.redis.set_json(cache_key, result, ttl_seconds=REDIS.cache_ttl_seconds)
        return json_response(result)


@v1.post("/ask/feedback")
async def ask_feedback(request: Request):
    """Thumbs up/down (+ optional comment) on a RAG answer, logged for later review
    of which policy questions get poor answers."""
    try:
        body = AskFeedbackRequest.model_validate(request.json or {})
    except ValidationError as e:
        return json_response({"error": "invalid request", "details": e.errors()}, status=400)

    request.app.ctx.mongo_store.db["rag_feedback"].insert_one({
        "question": body.question, "answer": body.answer, "rating": body.rating, "comment": body.comment,
    })
    return json_response({"status": "recorded"})


@v1.websocket("/ask/stream")
async def ask_stream(request: Request, ws):
    """WebSocket variant: client sends {"question": "..."}, server streams the answer in chunks."""
    loop = asyncio.get_event_loop()
    async for raw_message in ws:
        try:
            payload = json.loads(raw_message)
            question = payload["question"]
        except (json.JSONDecodeError, KeyError):
            await ws.send(json.dumps({"error": "send {'question': '...'}"}))
            continue

        try:
            answer = await loop.run_in_executor(None, request.app.ctx.rag_engine.query, question, 3)
        except RuntimeError as e:
            await ws.send(json.dumps({"error": str(e)}))
            continue

        chunk_size = 40
        for i in range(0, len(answer), chunk_size):
            await ws.send(json.dumps({"delta": answer[i:i + chunk_size]}))
            await asyncio.sleep(0.02)
        await ws.send(json.dumps({"done": True}))


app.blueprint(v1)


# --------------------------------------------------------------------------
# WhatsApp bot: same RAG pipeline, reached over WhatsApp instead of a web/app UI.
# --------------------------------------------------------------------------
def _verify_whatsapp_signature(request: Request) -> bool:
    """Validates Meta's X-Hub-Signature-256 header (HMAC-SHA256 of the raw
    body, keyed with the Meta App secret) so only genuine Meta requests are
    processed.

    Fails CLOSED if WHATSAPP_APP_SECRET isn't set: an unsigned request is
    rejected. The old behavior returned True (accepted the request) in that
    case, which meant a missing env var in production silently turned into
    "anyone can POST arbitrary messages into the LLM pipeline as if from
    Meta." The only way to skip verification now is the explicit
    ALLOW_UNSIGNED_WEBHOOK=true dev flag, which defaults to off everywhere."""
    if not WHATSAPP.app_secret:
        if WHATSAPP.allow_unsigned_webhook:
            logger.warning(
                "WHATSAPP_APP_SECRET not set — skipping signature verification "
                "because ALLOW_UNSIGNED_WEBHOOK=true (dev only, never set this in prod)"
            )
            return True
        logger.error(
            "WHATSAPP_APP_SECRET not set — rejecting webhook request. "
            "Set WHATSAPP_APP_SECRET, or ALLOW_UNSIGNED_WEBHOOK=true for local dev only."
        )
        return False

    signature_header = request.headers.get("x-hub-signature-256", "")
    if not signature_header.startswith("sha256="):
        return False
    provided_sig = signature_header.removeprefix("sha256=")

    expected_sig = hmac.new(
        WHATSAPP.app_secret.encode(), request.body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP.verify_token:
        return response.text(challenge or "")
    return json_response({"error": "verification failed"}, status=403)


@app.post("/webhook/whatsapp")
async def whatsapp_incoming(request: Request):
    if not _verify_whatsapp_signature(request):
        logger.warning("Rejected WhatsApp webhook call with invalid signature")
        return json_response({"error": "invalid signature"}, status=403)

    ctx = request.app.ctx
    parsed = ctx.whatsapp_client.parse_incoming(request.json or {})
    if parsed is None:
        return json_response({"status": "ignored"})  # status callback or non-text message

    question = parsed["text"]
    sender = parsed["from"]
    loop = asyncio.get_event_loop()

    language_code = await loop.run_in_executor(None, ctx.language_detector.detect, question)
    language_name = ctx.language_detector.language_name(language_code)

    try:
        answer = await loop.run_in_executor(
            None, partial(ctx.rag_engine.query, question, top_k=3,
                          language_name=language_name, language_code=language_code)
        )
    except RuntimeError:
        answer = ("Sorry, I don't have any policy documents indexed yet — "
                  "please try again later.")

    await ctx.whatsapp_client.send_text(sender, answer)
    return json_response({"status": "replied"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, workers=int(os.getenv("SANIC_WORKERS", 2)))
