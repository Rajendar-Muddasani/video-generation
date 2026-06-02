#!/usr/bin/env python3
"""Small Hugging Face dataset storage helpers for job bundles and results."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def hf_token(explicit_token: str | None = None) -> str | None:
    return explicit_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")


def require_hf():
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "❌  Missing Hugging Face Hub support. Install requirements-orchestration.txt first."
        ) from exc
    return HfApi, snapshot_download


def ensure_dataset_repo(repo_id: str, *, token: str | None, private: bool) -> None:
    HfApi, _ = require_hf()
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)


def upload_folder(local_dir: Path, *, repo_id: str, remote_path: str,
                  token: str | None, commit_message: str) -> None:
    HfApi, _ = require_hf()
    api = HfApi(token=token)
    api.upload_folder(
        folder_path=str(local_dir),
        repo_id=repo_id,
        repo_type="dataset",
        path_in_repo=remote_path,
        commit_message=commit_message,
    )


def upload_file(local_path: Path, *, repo_id: str, remote_path: str,
                token: str | None, commit_message: str) -> None:
    HfApi, _ = require_hf()
    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=str(local_path),
        repo_id=repo_id,
        repo_type="dataset",
        path_in_repo=remote_path,
        commit_message=commit_message,
    )


def copy_tree(src: Path, dst: Path) -> int:
    count = 0
    for file_path in src.rglob("*"):
        if not file_path.is_file():
            continue
        rel_path = file_path.relative_to(src)
        target = dst / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)
        count += 1
    return count


def download_tree(*, repo_id: str, remote_path: str, local_dir: Path,
                  token: str | None) -> int:
    _, snapshot_download = require_hf()
    snapshot_root = Path(snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        allow_patterns=[f"{remote_path}/**", f"{remote_path}/*", f"{remote_path}/.*"],
    ))
    source_dir = snapshot_root / remote_path
    if not source_dir.exists():
        raise SystemExit(f"❌  Remote path not found in dataset repo: {remote_path}")
    local_dir.mkdir(parents=True, exist_ok=True)
    return copy_tree(source_dir, local_dir)


def has_files(path: Path, suffixes: tuple[str, ...] | None = None) -> bool:
    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        if suffixes is None or file_path.suffix.lower() in suffixes:
            return True
    return False


def job_remote_layout(job_id: str) -> dict[str, str]:
    root = f"jobs/{job_id}"
    return {
        "job_root": root,
        "input_prefix": f"{root}/input",
        "state_prefix": f"{root}/state",
        "results_prefix": f"{root}/results",
    }