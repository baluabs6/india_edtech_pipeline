import json
import logging
import os
import shutil
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

REGISTRY_DIR = os.getenv("MODEL_REGISTRY_DIR", "model_registry")
MANIFEST_PATH = os.path.join(REGISTRY_DIR, "manifest.json")
CURRENT_MODEL_PATH = "dropout_model.joblib"  # the file app.py actually loads


def _load_manifest() -> list[dict]:
    if not os.path.exists(MANIFEST_PATH):
        return []
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def _save_manifest(entries: list[dict]):
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def register_version(source_model_path: str, metrics: dict) -> str:
    """Copies the trained model into the registry under a timestamped version,
    records its metrics, and promotes it to the live `dropout_model.joblib`."""
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    versioned_path = os.path.join(REGISTRY_DIR, f"dropout_model_{version}.joblib")
    shutil.copy(source_model_path, versioned_path)

    entries = _load_manifest()
    entries.append({"version": version, "path": versioned_path, "metrics": metrics,
                     "promoted": True})
    for entry in entries[:-1]:
        entry["promoted"] = False  # only the newest version is "live" by default
    _save_manifest(entries)

    shutil.copy(versioned_path, CURRENT_MODEL_PATH)
    logger.info("Registered model version %s (roc_auc=%.3f) and promoted to live", version, metrics.get("roc_auc", 0))
    return version


def list_versions() -> list[dict]:
    return _load_manifest()


def rollback_to(version: str) -> bool:
    """Promotes a previously registered version back to live."""
    entries = _load_manifest()
    target = next((e for e in entries if e["version"] == version), None)
    if not target:
        return False
    shutil.copy(target["path"], CURRENT_MODEL_PATH)
    for entry in entries:
        entry["promoted"] = (entry["version"] == version)
    _save_manifest(entries)
    logger.info("Rolled back live model to version %s", version)
    return True
