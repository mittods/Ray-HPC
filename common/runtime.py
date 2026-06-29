"""Artifact path utilities for the experiment (mirrors production runtime.py)."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

ARTIFACT_ROOT = Path(os.getenv("ARTIFACT_ROOT", "/tmp/exp_artifacts"))


def submission_artifact_dir(submission_id: str) -> Path:
    return ARTIFACT_ROOT / submission_id


def ensure_submission_artifact_dir(submission_id: str) -> Path:
    d = submission_artifact_dir(submission_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_submission_manifest(submission_id: str, manifest: dict[str, Any]) -> None:
    d = ensure_submission_artifact_dir(submission_id)
    (d / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def read_submission_manifest(submission_id: str) -> dict[str, Any]:
    p = submission_artifact_dir(submission_id) / "manifest.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def cleanup_submission_artifacts(submission_id: str) -> None:
    d = submission_artifact_dir(submission_id)
    if not d.exists():
        return
    for path in sorted(d.glob("**/*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()
    d.rmdir()
