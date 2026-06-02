#!/usr/bin/env python3
"""Package a planned job manifest and stills, then publish the bundle to HF storage."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestration.hf_storage import ensure_dataset_repo, hf_token, job_remote_layout, upload_folder
from orchestration.render_job import parse_slide_selection, refresh_manifest_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Package and publish a job bundle for Kaggle/Colab rendering")
    parser.add_argument("job", help="Local job manifest path")
    parser.add_argument("--repo-id", required=True, help="HF dataset repo id, e.g. yourname/bedtime-story-jobs")
    parser.add_argument("--token", help="HF token; defaults to HF_TOKEN or HUGGINGFACE_HUB_TOKEN")
    parser.add_argument("--slides", help="Optional 1-based slide filter like 1,3-5 for partial retries")
    parser.add_argument("--private", action="store_true", help="Create the HF dataset repo as private if it does not exist")
    parser.add_argument("--staging-dir", help="Optional local staging directory; default .job-bundles/<job-id>")
    parser.add_argument("--dry-run", action="store_true", help="Build the bundle locally but skip upload")
    parser.add_argument("--force", action="store_true", help="Overwrite the local staging directory if it exists")
    return parser


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_manifest(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"❌  Expected a YAML object in {path}")
    return data


def save_manifest(path: Path, manifest: dict) -> None:
    rendered = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=1000)
    path.write_text(rendered, encoding="utf-8")


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def collect_source_images(manifest: dict, selected_slides: set[int] | None) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for slide in manifest.get("slides", []):
        slide_index = int(slide.get("slide_index", 0))
        if selected_slides and slide_index not in selected_slides:
            continue
        for shot in slide.get("shots", []):
            rel_path = shot["source_image"]["path"]
            path = resolve_repo_path(rel_path)
            if not path.exists():
                raise SystemExit(f"❌  Missing source image required for bundle: {path}")
            items.append((rel_path, path))
    return items


def copy_file(relative_path: str, source_path: Path, stage_root: Path) -> None:
    target = stage_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    manifest_path = Path(args.job).resolve()
    if not manifest_path.exists():
        raise SystemExit(f"❌  Job manifest not found: {manifest_path}")

    manifest = load_manifest(manifest_path)
    refresh_manifest_state(manifest)

    job_id = str(manifest.get("job_id") or manifest_path.stem)
    selected_slides = parse_slide_selection(args.slides, int(manifest.get("story", {}).get("slide_count", 0) or len(manifest.get("slides", []))))
    remote = job_remote_layout(job_id)
    token = hf_token(args.token)
    manifest_rel_path = str(manifest.get("manifest_path") or repo_relative(manifest_path))

    manifest.setdefault("storage", {})
    manifest["storage"].update({
        "provider": "hf-dataset",
        "repo_id": args.repo_id,
        **remote,
        "published_at": now_iso(),
    })
    manifest.setdefault("commands", {})
    manifest["commands"].update({
        "publish_bundle": " ".join([
            "python",
            "orchestration/publish_job_bundle.py",
            manifest_rel_path,
            "--repo-id",
            args.repo_id,
        ] + (["--private"] if args.private else [])),
        "kaggle_worker": f"python orchestration/kaggle_worker.py --repo-id {args.repo_id} --job-id {job_id} --install-deps",
        "sync_results": f"python orchestration/sync_job_results.py {manifest_rel_path}",
    })
    save_manifest(manifest_path, manifest)

    stage_root = Path(args.staging_dir).resolve() if args.staging_dir else (REPO_ROOT / ".job-bundles" / job_id)
    if stage_root.exists():
        if not args.force:
            raise SystemExit(f"❌  Staging directory already exists: {stage_root}. Use --force to replace it.")
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)

    copy_file(manifest_rel_path, manifest_path, stage_root)

    source_images = collect_source_images(manifest, selected_slides)
    for rel_path, source_path in source_images:
        copy_file(rel_path, source_path, stage_root)

    runtime_files = [
        "orchestration/__init__.py",
        "orchestration/render_job.py",
        "orchestration/kaggle_worker.py",
        "orchestration/hf_storage.py",
        "requirements-selfhosted.txt",
        "requirements-orchestration.txt",
    ]
    for rel_path in runtime_files:
        copy_file(rel_path, resolve_repo_path(rel_path), stage_root)

    bundle_meta = {
        "schema_version": 1,
        "job_id": job_id,
        "manifest_path": manifest_rel_path,
        "selected_slides": sorted(selected_slides) if selected_slides else "all",
        "source_image_count": len(source_images),
        "repo_id": args.repo_id,
        **remote,
        "created_at": now_iso(),
    }
    bundle_meta_path = stage_root / ".job-bundle.yaml"
    bundle_meta_path.write_text(yaml.safe_dump(bundle_meta, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")

    print(f"[bundle] staged {len(source_images)} source images in {repo_relative(stage_root)}")
    print(f"[bundle] manifest: {manifest_rel_path}")

    if args.dry_run:
        print("[bundle] dry run only; upload skipped")
        return

    ensure_dataset_repo(args.repo_id, token=token, private=bool(args.private))
    upload_folder(
        stage_root,
        repo_id=args.repo_id,
        remote_path=remote["input_prefix"],
        token=token,
        commit_message=f"Publish job bundle for {job_id}",
    )
    print(f"[bundle] uploaded to {args.repo_id}:{remote['input_prefix']}")
    print(f"[next] Kaggle worker: python orchestration/kaggle_worker.py --repo-id {args.repo_id} --job-id {job_id} --install-deps")


if __name__ == "__main__":
    main()