from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from .codex_loop import OneirosCodexLoop
from .state import RunLayout, load_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="oneiros-ceobench-codex-worker")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--codex-bin", default=None)
    parser.add_argument("--oneiros-bin", default=None)
    parser.add_argument("--max-resume-attempts-per-week", type=int, default=3)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    layout = RunLayout.from_run_dir(args.run_dir)
    config = _config_from_manifest(load_manifest(layout.run_dir))
    loop = OneirosCodexLoop(
        config=cast(Any, config),
        layout=layout,
        codex_bin=args.codex_bin,
        oneiros_bin=args.oneiros_bin,
        max_resume_attempts_per_week=args.max_resume_attempts_per_week,
    )
    result = loop.run(verbose=not args.quiet)
    print(f"result: {json.dumps(result, indent=2, sort_keys=True)}")
    return 0


def _config_from_manifest(manifest: dict[str, Any]) -> SimpleNamespace:
    raw = manifest["config"]
    paths = raw["paths"]
    return SimpleNamespace(
        model=_namespace(raw["model"]),
        run=_namespace(raw["run"]),
        azure_openai=_namespace(raw["azure_openai"]),
        paths=SimpleNamespace(
            ceobench_repo=Path(paths["ceobench_repo"]),
            oneiros_repo=Path(paths["oneiros_repo"]),
        ),
        oneiros=_namespace(raw["oneiros"]),
        oneiros_azure=None,
    )


def _namespace(value: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**value)


if __name__ == "__main__":
    raise SystemExit(main())
