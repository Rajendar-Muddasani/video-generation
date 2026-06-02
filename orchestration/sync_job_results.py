#!/usr/bin/env python3
"""Pull updated manifest state and rendered clips back from HF storage or a local outbox."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestration.hf_storage import download_tree, hf_token, job_remote_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync remote manifest state and clips back into the repo")
    parser.add_argument("job", help="Local job manifest path")
    parser.add_argument("--repo-id", help="HF dataset repo id; defaults to manifest storage.repo_id")
    parser.add_argument("--token", help="HF token; defaults to HF_TOKEN or HUGGINGFACE_HUB_TOKEN")
    parser.add_argument("--from-dir", help="Use a local outbox directory instead of downloading from HF")
    parser.add_argument("--manifest-only", action="store_true", help="Sync only the updated manifest, not rendered clips")
    return parser


def load_manifest(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"❌  Expected a YAML object in {path}")
    return data


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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    manifest_path = Path(args.job).resolve()
    if not manifest_path.exists():
        raise SystemExit(f"❌  Job manifest not found: {manifest_path}")
    manifest = load_manifest(manifest_path)

    job_id = str(manifest.get("job_id") or manifest_path.stem)
    storage = manifest.get("storage", {})
    repo_id = args.repo_id or storage.get("repo_id")
    remote = {**job_remote_layout(job_id), **storage}
    token = hf_token(args.token)

    if args.from_dir:
        outbox_dir = Path(args.from_dir).resolve()
        if not outbox_dir.exists():
            raise SystemExit(f"❌  Local outbox directory not found: {outbox_dir}")
        state_dir = outbox_dir / "state"
        result_dir = outbox_dir / "results"
        if not state_dir.exists():
            raise SystemExit(f"❌  Missing state directory in outbox: {state_dir}")
        copied_manifests = copy_tree(state_dir, REPO_ROOT)
        copied_clips = 0 if args.manifest_only or not result_dir.exists() else copy_tree(result_dir, REPO_ROOT)
        print(f"[sync] updated manifest files: {copied_manifests}")
        print(f"[sync] updated clip files: {copied_clips}")
        return

    if not repo_id:
        raise SystemExit("❌  Missing repo id. Pass --repo-id or publish the job first so storage.repo_id is recorded.")

    with tempfile.TemporaryDirectory(prefix=f"sync-{job_id}-") as tmp_dir_text:
        tmp_dir = Path(tmp_dir_text)
        state_dir = tmp_dir / "state"
        clip_dir = tmp_dir / "results"

        state_files = download_tree(repo_id=repo_id, remote_path=remote["state_prefix"], local_dir=state_dir, token=token)
        if state_files == 0:
            raise SystemExit(f"❌  No remote manifest state found at {repo_id}:{remote['state_prefix']}")
        copied_manifests = copy_tree(state_dir, REPO_ROOT)

        copied_clips = 0
        if not args.manifest_only:
            try:
                result_files = download_tree(repo_id=repo_id, remote_path=remote["results_prefix"], local_dir=clip_dir, token=token)
            except SystemExit:
                result_files = 0
            if result_files:
                copied_clips = copy_tree(clip_dir, REPO_ROOT)

    print(f"[sync] updated manifest files: {copied_manifests}")
    print(f"[sync] updated clip files: {copied_clips}")


if __name__ == "__main__":
    main()