#!/usr/bin/env python3
"""Download a published job bundle, render it, and push results back to HF storage."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestration.hf_storage import download_tree, has_files, hf_token, job_remote_layout, upload_file, upload_folder


VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".webm")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kaggle/Colab worker for a published HF job bundle")
    parser.add_argument("--repo-id", required=True, help="HF dataset repo id")
    parser.add_argument("--job-id", required=True, help="Job id from the manifest")
    parser.add_argument("--token", help="HF token; defaults to HF_TOKEN or HUGGINGFACE_HUB_TOKEN")
    parser.add_argument("--slides", help="Optional 1-based slide filter like 1,3-5")
    parser.add_argument("--status-only", action="store_true", help="Only refresh manifest state; do not render")
    parser.add_argument("--force", action="store_true", help="Re-render clips even if they exist in the workdir")
    parser.add_argument("--install-deps", action="store_true", help="Install requirements-orchestration.txt and requirements-selfhosted.txt from the bundle")
    parser.add_argument("--device", help="Override torch device for render_job.py")
    parser.add_argument("--dtype", choices=["bfloat16", "float16", "float32"], help="Override torch dtype for render_job.py")
    parser.add_argument("--cpu-offload", action="store_true", help="Enable CPU offload for render_job.py")
    parser.add_argument("--workdir", help="Local worker directory; default /kaggle/working/<job-id> when available")
    parser.add_argument("--bundle-dir", help="Use an already-staged local bundle directory instead of downloading from HF")
    parser.add_argument("--skip-upload", action="store_true", help="Skip uploading results; useful for local dry-run validation")
    parser.add_argument("--outbox-dir", help="When set, write remote-style state/results folders locally for manual sync")
    parser.add_argument("--keep-workdir", action="store_true", help="Keep the working directory after completion")
    return parser


def load_yaml(path: Path) -> dict:
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


def default_workdir(job_id: str) -> Path:
    kaggle_root = Path("/kaggle/working")
    if kaggle_root.exists():
        return kaggle_root / job_id
    return Path.cwd() / ".job-bundles" / "remote-work" / job_id


def maybe_install_deps(workdir: Path) -> None:
    for rel_path in ("requirements-orchestration.txt", "requirements-selfhosted.txt"):
        req_path = workdir / rel_path
        if req_path.exists():
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req_path)], check=True)


def running_on_kaggle() -> bool:
    return Path("/kaggle/working").exists()


def iter_ready_clip_paths(manifest: dict, workdir: Path):
    for slide in manifest.get("slides", []):
        for shot in slide.get("shots", []):
            clip = shot.get("clip", {})
            rel_path = clip.get("path")
            if not rel_path or clip.get("status") != "ready":
                continue
            clip_path = Path(rel_path)
            if not clip_path.is_absolute():
                clip_path = workdir / clip_path
            if clip_path.is_file() and clip_path.suffix.lower() in VIDEO_SUFFIXES:
                yield str(rel_path), clip_path


def upload_progress(repo_id: str, remote: dict[str, str], token: str | None,
                    workdir: Path, manifest_rel: str, progress_state: dict) -> None:
    manifest_path = workdir / manifest_rel
    if not manifest_path.exists():
        return

    manifest_mtime_ns = manifest_path.stat().st_mtime_ns
    if progress_state.get("manifest_mtime_ns") == manifest_mtime_ns:
        return

    try:
        manifest = load_yaml(manifest_path)
    except Exception:
        return

    upload_file(
        manifest_path,
        repo_id=repo_id,
        remote_path=f"{remote['state_prefix']}/{manifest_rel}",
        token=token,
        commit_message=f"Update manifest progress for {remote['job_root'].split('/')[-1]}",
    )
    progress_state["manifest_mtime_ns"] = manifest_mtime_ns

    uploaded_clip_rel_paths = progress_state.setdefault("uploaded_clip_rel_paths", set())
    for rel_path, clip_path in iter_ready_clip_paths(manifest, workdir):
        if rel_path in uploaded_clip_rel_paths:
            continue
        upload_file(
            clip_path,
            repo_id=repo_id,
            remote_path=f"{remote['results_prefix']}/{rel_path}",
            token=token,
            commit_message=f"Upload rendered clip {Path(rel_path).name} for {remote['job_root'].split('/')[-1]}",
        )
        uploaded_clip_rel_paths.add(rel_path)


def selected_slides_arg(bundle_meta: dict, explicit_slides: str | None) -> str | None:
    if explicit_slides:
        return explicit_slides
    selected = bundle_meta.get("selected_slides")
    if selected in (None, "all"):
        return None
    return ",".join(str(item) for item in selected)


def build_render_command(workdir: Path, manifest_rel: str, args, bundle_meta: dict) -> list[str]:
    command = [
        sys.executable,
        str(workdir / "orchestration" / "render_job.py"),
        str(workdir / manifest_rel),
    ]
    slides = selected_slides_arg(bundle_meta, args.slides)
    if slides:
        command.extend(["--slides", slides])
    if args.status_only:
        command.append("--status-only")
    if args.force:
        command.append("--force")
    if args.device:
        command.extend(["--device", args.device])
    if args.dtype:
        command.extend(["--dtype", args.dtype])
    auto_cpu_offload = (
        running_on_kaggle()
        and not args.status_only
        and (args.device is None or args.device.startswith("cuda"))
    )
    if args.cpu_offload or auto_cpu_offload:
        command.append("--cpu-offload")
    return command


def merge_remote_state(repo_id: str, remote: dict[str, str], token: str | None, workdir: Path) -> None:
    for remote_path in (remote["state_prefix"], remote["results_prefix"]):
        try:
            download_tree(repo_id=repo_id, remote_path=remote_path, local_dir=workdir, token=token)
        except SystemExit:
            continue


def write_outbox(outbox_root: Path, workdir: Path, manifest_rel: str, manifest: dict) -> None:
    state_root = outbox_root / "state"
    results_root = outbox_root / "results"
    state_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)

    manifest_src = workdir / manifest_rel
    manifest_dst = state_root / manifest_rel
    manifest_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_src, manifest_dst)

    shot_dir_rel = manifest.get("paths", {}).get("shot_dir")
    if shot_dir_rel:
        clip_src = workdir / shot_dir_rel
        if clip_src.exists() and has_files(clip_src, suffixes=(".mp4", ".mov", ".mkv", ".webm")):
            copy_tree(clip_src, results_root / shot_dir_rel)


def upload_results(repo_id: str, remote: dict[str, str], token: str | None,
                   workdir: Path, manifest_rel: str, manifest: dict) -> None:
    manifest_path = workdir / manifest_rel
    upload_file(
        manifest_path,
        repo_id=repo_id,
        remote_path=f"{remote['state_prefix']}/{manifest_rel}",
        token=token,
        commit_message=f"Update manifest state for {remote['job_root'].split('/')[-1]}",
    )

    shot_dir_rel = manifest.get("paths", {}).get("shot_dir")
    if shot_dir_rel:
        clip_dir = workdir / shot_dir_rel
        if clip_dir.exists() and has_files(clip_dir, suffixes=(".mp4", ".mov", ".mkv", ".webm")):
            upload_folder(
                clip_dir,
                repo_id=repo_id,
                remote_path=f"{remote['results_prefix']}/{shot_dir_rel}",
                token=token,
                commit_message=f"Upload rendered clips for {remote['job_root'].split('/')[-1]}",
            )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    token = hf_token(args.token)
    remote = job_remote_layout(args.job_id)

    if args.bundle_dir:
        workdir = Path(args.bundle_dir).resolve()
        if not workdir.exists():
            raise SystemExit(f"❌  Local bundle directory not found: {workdir}")
    else:
        workdir = Path(args.workdir).resolve() if args.workdir else default_workdir(args.job_id).resolve()
        if workdir.exists() and not args.keep_workdir:
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        download_tree(repo_id=args.repo_id, remote_path=remote["input_prefix"], local_dir=workdir, token=token)
        merge_remote_state(args.repo_id, remote, token, workdir)

    bundle_meta = load_yaml(workdir / ".job-bundle.yaml")
    manifest_rel = str(bundle_meta["manifest_path"])

    if args.install_deps:
        maybe_install_deps(workdir)

    command = build_render_command(workdir, manifest_rel, args, bundle_meta)
    if running_on_kaggle() and not args.cpu_offload and not args.status_only:
        print("[info] Kaggle worker enabling --cpu-offload automatically for LTX compatibility")
    print(f"[run] {' '.join(command)}")
    exit_code = 0
    progress_state = {
        "manifest_mtime_ns": None,
        "uploaded_clip_rel_paths": set(),
    }
    try:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        process = subprocess.Popen(command, cwd=workdir, env=env)
        while True:
            exit_code = process.poll()
            if exit_code is not None:
                break
            if not args.skip_upload:
                try:
                    upload_progress(args.repo_id, remote, token, workdir, manifest_rel, progress_state)
                except Exception as exc:
                    print(f"[warn] incremental upload skipped: {exc}")
            time.sleep(20)
    finally:
        manifest = load_yaml(workdir / manifest_rel)
        if args.outbox_dir:
            write_outbox(Path(args.outbox_dir).resolve(), workdir, manifest_rel, manifest)
        if not args.skip_upload:
            upload_results(args.repo_id, remote, token, workdir, manifest_rel, manifest)

    if exit_code != 0:
        raise SystemExit(exit_code)
    if args.skip_upload:
        print("[done] upload skipped; manifest state remains in the local bundle/outbox")
    else:
        print(f"[done] uploaded manifest state and rendered clips to {args.repo_id}:{remote['results_prefix']}")

    if not args.bundle_dir and not args.keep_workdir and workdir.exists():
        shutil.rmtree(workdir)


if __name__ == "__main__":
    main()