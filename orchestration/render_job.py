#!/usr/bin/env python3
"""Render missing local shot clips directly from a planned job manifest."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render missing self-hosted clips from a planned job manifest")
    parser.add_argument("job", help="Path to jobs/<story>__<profile>.yaml")
    parser.add_argument("--slides", help="Optional 1-based slide selection like 1,3-5")
    parser.add_argument("--status-only", action="store_true", help="Refresh source/clip status in the manifest without generating clips")
    parser.add_argument("--force", action="store_true", help="Re-render clips even when the output file already exists")
    parser.add_argument("--cpu-offload", action="store_true", help="Override worker settings and enable model CPU offload")
    parser.add_argument("--device", help="Override the torch device, for example cuda")
    parser.add_argument("--dtype", choices=["bfloat16", "float16", "float32"], help="Override torch dtype")
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


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def parse_slide_selection(selection: str | None, total_slides: int) -> set[int] | None:
    if not selection:
        return None
    chosen: set[int] = set()
    for token in selection.split(","):
        chunk = token.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise SystemExit(f"❌  Invalid slide range: {chunk}")
            for slide_num in range(start, end + 1):
                if not 1 <= slide_num <= total_slides:
                    raise SystemExit(f"❌  Slide out of range in selection: {slide_num}")
                chosen.add(slide_num)
        else:
            slide_num = int(chunk)
            if not 1 <= slide_num <= total_slides:
                raise SystemExit(f"❌  Slide out of range in selection: {slide_num}")
            chosen.add(slide_num)
    return chosen


def selected_shots(manifest: dict, selected_slides: set[int] | None):
    for slide in manifest.get("slides", []):
        slide_index = int(slide.get("slide_index", 0))
        if selected_slides and slide_index not in selected_slides:
            continue
        for shot in slide.get("shots", []):
            yield slide, shot


def refresh_manifest_state(manifest: dict) -> None:
    total_shots = 0
    total_clip_seconds = 0
    existing_source_images = 0
    existing_clips = 0

    for slide in manifest.get("slides", []):
        for shot in slide.get("shots", []):
            total_shots += 1
            total_clip_seconds += int(shot.get("duration_seconds", 0))

            source_path = resolve_repo_path(shot["source_image"]["path"])
            clip_path = resolve_repo_path(shot["clip"]["path"])

            source_ready = source_path.exists()
            clip_ready = clip_path.exists()

            shot["source_image"]["status"] = "ready" if source_ready else "missing"
            if source_ready:
                existing_source_images += 1

            if clip_ready:
                shot["clip"]["status"] = "ready"
                existing_clips += 1
            elif shot["source_image"]["status"] == "missing":
                shot["clip"]["status"] = "blocked"
            else:
                shot["clip"]["status"] = "missing"

    manifest.setdefault("summary", {})
    manifest["summary"].update({
        "total_slides": len(manifest.get("slides", [])),
        "total_shots": total_shots,
        "total_clip_seconds": total_clip_seconds,
        "existing_source_images": existing_source_images,
        "missing_source_images": total_shots - existing_source_images,
        "existing_clips": existing_clips,
        "missing_clips": total_shots - existing_clips,
    })

    plan_status = manifest.setdefault("plan", {}).setdefault("status", {})
    plan_status["source_images"] = "complete" if total_shots == existing_source_images else "pending"
    plan_status["clips"] = "complete" if total_shots == existing_clips else "pending"
    plan_status.setdefault("assembly", "pending")
    plan_status.setdefault("validation", "pending")


def parse_torch_dtype(name: str):
    import torch

    mapping = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    return mapping[name]


def load_ltx_pipeline(model_name: str, dtype_name: str, device: str, cpu_offload: bool):
    import torch

    try:
        from diffusers import LTXImageToVideoPipeline
    except ImportError as exc:
        raise SystemExit(
            "❌  Missing self-hosted video dependencies. Install requirements-selfhosted.txt and a GPU torch build first."
        ) from exc

    resolved_dtype_name = dtype_name
    if device.startswith("cuda") and dtype_name == "bfloat16":
        if not torch.cuda.is_available():
            raise SystemExit("❌  Requested CUDA rendering, but torch.cuda is not available on this worker.")
        is_bf16_supported = getattr(torch.cuda, "is_bf16_supported", None)
        if callable(is_bf16_supported) and not is_bf16_supported():
            print("[warn] CUDA device does not support bfloat16; falling back to float16")
            resolved_dtype_name = "float16"

    dtype = parse_torch_dtype(resolved_dtype_name)
    load_kwargs = {
        "torch_dtype": dtype,
    }
    if cpu_offload:
        load_kwargs["low_cpu_mem_usage"] = True
        if device.startswith("cuda") and torch.cuda.is_available():
            gpu_index = 0
            if ":" in device:
                gpu_index = int(device.split(":", 1)[1])
            total_vram_gib = torch.cuda.get_device_properties(gpu_index).total_memory / (1024 ** 3)
            gpu_budget_gib = max(1, int(total_vram_gib - 1))
            load_kwargs["device_map"] = "balanced"
            load_kwargs["max_memory"] = {
                gpu_index: f"{gpu_budget_gib}GiB",
                "cpu": "28GiB",
            }
            load_kwargs["offload_state_dict"] = True

    pipe = LTXImageToVideoPipeline.from_pretrained(model_name, **load_kwargs)
    if hasattr(pipe, "vae"):
        if hasattr(pipe.vae, "enable_tiling"):
            pipe.vae.enable_tiling()
        if hasattr(pipe.vae, "enable_slicing"):
            pipe.vae.enable_slicing()
    if cpu_offload:
        if "device_map" in load_kwargs:
            return pipe, "cpu"
        applied_group_offload = False
        try:
            from diffusers.hooks import apply_group_offloading

            onload_device = torch.device(device)
            offload_device = torch.device("cpu")

            if hasattr(pipe, "transformer") and hasattr(pipe.transformer, "enable_group_offload"):
                pipe.transformer.enable_group_offload(
                    onload_device=onload_device,
                    offload_device=offload_device,
                    offload_type="leaf_level",
                    use_stream=True,
                )
                applied_group_offload = True
            if hasattr(pipe, "text_encoder"):
                apply_group_offloading(
                    pipe.text_encoder,
                    onload_device=onload_device,
                    offload_device=offload_device,
                    offload_type="block_level",
                    num_blocks_per_group=2,
                    use_stream=True,
                )
                applied_group_offload = True
            if hasattr(pipe, "vae"):
                apply_group_offloading(
                    pipe.vae,
                    onload_device=onload_device,
                    offload_device=offload_device,
                    offload_type="leaf_level",
                    use_stream=True,
                )
                applied_group_offload = True
        except Exception:
            applied_group_offload = False

        if not applied_group_offload:
            pipe.enable_model_cpu_offload()
        return pipe, "cpu"
    pipe = pipe.to(device)
    return pipe, device


def seed_for_shot(base_seed: int, slide_index: int, shot_index: int) -> int:
    return base_seed + (slide_index * 100) + shot_index


def render_selected_shots(manifest_path: Path, manifest: dict, selected_slides: set[int] | None,
                          force: bool, device_override: str | None,
                          dtype_override: str | None, cpu_offload_override: bool) -> None:
    animation = manifest.get("animation", {})
    if animation.get("provider") != "local":
        raise SystemExit("❌  render_job.py only supports manifests with animation.provider=local")
    if animation.get("backend") != "ltx-diffusers":
        raise SystemExit("❌  render_job.py currently supports only animation.backend=ltx-diffusers")

    worker_args = dict(animation.get("worker_args", {}))
    model_name = str(animation.get("model", "Lightricks/LTX-Video"))
    dtype_name = dtype_override or str(worker_args.get("dtype", "bfloat16"))
    device_name = device_override or str(worker_args.get("device", "cuda"))
    cpu_offload = cpu_offload_override or bool(worker_args.get("cpu_offload", False))
    fps = int(worker_args.get("fps", manifest.get("animation", {}).get("merged_defaults", {}).get("frames_per_second", 24)))
    width = int(worker_args.get("width", 704))
    height = int(worker_args.get("height", 480))
    steps = int(worker_args.get("steps", 8))
    guidance_scale = float(worker_args.get("guidance_scale", 1.0))
    negative_prompt = worker_args.get("negative_prompt") or None
    base_seed = int(worker_args.get("seed", 42))

    pipe, generator_device = load_ltx_pipeline(model_name, dtype_name, device_name, cpu_offload)

    try:
        import torch
        from diffusers.utils import export_to_video, load_image
    except ImportError as exc:
        raise SystemExit(
            "❌  Missing self-hosted video dependencies. Install requirements-selfhosted.txt and a GPU torch build first."
        ) from exc

    generated = 0
    skipped = 0
    blocked = 0

    for slide, shot in selected_shots(manifest, selected_slides):
        slide_index = int(slide.get("slide_index", 0))
        shot_index = int(shot.get("shot_index", 0))
        shot_tag = str(shot.get("shot_tag", f"slide{slide_index:02d}_shot{shot_index:02d}"))
        source_path = resolve_repo_path(shot["source_image"]["path"])
        clip_path = resolve_repo_path(shot["clip"]["path"])

        shot["source_image"]["status"] = "ready" if source_path.exists() else "missing"
        if not source_path.exists():
            shot["clip"]["status"] = "blocked"
            shot["clip"]["last_error"] = "missing source image"
            blocked += 1
            print(f"[skip] {shot_tag} missing source image: {repo_relative(source_path)}")
            save_manifest(manifest_path, manifest)
            continue

        if clip_path.exists() and not force:
            shot["clip"]["status"] = "ready"
            shot["clip"].pop("last_error", None)
            skipped += 1
            print(f"[cached] {repo_relative(clip_path)}")
            save_manifest(manifest_path, manifest)
            continue

        duration = int(shot.get("duration_seconds", worker_args.get("seconds", 4)))
        num_frames = max(9, int(duration * fps) + 1)
        generator = torch.Generator(generator_device).manual_seed(seed_for_shot(base_seed, slide_index, shot_index))
        clip_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"[gen] {shot_tag} -> {repo_relative(clip_path)}")
        result = pipe(
            image=load_image(source_path),
            prompt=shot.get("video_prompt", shot.get("motion_prompt", "")),
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_frames=num_frames,
            frame_rate=fps,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        export_to_video(result.frames[0], str(clip_path), fps=fps)

        shot["clip"]["status"] = "ready"
        shot["clip"]["generated_at"] = now_iso()
        shot["clip"].pop("last_error", None)
        generated += 1
        save_manifest(manifest_path, manifest)

    refresh_manifest_state(manifest)
    manifest.setdefault("plan", {}).setdefault("status", {})["clips"] = "complete" if manifest["summary"]["missing_clips"] == 0 else "pending"
    manifest.setdefault("run_history", []).append({
        "stage": "render_job",
        "finished_at": now_iso(),
        "generated": generated,
        "cached": skipped,
        "blocked": blocked,
        "selected_slides": sorted(selected_slides) if selected_slides else "all",
    })
    save_manifest(manifest_path, manifest)

    print(f"[done] generated={generated} cached={skipped} blocked={blocked}")
    print(f"[done] clips ready: {manifest['summary']['existing_clips']}/{manifest['summary']['total_shots']}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    manifest_path = Path(args.job).resolve()
    if not manifest_path.exists():
        raise SystemExit(f"❌  Job manifest not found: {manifest_path}")

    manifest = load_manifest(manifest_path)
    selected_slides = parse_slide_selection(args.slides, int(manifest.get("story", {}).get("slide_count", 0) or len(manifest.get("slides", []))))
    refresh_manifest_state(manifest)
    manifest.setdefault("plan", {}).setdefault("status", {})["planner"] = "complete"

    if args.status_only:
        manifest.setdefault("run_history", []).append({
            "stage": "render_job_status_only",
            "finished_at": now_iso(),
            "selected_slides": sorted(selected_slides) if selected_slides else "all",
        })
        save_manifest(manifest_path, manifest)
        print(f"[status] source images ready: {manifest['summary']['existing_source_images']}/{manifest['summary']['total_shots']}")
        print(f"[status] clips ready: {manifest['summary']['existing_clips']}/{manifest['summary']['total_shots']}")
        return

    render_selected_shots(
        manifest_path,
        manifest,
        selected_slides,
        force=args.force,
        device_override=args.device,
        dtype_override=args.dtype,
        cpu_offload_override=args.cpu_offload,
    )


if __name__ == "__main__":
    main()