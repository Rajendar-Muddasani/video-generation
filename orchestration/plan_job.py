#!/usr/bin/env python3
"""Build a reusable run manifest from a story YAML and a channel profile."""

from __future__ import annotations

import argparse
import shlex
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from generate_story import animation_output_tag, animated_defaults_for_story, load_story, resolve_slide_shots, story_slide_records, video_prompt_for_shot


SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a reusable animation job manifest from a story and profile")
    parser.add_argument("story", help="Story YAML or legacy Python story path")
    parser.add_argument("--profile", required=True, help="Profile YAML path, e.g. profiles/bedtime-lowcost-v1.yaml")
    parser.add_argument("--output", help="Output manifest path, default: jobs/<story-id>__<profile-id>.yaml")
    parser.add_argument("--job-id", help="Optional stable job id override")
    parser.add_argument("--stdout", action="store_true", help="Print manifest to stdout instead of writing a file")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing manifest file")
    return parser


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"❌  Expected a YAML object at the top level in {path}")
    return data


def require_keys(data: dict, dotted_keys: list[str], label: str) -> None:
    missing: list[str] = []
    for dotted in dotted_keys:
        current = data
        ok = True
        for part in dotted.split("."):
            if not isinstance(current, dict) or part not in current:
                ok = False
                break
            current = current[part]
        if not ok:
            missing.append(dotted)
    if missing:
        missing_text = ", ".join(missing)
        raise SystemExit(f"❌  {label} is missing required keys: {missing_text}")


def deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return deepcopy(override)
    merged = deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def expand_repo_path(template: str, *, story_id: str, profile_id: str, job_id: str) -> Path:
    rendered = template.format(story_id=story_id, profile_id=profile_id, job_id=job_id)
    path = Path(rendered)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def shell_join(parts: list[object]) -> str:
    return shlex.join([str(part) for part in parts])


def build_worker_command(story_path: str, image_dir: str, shot_dir: str,
                         animation_block: dict) -> str:
    worker_args = animation_block.get("worker_args", {})
    command = [
        "python",
        animation_block["generate_script"],
        story_path,
        "--image-dir",
        image_dir,
        "--output-dir",
        shot_dir,
        "--model",
        animation_block["model"],
        "--dtype",
        worker_args.get("dtype", "bfloat16"),
        "--device",
        worker_args.get("device", "cuda"),
        "--width",
        worker_args.get("width", 704),
        "--height",
        worker_args.get("height", 480),
        "--fps",
        worker_args.get("fps", 24),
        "--seconds",
        worker_args.get("seconds", 4),
        "--steps",
        worker_args.get("steps", 8),
        "--guidance-scale",
        worker_args.get("guidance_scale", 1.0),
        "--negative-prompt",
        worker_args.get("negative_prompt", "worst quality, blurry, jittery, distorted, flicker"),
        "--seed",
        worker_args.get("seed", 42),
    ]
    if worker_args.get("cpu_offload"):
        command.append("--cpu-offload")
    return shell_join(command)


def build_assembly_command(story_path: str, manifest_path: str, language: str) -> str:
    command = [
        "python",
        "generate_story.py",
        story_path,
        "--job-manifest",
        manifest_path,
        "--lang",
        language,
    ]
    return shell_join(command)


def planned_final_path(final_dir: Path, story_id: str, language: str,
                       video_mode: str, animated_defaults: dict) -> Path:
    if video_mode == "still":
        mode_suffix = ""
    elif video_mode == "storybook":
        mode_suffix = "_storybook_local_2p5d"
    else:
        mode_suffix = f"_{video_mode}_{animation_output_tag(animated_defaults)}"
    return final_dir / f"final_{story_id}_{language}{mode_suffix}.mp4"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    story_path = Path(args.story).resolve()
    profile_path = Path(args.profile).resolve()

    if not story_path.exists():
        raise SystemExit(f"❌  Story file not found: {story_path}")
    if not profile_path.exists():
        raise SystemExit(f"❌  Profile file not found: {profile_path}")

    profile = load_yaml(profile_path)
    require_keys(
        profile,
        [
            "profile_id",
            "display_name",
            "genre",
            "plan.languages",
            "plan.video_mode",
            "source_images.provider",
            "source_images.dir_template",
            "animation.provider",
            "animation.backend",
            "animation.model",
            "animation.output_dir_template",
            "animation.generate_script",
            "budget.target_cost_usd",
        ],
        label=f"Profile {profile_path.name}",
    )

    story = load_story(str(story_path), "en")
    story_id = story.STORY_ID
    profile_id = str(profile["profile_id"])
    job_id = args.job_id or f"{story_id}__{profile_id}"

    raw_story_defaults = deepcopy(getattr(story, "ANIMATED_DEFAULTS", {}) or {})
    raw_profile_defaults = deepcopy(profile.get("animation", {}).get("defaults_override", {}))
    merged_defaults = animated_defaults_for_story(
        SimpleNamespace(ANIMATED_DEFAULTS=deep_merge(raw_story_defaults, raw_profile_defaults))
    )

    default_output = REPO_ROOT / "jobs" / f"{job_id}.yaml"
    output_path = Path(args.output).resolve() if args.output else default_output
    manifest_path_rel = repo_relative(output_path)

    story_path_rel = repo_relative(story_path)
    profile_path_rel = repo_relative(profile_path)
    image_dir = expand_repo_path(
        profile["source_images"]["dir_template"],
        story_id=story_id,
        profile_id=profile_id,
        job_id=job_id,
    )
    shot_dir = expand_repo_path(
        profile["animation"]["output_dir_template"],
        story_id=story_id,
        profile_id=profile_id,
        job_id=job_id,
    )
    final_dir = expand_repo_path(
        profile.get("assembly", {}).get("final_dir_template", "output/{story_id}"),
        story_id=story_id,
        profile_id=profile_id,
        job_id=job_id,
    )

    image_dir_rel = repo_relative(image_dir)
    shot_dir_rel = repo_relative(shot_dir)
    final_dir_rel = repo_relative(final_dir)

    languages = list(profile["plan"]["languages"])
    video_mode = str(profile["plan"]["video_mode"])
    image_provider = str(profile["source_images"]["provider"])
    animation_provider = str(profile["animation"]["provider"])

    slide_records_en = story_slide_records(story, "en")
    slide_records_te = story_slide_records(story, "te") if "te" in languages else []

    slide_entries: list[dict] = []
    total_shots = 0
    total_clip_seconds = 0
    existing_source_images = 0
    existing_clips = 0

    for slide_index, slide_en in enumerate(slide_records_en, 1):
        shots = resolve_slide_shots(story, slide_records_en, slide_index - 1, merged_defaults)
        te_slide = slide_records_te[slide_index - 1] if slide_index - 1 < len(slide_records_te) else None
        slide_tag = f"slide{slide_index:02d}"
        shot_entries: list[dict] = []

        for shot_index, shot in enumerate(shots, 1):
            shot_tag = f"{slide_tag}_shot{shot_index:02d}"
            source_image_path = image_dir / f"{shot_tag}_raw.jpg"
            shot_clip_path = shot_dir / f"{shot_tag}.mp4"
            duration = int(shot.get("duration", merged_defaults["shot_duration_seconds"]))
            source_image_exists = source_image_path.exists()
            shot_clip_exists = shot_clip_path.exists()

            total_shots += 1
            total_clip_seconds += duration
            if source_image_exists:
                existing_source_images += 1
            if shot_clip_exists:
                existing_clips += 1

            shot_entries.append({
                "shot_index": shot_index,
                "shot_tag": shot_tag,
                "duration_seconds": duration,
                "image_prompt": shot.get("image_prompt", slide_en.get("dall_e_prompt", "")),
                "motion_prompt": shot.get("motion_prompt", ""),
                "video_prompt": video_prompt_for_shot(shot, slide_en.get("dall_e_prompt", ""), merged_defaults),
                "source_image": {
                    "path": repo_relative(source_image_path),
                    "status": "ready" if source_image_exists else "missing",
                },
                "clip": {
                    "path": repo_relative(shot_clip_path),
                    "status": "ready" if shot_clip_exists else "missing",
                    "qc": "pending",
                },
            })

        slide_entries.append({
            "slide_index": slide_index,
            "slide_tag": slide_tag,
            "title_en": slide_en.get("title", ""),
            "title_te": te_slide.get("title", "") if te_slide else "",
            "eyebrow": slide_en.get("eyebrow", ""),
            "scene_prompt": slide_en.get("dall_e_prompt", ""),
            "narration_languages": [lang for lang in languages if (lang != "te" or te_slide is not None)],
            "shots": shot_entries,
        })

    generate_clips_raw_command = build_worker_command(story_path_rel, image_dir_rel, shot_dir_rel, profile["animation"])
    render_job_command = shell_join(["python", "orchestration/render_job.py", manifest_path_rel])
    assemble_job_command = shell_join(["python", "orchestration/assemble_job.py", manifest_path_rel])
    assembly_commands = {
        language: build_assembly_command(story_path_rel, manifest_path_rel, language)
        for language in languages
    }
    final_outputs = {
        language: {
            "path": repo_relative(planned_final_path(final_dir, story_id, language, video_mode, merged_defaults)),
            "status": "ready" if planned_final_path(final_dir, story_id, language, video_mode, merged_defaults).exists() else "missing",
            "validation_status": "pending",
        }
        for language in languages
    }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "manifest_path": manifest_path_rel,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": {
            "path": story_path_rel,
            "story_id": story_id,
            "title_en": getattr(story, "STORY_TITLE", story_id),
            "title_te": getattr(story, "_yaml_meta", {}).get("story_title_te", "") if getattr(story, "_is_yaml", False) else "",
            "slide_count": len(slide_records_en),
        },
        "profile": {
            "path": profile_path_rel,
            "profile_id": profile_id,
            "display_name": profile["display_name"],
            "genre": profile["genre"],
            "description": profile.get("description", ""),
        },
        "plan": {
            "video_mode": video_mode,
            "languages": languages,
            "status": {
                "planner": "complete",
                "source_images": "pending",
                "clips": "pending",
                "assembly": "pending",
                "validation": "pending",
            },
        },
        "paths": {
            "source_image_dir": image_dir_rel,
            "shot_dir": shot_dir_rel,
            "final_dir": final_dir_rel,
        },
        "source_images": profile["source_images"],
        "animation": {
            "provider": animation_provider,
            "backend": profile["animation"]["backend"],
            "model": profile["animation"]["model"],
            "generate_script": profile["animation"]["generate_script"],
            "worker_args": profile["animation"].get("worker_args", {}),
            "merged_defaults": merged_defaults,
        },
        "assembly": {
            "script": "generate_story.py",
            "driver_script": "orchestration/assemble_job.py",
            "reuse_shots_across_languages": bool(profile.get("assembly", {}).get("reuse_shots_across_languages", True)),
            "commands": deepcopy(assembly_commands),
        },
        "outputs": {
            "finals": final_outputs,
        },
        "budget": profile["budget"],
        "quality_control": profile.get("quality_control", {}),
        "commands": {
            "generate_clips": render_job_command,
            "generate_clips_raw": generate_clips_raw_command,
            "dry_run_en": f"{assembly_commands.get('en', next(iter(assembly_commands.values())))} --dry-run" if assembly_commands else "",
            "assemble_job": assemble_job_command,
            "assemble": deepcopy(assembly_commands),
        },
        "summary": {
            "total_slides": len(slide_records_en),
            "total_shots": total_shots,
            "total_clip_seconds": total_clip_seconds,
            "existing_source_images": existing_source_images,
            "missing_source_images": total_shots - existing_source_images,
            "existing_clips": existing_clips,
            "missing_clips": total_shots - existing_clips,
        },
        "slides": slide_entries,
    }

    rendered = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=1000)
    if args.stdout:
        sys.stdout.write(rendered)
        return

    if output_path.exists() and not args.force:
        raise SystemExit(f"❌  Manifest already exists: {output_path}. Use --force to overwrite.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")

    print(f"[plan] wrote {repo_relative(output_path)}")
    print(f"[plan] shots: {total_shots} | clip seconds: {total_clip_seconds}")
    print(f"[plan] source images ready: {existing_source_images}/{total_shots}")
    print(f"[plan] clips ready: {existing_clips}/{total_shots}")


if __name__ == "__main__":
    main()