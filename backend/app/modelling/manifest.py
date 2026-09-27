from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_manifest(
    path: Path,
    *,
    model: str,
    adapter_version: str,
    variant_parameters: dict[str, Any],
    native_input_directory: Path,
    preprocessing_artifacts: dict[str, str | None] | None = None,
) -> Path:
    payload = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "adapter_version": adapter_version,
        "native_input_directory": str(native_input_directory.resolve()),
        "variant_parameters": variant_parameters,
        "preprocessing_artifacts": preprocessing_artifacts or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
