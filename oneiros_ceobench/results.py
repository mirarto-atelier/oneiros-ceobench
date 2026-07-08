from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def aggregate_results(results_dir: Path, output_path: Path) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    if results_dir.exists():
        for path in sorted(results_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                runs.append(data)

    payload = {"runs": runs}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload
