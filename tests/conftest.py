import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-key-not-for-production-use-only-32ch")
os.environ.setdefault("EXPORT_HASH_SECRET", "test-export-hash-secret-not-for-production-32ch")
os.environ.setdefault("CLIENT_CREDENTIALS_JSON", '{"bihar-dept": {"secret": "pw123", "state": "Bihar"}}')
