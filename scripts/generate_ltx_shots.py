#!/usr/bin/env python3
"""Generate short local LTX image-to-video clips that match generate_story.py naming."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate self-hosted LTX shot clips for a story YAML")
    parser.add_argument("story", help="Path to story YAML file")
    parser.add_argument("--image-dir", help="Directory with source stills, default: output/<story-id>/")
    parser.add_argument("--output-dir", required=True, help="Directory to write slide01_shot01.mp4 style clips")
    parser.add_argument("--model", default="Lightricks/LTX-Video", help="Diffusers model id")
    parser.add_argument("--device", default="cuda", help="Torch device, usually cuda")
    parser.add_argument("--dtype", choices=["bfloat16", "float16", "float32"], default="bfloat16")
    parser.add_argument("--width", type=int, default=704, help="Output width")
    parser.add_argument("--height", type=int, default=480, help="Output height")
    parser.add_argument("--fps", type=int, default=24, help="Output fps")
    parser.add_argument("--seconds", type=int, default=4, help="Clip length per slide in seconds")
    parser.add_argument("--steps", type=int, default=8, help="Denoising steps; keep low for budget runs")
    parser.add_argument("--guidance-scale", type=float, default=1.0, help="Use 1.0 for distilled LTX checkpoints")
    parser.add_argument("--negative-prompt", default="worst quality, blurry, jittery, distorted, flicker", help="Optional negative prompt")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    parser.add_argument("--start-slide", type=int, default=1, help="1-based inclusive")
    parser.add_argument("--end-slide", type=int, help="1-based inclusive; default is last slide")
    parser.add_argument("--cpu-offload", action="store_true", help="Enable model CPU offload if VRAM is tight")
    parser.add_argument("--force", action="store_true", help="Regenerate existing clips")
    return parser


def parse_torch_dtype(name: str):
    import torch

    mapping = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    return mapping[name]


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        import torch
        from diffusers import LTXImageToVideoPipeline
        from diffusers.utils import export_to_video, load_image
    except ImportError as exc:
        raise SystemExit(
            "❌  Missing self-hosted video dependencies. Install requirements-selfhosted.txt and a GPU torch build first."
        ) from exc

    from generate_story import ROOT, animated_defaults_for_story, load_story, resolve_slide_shots, story_slide_records, video_prompt_for_shot

    story = load_story(args.story, "en")
    slide_records = story_slide_records(story, "en")
    defaults = animated_defaults_for_story(story)
    story_id = story.STORY_ID

    image_dir = Path(args.image_dir).expanduser().resolve() if args.image_dir else (ROOT / "output" / story_id)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dtype = parse_torch_dtype(args.dtype)
    pipe = LTXImageToVideoPipeline.from_pretrained(args.model, torch_dtype=dtype)
    if args.cpu_offload:
        pipe.enable_model_cpu_offload()
        generator_device = "cpu"
    else:
        pipe = pipe.to(args.device)
        generator_device = args.device

    start_slide = max(1, args.start_slide)
    end_slide = args.end_slide or len(slide_records)
    end_slide = min(end_slide, len(slide_records))

    for slide_num in range(start_slide, end_slide + 1):
        slide = slide_records[slide_num - 1]
        shots = resolve_slide_shots(story, slide_records, slide_num - 1)
        for shot_idx, shot in enumerate(shots, 1):
            shot_tag = f"slide{slide_num:02d}_shot{shot_idx:02d}"
            image_path = image_dir / f"{shot_tag}_raw.jpg"
            output_path = output_dir / f"{shot_tag}.mp4"

            if output_path.exists() and not args.force:
                print(f"[cached] {output_path.name}")
                continue
            if not image_path.exists():
                raise SystemExit(f"❌  Missing source still: {image_path}")

            duration = int(shot.get("duration", args.seconds or defaults.get("shot_duration_seconds", 4)))
            num_frames = max(9, int(duration * args.fps) + 1)
            prompt = video_prompt_for_shot(shot, slide.get("dall_e_prompt", ""), defaults)
            image = load_image(image_path)
            seed = args.seed + (slide_num * 100) + shot_idx
            generator = torch.Generator(generator_device).manual_seed(seed)

            print(f"[gen] {output_path.name} from {image_path.name}")
            result = pipe(
                image=image,
                prompt=prompt,
                negative_prompt=args.negative_prompt or None,
                width=args.width,
                height=args.height,
                num_frames=num_frames,
                frame_rate=args.fps,
                num_inference_steps=args.steps,
                guidance_scale=args.guidance_scale,
                generator=generator,
            )
            export_to_video(result.frames[0], str(output_path), fps=args.fps)
            print(f"[ok]  {output_path}")


if __name__ == "__main__":
    main()