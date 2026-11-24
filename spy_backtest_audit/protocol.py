"""Check the recorded configuration and snapshot hashes."""
import hashlib
import json

from .data import DataValidationError
def verify_validation_freeze(root):
    path = root / "research/validation_freeze.json"
    freeze = json.loads(path.read_text(encoding="utf-8"))
    if freeze.get("version") != 1 or freeze.get("status") != "RULES_FROZEN_NOT_EXECUTED":
        raise DataValidationError("Unsupported validation freeze")
    for relative, expected in freeze["file_sha256"].items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise DataValidationError(f"Frozen methodology changed: {relative}; document a new protocol version")
    manifest = json.loads((root / "data/raw/spy.manifest.json").read_text(encoding="utf-8"))
    if manifest.get("sha256") != freeze["snapshot_sha256"]:
        raise DataValidationError("Dataset differs from the validation freeze")
    return freeze
