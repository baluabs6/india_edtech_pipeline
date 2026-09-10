"""
conftest.py
Sets safe, non-production env vars BEFORE any test module imports `config`
(directly, or transitively via e.g. genai.rag_pipeline -> config.AZURE).

config.py's fail-fast startup check (see _fail_fast_on_insecure_config)
refuses to import in ENVIRONMENT=production without a real JWT_SECRET /
EXPORT_HASH_SECRET. Tests should exercise that check too where relevant
(none currently do), but shouldn't be blocked by it just for importing
unrelated modules — so we set ENVIRONMENT=development here, plus secrets
long enough to also satisfy the production-strength check, belt-and-suspenders.

conftest.py is collected by pytest before test files in the same directory,
so these env vars are in place before test_auth_and_ratelimit.py's own
os.environ.setdefault(...) calls run — setdefault() there is then a no-op
for keys we've already set, which is fine, they agree.
"""
import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-key-not-for-production-use-only-32ch")
os.environ.setdefault("EXPORT_HASH_SECRET", "test-export-hash-secret-not-for-production-32ch")
os.environ.setdefault("CLIENT_CREDENTIALS_JSON", '{"bihar-dept": {"secret": "pw123", "state": "Bihar"}}')
