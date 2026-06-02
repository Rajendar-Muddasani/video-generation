#!/usr/bin/env python3
"""Assemble one or more final outputs from a planned job manifest."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from generate_story import animation_output_tag


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble final story videos from a planned job manifest")
    parser.add_argument("job", help="Path to jobs/<story>__<profile>.yaml")
    parser.add_argument("--languages", help="Comma-separated languages to assemble, default: all planned languages")
    parser.add_argument("--dry-run", action="store_true", help="Append --dry-run to the underlying generate_story command")
    parser.add_argument("--force", action="store_true", help="Append --force to the underlying generate_story command")
    parser.add_argument("--validate", action="store_true", help="Validate generated final MP4s with ffmpeg after assembly")
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


def resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def default_final_output(manifest: dict, language: str) -> str:
    story = manifest.get("story", {})
    story_id = story.get("story_id")
    video_mode = manifest.get("plan", {}).get("video_mode", "still")
    final_dir = resolve_repo_path(manifest.get("paths", {}).get("final_dir", f"output/{story_id}"))
    animated_defaults = manifest.get("animation", {}).get("merged_defaults", {})
    if video_mode == "still":
        mode_suffix = ""
    elif video_mode == "storybook":
        mode_suffix = "_storybook_local_2p5d"
    else:
        mode_suffix = f"_{video_mode}_{animation_output_tag(animated_defaults)}"
    return str((final_dir / f"final_{story_id}_{language}{mode_suffix}.mp4").resolve().relative_to(REPO_ROOT))


def ensure_output_entries(manifest: dict) -> dict:
    finals = manifest.setdefault("outputs", {}).setdefault("finals", {})
    for language in manifest.get("plan", {}).get("languages", []):
        finals.setdefault(language, {
            "path": default_final_output(manifest, language),
            "status": "missing",
            "validation_status": "pending",
        })
    return finals


def parse_languages(value: str | None, manifest: dict) -> list[str]:
    available = list(manifest.get("assembly", {}).get("commands", {}).keys())
    if not value:
        return available
    requested = [item.strip() for item in value.split(",") if item.strip()]
    for language in requested:
        if language not in available:
            raise SystemExit(f"❌  Language {language} is not present in the job manifest")
    return requested


def append_flags(command_text: str, dry_run: bool, force: bool) -> list[str]:
    parts = shlex.split(command_text)
    if dry_run and "--dry-run" not in parts:
        parts.append("--dry-run")
    if force and "--force" not in parts:
        parts.append("--force")
    return parts


def validate_output(path: Path) -> tuple[bool, str]:
    cmd = ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-map", "0", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, ""
    detail = (result.stderr or result.stdout or "validation failed").strip()
    return False, detail[-800:]


def refresh_output_state(manifest: dict) -> None:
    finals = ensure_output_entries(manifest)
    ready = 0
    validated = 0
    for output in finals.values():
        output_path = resolve_repo_path(output["path"])
        if output_path.exists():
            output["status"] = "ready"
            ready += 1
            if output.get("validation_status") == "complete":
                validated += 1
        else:
            output["status"] = "missing"
            if output.get("validation_status") == "complete":
                output["validation_status"] = "pending"
                output.pop("validated_at", None)
    plan_status = manifest.setdefault("plan", {}).setdefault("status", {})
    plan_status["assembly"] = "complete" if finals and ready == len(finals) else "pending"
    plan_status["validation"] = "complete" if finals and validated == len(finals) else "pending"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    manifest_path = Path(args.job).resolve()
    if not manifest_path.exists():
        raise SystemExit(f"❌  Job manifest not found: {manifest_path}")
    manifest = load_manifest(manifest_path)
    refresh_output_state(manifest)

    if not args.dry_run and manifest.get("animation", {}).get("provider") == "local":
        missing_clips = int(manifest.get("summary", {}).get("missing_clips", 0))
        if missing_clips > 0:
            raise SystemExit(
                f"❌  Cannot assemble yet: {missing_clips} planned local clips are still missing. Run render_job.py first."
            )

    languages = parse_languages(args.languages, manifest)
    finals = ensure_output_entries(manifest)
    commands = manifest.get("assembly", {}).get("commands", {})

    for language in languages:
        command_parts = append_flags(commands[language], args.dry_run, args.force)
        print(f"[run] {' '.join(shlex.quote(part) for part in command_parts)}")
        result = subprocess.run(command_parts, cwd=REPO_ROOT)
        if result.returncode != 0:
            finals[language]["status"] = "failed"
            finals[language]["last_error"] = f"assembly command exited with {result.returncode}"
            save_manifest(manifest_path, manifest)
            raise SystemExit(result.returncode)

        finals[language]["assembled_at"] = now_iso()
        final_path = resolve_repo_path(finals[language]["path"])
        finals[language]["status"] = "ready" if final_path.exists() else "missing"
        finals[language].pop("last_error", None)

        if args.validate and not args.dry_run and final_path.exists():
            ok, detail = validate_output(final_path)
            finals[language]["validated_at"] = now_iso()
            finals[language]["validation_status"] = "complete" if ok else "failed"
            if ok:
                finals[language].pop("validation_error", None)
            else:
                finals[language]["validation_error"] = detail
                save_manifest(manifest_path, manifest)
                raise SystemExit(f"❌  Validation failed for {language}: {detail}")

        save_manifest(manifest_path, manifest)

    refresh_output_state(manifest)
    manifest.setdefault("run_history", []).append({
        "stage": "assemble_job",
        "finished_at": now_iso(),
        "languages": languages,
        "dry_run": bool(args.dry_run),
        "validate": bool(args.validate),
    })
    save_manifest(manifest_path, manifest)

    ready_outputs = sum(1 for output in finals.values() if output.get("status") == "ready")
    print(f"[done] finals ready: {ready_outputs}/{len(finals)}")


if __name__ == "__main__":
    main()