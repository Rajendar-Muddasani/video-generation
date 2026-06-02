#!/usr/bin/env python3
"""
generate_story.py — Story video engine
Generates a YouTube-ready MP4 from any story data file.

Usage:
    python generate_story.py stories/clever_crow.py
    python generate_story.py stories/clever_crow.py --force
    python generate_story.py stories/clever_crow.py --lang te
    python generate_story.py stories/story.yaml --video-mode animated

Each story file must export or provide:
    STORY_ID / story_id
    STORY_TITLE / story_title
    SLIDES / slides_en (+ optional slides_te)
    VOICE_EN / voice_en
    VOICE_TE / voice_te
    ART_STYLE / art_style
"""

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml

from dotenv import load_dotenv

# ── Environment ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_CREDS   = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
FAL_KEY        = os.environ.get("FAL_KEY", "")

DEFAULT_FAL_MODEL = "fal-ai/wan-25-preview/text-to-video"
DEFAULT_FAL_COST_PER_SECOND = 0.05
DEFAULT_FAL_MAX_COST_USD = 3.0
DEFAULT_FAL_NEGATIVE_PROMPT = (
    "blur, distort, low quality, flicker, jitter, warped anatomy, extra limbs, "
    "text, watermark"
)

if GOOGLE_CREDS:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDS

FONT_BOLD    = str(ROOT / "fonts/NotoSansTelugu-Bold.ttf")
FONT_REGULAR = str(ROOT / "fonts/NotoSansTelugu-Regular.ttf")


# ── Load story — supports .py modules and .yaml files ────────────────────────
def _slide_records_from_list(lst: list | None) -> list[dict]:
    records: list[dict] = []
    for slide in (lst or []):
        records.append({
            "eyebrow": slide.get("eyebrow", ""),
            "title": slide.get("title", ""),
            "dall_e_prompt": slide.get("dall_e_prompt", ""),
            "narration": slide.get("narration", ""),
            "shots": slide.get("shots", []),
        })
    return records


def _slide_records_from_shared_list(lst: list | None, lang: str) -> list[dict]:
    records: list[dict] = []
    title_key = f"title_{lang}"
    narration_key = f"narration_{lang}"
    for slide in (lst or []):
        records.append({
            "eyebrow": slide.get("eyebrow", ""),
            "title": slide.get(title_key, slide.get("title", "")),
            "dall_e_prompt": slide.get("dall_e_prompt", ""),
            "narration": slide.get(narration_key, slide.get("narration", "")),
            "shots": slide.get("shots", []),
        })
    return records


def _slides_from_records(lst: list[dict]) -> list:
    return [
        (s.get("eyebrow", ""), s.get("title", ""),
         s.get("dall_e_prompt", ""), s.get("narration", ""))
        for s in lst
    ]


def _format_youtube_meta(meta: dict, lang: str) -> str:
    key = f"youtube_{lang}"
    m   = meta.get(key, meta.get("youtube_en", {}))
    if not m:
        return ""
    tags = ", ".join(m.get("tags", []))
    return (
        f"Title      : {m.get('title', '')}\n"
        f"Description: {m.get('description', '')}\n"
        f"Tags       : {tags}\n"
    )


def load_story(path: str, lang: str = "en"):
    p = Path(path).resolve()
    if p.suffix in (".yaml", ".yml"):
        with open(p, encoding="utf-8") as f:
            d = yaml.safe_load(f)

        shared_slides = d.get("slides", [])
        slides_en_raw = (
            _slide_records_from_shared_list(shared_slides, "en")
            if shared_slides else
            _slide_records_from_list(d.get("slides_en", []))
        )
        slides_te_raw = (
            _slide_records_from_shared_list(shared_slides, "te")
            if shared_slides else
            _slide_records_from_list(d.get("slides_te", []))
        )

        ns = SimpleNamespace()
        ns.STORY_ID    = d["story_id"]
        ns.STORY_TITLE = d["story_title"]
        ns.ART_STYLE   = d.get("art_style", "")
        ns.CHANNEL_EN  = d.get("channel_en", "Mitra AI Stories")
        ns.CHANNEL_TE  = d.get("channel_te", "మిత్ర AI కథలు")
        ns.VOICE_EN    = d.get("voice_en", {})
        ns.VOICE_TE    = d.get("voice_te", {})
        ns.SHARED_SLIDES = shared_slides
        ns.SLIDES_EN_RAW = slides_en_raw
        ns.SLIDES_TE_RAW = slides_te_raw
        ns.SLIDES      = _slides_from_records(slides_en_raw)
        ns.SLIDES_TE   = _slides_from_records(slides_te_raw)
        ns.ANIMATED_DEFAULTS = d.get("animated_defaults", {})
        ns._yaml_meta  = d
        ns._is_yaml    = True
        return ns

    spec = importlib.util.spec_from_file_location("story", p)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._is_yaml = False
    return mod


def story_slide_records(story, lang: str) -> list[dict]:
    if getattr(story, "_is_yaml", False):
        if lang == "te" and getattr(story, "SLIDES_TE_RAW", None):
            return story.SLIDES_TE_RAW
        return story.SLIDES_EN_RAW

    if lang == "te" and hasattr(story, "SLIDES_TE"):
        slides = story.SLIDES_TE
    else:
        slides = story.SLIDES
    return [
        {
            "eyebrow": eyebrow,
            "title": title,
            "dall_e_prompt": scene_prompt,
            "narration": narration,
            "shots": [],
        }
        for eyebrow, title, scene_prompt, narration in slides
    ]


def infer_fal_model_input(model: str) -> str:
    model_lower = model.lower()
    if "text-to-video" in model_lower:
        return "text"
    return "image"


def default_fal_cost_per_second(model: str) -> float | None:
    model_lower = model.lower()
    if "wan-i2v" in model_lower or "wan-flf2v" in model_lower:
        return None
    if "kling-video/v2.1/master" in model_lower:
        return 0.28
    if "wan-25-preview" in model_lower:
        return 0.05
    return DEFAULT_FAL_COST_PER_SECOND


def default_fal_cost_per_video(model: str, resolution: str) -> float | None:
    model_lower = model.lower()
    if "wan-i2v" in model_lower or "wan-flf2v" in model_lower:
        return 0.40 if str(resolution).lower() == "720p" else 0.20
    return None


def bool_default(value, fallback: bool) -> bool:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def safe_cache_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "animation"


def dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def find_external_asset(source_dir: Path | None, candidate_names: list[str]) -> Path | None:
    if source_dir is None:
        return None
    for name in candidate_names:
        candidate = source_dir / name
        if candidate.exists():
            return candidate
    return None


def animation_cache_tag(defaults: dict) -> str:
    model_tag = safe_cache_part(defaults.get("model", DEFAULT_FAL_MODEL))
    if model_tag.startswith("fal-ai-"):
        model_tag = model_tag[len("fal-ai-"):]
    model_tag = model_tag[:56].strip("-")
    input_tag = safe_cache_part(defaults.get("model_input", infer_fal_model_input(defaults.get("model", DEFAULT_FAL_MODEL))))
    resolution = safe_cache_part(str(defaults.get("resolution", "auto")))
    duration = int(defaults.get("shot_duration_seconds", 5))
    return f"{model_tag}_{input_tag}_{resolution}_{duration}s"


def animation_output_tag(defaults: dict) -> str:
    tag = f"{animation_cache_tag(defaults)}_{int(defaults.get('shots_per_slide', 1))}shots"
    strategy = safe_cache_part(str(defaults.get("segment_strategy", "")))
    if strategy in {"hybrid-hold", "hybrid-legacy-hold"}:
        return f"{tag}_{strategy}"
    return tag


def source_image_candidate_names(out_path: Path) -> list[str]:
    names = [out_path.name]
    if out_path.name.endswith("_shot01_raw.jpg"):
        names.append(out_path.name.replace("_shot01_raw.jpg", "_raw.jpg"))
    return dedupe_preserving_order(names)


def shot_video_candidate_names(out_path: Path, shot_tag: str, cache_tag: str) -> list[str]:
    return dedupe_preserving_order([
        out_path.name,
        f"{shot_tag}.mp4",
        f"{shot_tag}_{cache_tag}_anim.mp4",
    ])


def trim_prompt(prompt: str, max_chars: int) -> str:
    compact = " ".join((prompt or "").split())
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[:max_chars - 3].rsplit(" ", 1)[0]
    return f"{trimmed}..."


def video_prompt_for_shot(shot: dict, scene_prompt: str, defaults: dict) -> str:
    motion_prompt = shot.get("motion_prompt", "gentle cinematic motion, calm bedtime pacing")
    if defaults.get("model_input") == "text":
        image_prompt = shot.get("image_prompt") or scene_prompt
        return trim_prompt(f"{image_prompt}. Motion: {motion_prompt}", int(defaults.get("max_prompt_chars", 760)))
    return trim_prompt(motion_prompt, int(defaults.get("max_prompt_chars", 500)))


def fal_arguments_for_model(model: str, prompt: str, image_url: str | None,
                            duration: int, negative_prompt: str,
                            defaults: dict) -> dict:
    model_lower = model.lower()
    arguments = {"prompt": prompt}
    if image_url:
        arguments["image_url"] = image_url
    if negative_prompt:
        arguments["negative_prompt"] = negative_prompt

    if "kling-video" in model_lower:
        arguments["duration"] = str(duration)
        arguments["cfg_scale"] = float(defaults.get("cfg_scale", 0.5))
        return arguments

    if "wan-25-preview" in model_lower and "text-to-video" in model_lower:
        if duration not in (5, 10):
            raise SystemExit("❌  Wan 2.5 text-to-video only supports 5s or 10s clips.")
        arguments.update({
            "aspect_ratio": defaults.get("aspect_ratio", "16:9"),
            "resolution": defaults.get("resolution", "480p"),
            "duration": str(duration),
            "enable_prompt_expansion": bool_default(defaults.get("enable_prompt_expansion"), True),
            "enable_safety_checker": bool_default(defaults.get("enable_safety_checker"), True),
        })
        return arguments

    if "wan-i2v" in model_lower:
        fps = int(defaults.get("frames_per_second", 16))
        arguments.pop("negative_prompt", None)
        arguments.update({
            "num_frames": max(81, min(100, int(duration * fps) + 1)),
            "frames_per_second": fps,
            "resolution": defaults.get("resolution", "720p"),
            "aspect_ratio": defaults.get("aspect_ratio", "16:9"),
            "enable_safety_checker": bool_default(defaults.get("enable_safety_checker"), True),
        })
        return arguments

    if "wan/v2.7" in model_lower:
        arguments.update({
            "resolution": defaults.get("resolution", "720p"),
            "duration": int(duration),
            "enable_prompt_expansion": bool_default(defaults.get("enable_prompt_expansion"), True),
            "enable_safety_checker": bool_default(defaults.get("enable_safety_checker"), True),
        })
        return arguments

    if "wan/" in model_lower:
        fps = int(defaults.get("frames_per_second", 16))
        arguments.update({
            "num_frames": max(17, min(161, int(duration * fps) + 1)),
            "frames_per_second": fps,
            "resolution": defaults.get("resolution", "720p"),
            "aspect_ratio": defaults.get("aspect_ratio", "auto"),
            "enable_prompt_expansion": bool_default(defaults.get("enable_prompt_expansion"), False),
            "enable_safety_checker": bool_default(defaults.get("enable_safety_checker"), True),
            "enable_output_safety_checker": bool_default(defaults.get("enable_output_safety_checker"), False),
        })
        return arguments

    arguments["duration"] = str(duration)
    return arguments


def animated_defaults_for_story(story) -> dict:
    story_defaults = getattr(story, "ANIMATED_DEFAULTS", {}) or {}
    defaults = {
        "provider": "fal",
        "model": DEFAULT_FAL_MODEL,
        "shot_duration_seconds": 5,
        "shots_per_slide": 1,
        "negative_prompt": DEFAULT_FAL_NEGATIVE_PROMPT,
        "cfg_scale": 0.5,
        "aspect_ratio": "16:9",
        "resolution": "480p",
        "enable_prompt_expansion": True,
        "enable_safety_checker": True,
        "max_estimated_cost_usd": DEFAULT_FAL_MAX_COST_USD,
    }
    defaults.update(story_defaults)
    defaults["provider"] = str(defaults.get("provider", "fal")).lower()
    if defaults["provider"] == "local" and "model" not in story_defaults:
        defaults["model"] = "local-short-clip"

    model = str(defaults.get("model", DEFAULT_FAL_MODEL))
    if "model_input" not in story_defaults:
        defaults["model_input"] = infer_fal_model_input(model)
    if defaults["provider"] == "local":
        if "estimated_cost_per_second" not in story_defaults:
            defaults["estimated_cost_per_second"] = None
        if "estimated_cost_per_video" not in story_defaults:
            defaults["estimated_cost_per_video"] = 0.0
    else:
        if "estimated_cost_per_second" not in story_defaults:
            defaults["estimated_cost_per_second"] = default_fal_cost_per_second(model)
        if "estimated_cost_per_video" not in story_defaults:
            defaults["estimated_cost_per_video"] = default_fal_cost_per_video(model, defaults.get("resolution", "480p"))

    shot_duration = max(1, int(defaults.get("shot_duration_seconds", 5)))
    if "wan-25-preview" in model.lower() and shot_duration not in (5, 10):
        shot_duration = 5
    defaults["shot_duration_seconds"] = shot_duration
    defaults["shots_per_slide"] = max(1, int(defaults.get("shots_per_slide", 1)))
    defaults["cfg_scale"] = float(defaults.get("cfg_scale", 0.5))
    if defaults.get("estimated_cost_per_second") is not None:
        defaults["estimated_cost_per_second"] = float(defaults["estimated_cost_per_second"])
    if defaults.get("estimated_cost_per_video") is not None:
        defaults["estimated_cost_per_video"] = float(defaults["estimated_cost_per_video"])
    if defaults.get("max_estimated_cost_usd") is not None:
        defaults["max_estimated_cost_usd"] = float(defaults["max_estimated_cost_usd"])
    return defaults


def default_shots_for_slide(slide: dict, shot_count: int, shot_duration: int) -> list[dict]:
    scene_prompt = slide.get("dall_e_prompt", "")
    templates = [
        (
            "wide establishing composition, cinematic depth, layered foreground and background",
            "gentle cinematic push-in, subtle cloud drift, soft environmental motion, calm bedtime pacing",
        ),
        (
            "medium storytelling composition focused on the main subject, clear subject separation",
            "slow side-to-side camera drift, delicate parallax, soft organic movement, calm bedtime pacing",
        ),
        (
            "close emotional detail composition, expressive focus on the main subject, dreamy depth of field",
            "slow intimate push-in, subtle breathing or twinkling motion, no sudden movement, calm bedtime pacing",
        ),
        (
            "final poetic composition, luminous atmosphere, gentle visual closure",
            "very slow floating camera move, delicate shimmering light, restful ending motion",
        ),
    ]

    shots: list[dict] = []
    for idx in range(shot_count):
        image_suffix, motion_prompt = templates[min(idx, len(templates) - 1)]
        shots.append({
            "image_prompt": f"{scene_prompt}, {image_suffix}",
            "motion_prompt": motion_prompt,
            "duration": shot_duration,
        })
    return shots


def resolve_slide_shots(story, slide_records: list[dict], slide_index: int,
                        defaults: dict | None = None) -> list[dict]:
    defaults = defaults or animated_defaults_for_story(story)

    if slide_index < len(getattr(story, "SHARED_SLIDES", [])):
        shared = story.SHARED_SLIDES[slide_index]
        if shared.get("shots"):
            return shared["shots"]

    if slide_index < len(getattr(story, "SLIDES_EN_RAW", [])):
        en_slide = story.SLIDES_EN_RAW[slide_index]
        if en_slide.get("shots"):
            return en_slide["shots"]

    slide = slide_records[slide_index]
    if slide.get("shots"):
        return slide["shots"]

    return default_shots_for_slide(
        slide,
        defaults["shots_per_slide"],
        defaults["shot_duration_seconds"],
    )


def estimate_animated_workload(story, slide_records: list[dict], out_dir: Path,
                               force: bool, local_shot_dir: Path | None = None,
                               defaults_override: dict | None = None) -> dict:
    defaults = defaults_override or animated_defaults_for_story(story)
    provider = str(defaults.get("provider", "fal")).lower()
    cache_tag = animation_cache_tag(defaults)
    total_shots = 0
    total_output_seconds = 0
    billable_shots = 0
    billable_output_seconds = 0

    for slide_index in range(len(slide_records)):
        tag = f"slide{slide_index + 1:02d}"
        shots = resolve_slide_shots(story, slide_records, slide_index, defaults)
        for shot_idx, shot in enumerate(shots, 1):
            duration = int(shot.get("duration", defaults["shot_duration_seconds"]))
            shot_vid = out_dir / f"{tag}_shot{shot_idx:02d}_{cache_tag}_anim.mp4"
            total_shots += 1
            total_output_seconds += duration
            available = shot_vid.exists()
            if provider == "local" and not available:
                shot_tag = f"{tag}_shot{shot_idx:02d}"
                available = find_external_asset(
                    local_shot_dir,
                    shot_video_candidate_names(shot_vid, shot_tag, cache_tag),
                ) is not None
            if force or not available:
                billable_shots += 1
                billable_output_seconds += duration

    return {
        "total_shots": total_shots,
        "total_output_seconds": total_output_seconds,
        "billable_shots": billable_shots,
        "billable_output_seconds": billable_output_seconds,
    }


def estimated_animated_cost_usd(workload: dict, defaults: dict) -> float | None:
    flat_rate = defaults.get("estimated_cost_per_video")
    if flat_rate is not None:
        return workload["billable_shots"] * float(flat_rate)
    rate = defaults.get("estimated_cost_per_second")
    if rate is None:
        return None
    return workload["billable_output_seconds"] * float(rate)


def enforce_animated_budget(workload: dict, defaults: dict) -> None:
    estimated_cost = estimated_animated_cost_usd(workload, defaults)
    max_cost = defaults.get("max_estimated_cost_usd")
    if max_cost is not None and estimated_cost is None:
        raise SystemExit("❌  Animated budget cap is set, but no estimated animation cost rate is configured.")
    if max_cost is not None and estimated_cost is not None and estimated_cost > float(max_cost):
        raise SystemExit(
            "❌  Estimated animation cost "
            f"${estimated_cost:.2f} exceeds budget cap ${float(max_cost):.2f}. "
            "Lower shots_per_slide, shot_duration_seconds, or raise max_estimated_cost_usd intentionally."
        )


# ── gpt-image-1 image generation ─────────────────────────────────────────────
def generate_image(art_style: str, scene_prompt: str,
                   out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        print(f"  [img] cached  {out_path.name}")
        return
    ensure_openai_ready()
    import base64
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    print(f"  [img] generating  {out_path.name} …")
    resp = client.images.generate(
        model="gpt-image-1",
        prompt=art_style + scene_prompt,
        size="1536x1024",
        quality="medium",
        n=1,
    )
    image_bytes = base64.b64decode(resp.data[0].b64_json)
    out_path.write_bytes(image_bytes)
    print(f"         ✓ saved")


def generate_fal_image(art_style: str, scene_prompt: str,
                       out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        print(f"  [img] cached  {out_path.name}")
        return
    import fal_client

    ensure_fal_ready()
    prompt = (
        f"{art_style}. {scene_prompt}. Cute realistic animated animal characters, "
        "soft expressive eyes, believable fur, gentle premium children's animation still, "
        "cinematic bedtime lighting, detailed forest background, no text, no letters, no watermark."
    )
    moonless_text = f"{art_style} {scene_prompt}".lower()
    if "moonless" in moonless_text or "no visible moon" in moonless_text or "new moon" in moonless_text:
        prompt += " Moonless night: do not include any moon, full moon, crescent moon, planet, or bright round object in the sky."
    print(f"  [img] fal generating  {out_path.name} …")
    try:
        handle = fal_client.submit(
            "fal-ai/flux/schnell",
            arguments={
                "prompt": prompt,
                "image_size": "landscape_16_9",
                "num_inference_steps": 4,
                "guidance_scale": 3.5,
                "num_images": 1,
                "enable_safety_checker": True,
                "output_format": "jpeg",
            },
        )
        print(f"       [fal-img] request {handle.request_id} submitted")
        for update in handle.iter_events(with_logs=True, interval=2.0):
            logs = getattr(update, "logs", None) or []
            if logs:
                last = logs[-1]
                message = getattr(last, "message", None)
                if message is None and isinstance(last, dict):
                    message = last.get("message")
                if message:
                    print(f"       [fal-img] {message}")
        result = handle.get()
    except httpx.HTTPStatusError as exc:
        raise_fal_failure("Fal image generation", exc)
    except Exception as exc:
        raise_fal_failure("Fal image generation", exc)

    image_url = result["images"][0]["url"]
    urllib.request.urlretrieve(image_url, out_path)
    print(f"  [img] ✓  {out_path.name}")


def import_existing_image(out_path: Path, existing_image_dir: Path | None,
                          force: bool) -> None:
    if out_path.exists() and not force:
        print(f"  [img] cached  {out_path.name}")
        return
    if existing_image_dir is None:
        raise SystemExit(
            "❌  image-provider=existing requires --selfhosted-image-dir with pre-generated slide stills."
        )

    for candidate_name in source_image_candidate_names(out_path):
        candidate = existing_image_dir / candidate_name
        if candidate.exists():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if candidate.resolve() != out_path.resolve():
                shutil.copy2(candidate, out_path)
            print(f"  [img] imported  {candidate.name}")
            return

    expected = ", ".join(source_image_candidate_names(out_path))
    raise SystemExit(
        "❌  Missing self-hosted source image. Looked for "
        f"{expected} in {existing_image_dir}."
    )


def generate_source_image(art_style: str, scene_prompt: str, out_path: Path,
                          force: bool, provider: str, slide_index: int,
                          existing_image_dir: Path | None = None) -> None:
    if provider == "fal":
        generate_fal_image(art_style, scene_prompt, out_path, force)
    elif provider == "existing":
        import_existing_image(out_path, existing_image_dir, force)
    elif provider == "offline":
        create_offline_storybook_image(scene_prompt, out_path, slide_index)
    else:
        generate_image(art_style, scene_prompt, out_path, force)


# ── PIL text overlay ──────────────────────────────────────────────────────────
def _load_overlay_fonts():
    from PIL import ImageFont

    try:
        f_sm    = ImageFont.truetype(FONT_REGULAR, 28)
        f_eye   = ImageFont.truetype(FONT_REGULAR, 34)
        f_title = ImageFont.truetype(FONT_BOLD,    68)
    except Exception:
        f_sm = f_eye = f_title = ImageFont.load_default()
    return f_sm, f_eye, f_title


def build_text_overlay_layer(title: str, eyebrow: str, channel: str):
    from PIL import Image, ImageDraw

    W, H = 1920, 1080
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)

    bar = Image.new("RGBA", (W, 230), (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    for y in range(230):
        bd.line([(0, y), (W, y)], fill=(0, 0, 0, int(185 * y / 230)))
    layer.paste(bar, (0, H - 230), bar)

    f_sm, f_eye, f_title = _load_overlay_fonts()

    d.text((W - 28, 28), channel,
           fill=(255, 255, 255, 200), font=f_sm, anchor="ra")

    if eyebrow:
        d.text((48, H - 210), eyebrow.upper(), fill=(245, 158, 11), font=f_eye)

    words, lines, cur = title.split(), [], ""
    for word in words:
        test = f"{cur} {word}".strip()
        if d.textbbox((0, 0), test, font=f_title)[2] < W - 120:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)

    y = H - 155
    for line in lines:
        bb = d.textbbox((0, 0), line, font=f_title)
        x  = (W - (bb[2] - bb[0])) / 2
        d.text((x + 2, y + 2), line, fill=(0, 0, 0, 220), font=f_title)
        d.text((x,     y),     line, fill=(255, 255, 255), font=f_title)
        y += int(f_title.size * 1.2)

    return layer


def create_text_overlay_layer(title: str, eyebrow: str,
                              channel: str, out_path: Path) -> None:
    layer = build_text_overlay_layer(title, eyebrow, channel)
    layer.save(out_path, "PNG")


def add_text_overlay(raw_img: Path, title: str, eyebrow: str,
                     channel: str, out_path: Path) -> None:
    from PIL import Image

    img = Image.open(raw_img).convert("RGBA").resize((1920, 1080), Image.LANCZOS)
    out_img = Image.alpha_composite(img, build_text_overlay_layer(title, eyebrow, channel)).convert("RGB")
    out_img.save(out_path, "JPEG", quality=95)


def create_offline_storybook_image(scene_prompt: str, out_path: Path, slide_index: int) -> None:
    from PIL import Image, ImageDraw, ImageFilter

    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), (12, 24, 48))
    draw = ImageDraw.Draw(img, "RGBA")

    for y in range(height):
        t = y / height
        r = int(8 + 14 * t)
        g = int(20 + 28 * t)
        b = int(46 + 22 * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    for idx in range(9):
        x = -90 + idx * 260 + (slide_index % 3) * 35
        top = 190 + (idx % 3) * 35
        trunk = (42, 52, 42, 220)
        leaves = (18, 60, 56, 180)
        draw.polygon([(x + 65, height), (x + 115, top), (x + 170, height)], fill=trunk)
        draw.ellipse((x - 40, top - 70, x + 260, top + 210), fill=leaves)
        draw.ellipse((x - 85, top + 35, x + 220, top + 330), fill=(13, 50, 52, 145))

    draw.rectangle((0, 760, width, height), fill=(19, 57, 48, 230))
    for idx in range(24):
        x = (idx * 91 + slide_index * 47) % width
        h = 48 + (idx % 5) * 30
        draw.polygon([(x, height), (x + 12, 850 - h), (x + 26, height)], fill=(45, 91, 63, 150))

    prompt = scene_prompt.lower()
    if "stream" in prompt or "water" in prompt:
        draw.polygon([(0, 900), (width, 830), (width, 990), (0, 1035)], fill=(56, 112, 132, 185))
        draw.line([(80, 942), (560, 910), (1180, 915), (1760, 875)], fill=(205, 235, 239, 90), width=5)
    if "burrow" in prompt or "home" in prompt or "mommy" in prompt or "mother" in prompt:
        draw.ellipse((1260, 720, 1600, 970), fill=(72, 54, 42, 235))
        draw.ellipse((1348, 780, 1520, 970), fill=(22, 22, 24, 245))
        for idx in range(5):
            x = 1190 + idx * 72
            draw.ellipse((x, 710 - idx % 2 * 18, x + 34, 750 - idx % 2 * 18), fill=(156, 52, 58, 210))
    if "banyan" in prompt or "owl" in prompt:
        draw.rectangle((210, 360, 315, height), fill=(67, 54, 44, 235))
        for x in (155, 245, 340):
            draw.line([(260, 410), (x, height)], fill=(67, 54, 44, 160), width=12)
        draw.ellipse((360, 380, 450, 470), fill=(105, 88, 70, 230))
        draw.ellipse((384, 410, 398, 424), fill=(250, 218, 110, 255))
        draw.ellipse((414, 410, 428, 424), fill=(250, 218, 110, 255))

    deer_x = 650 + (slide_index % 4) * 35
    deer_y = 675
    draw.ellipse((deer_x, deer_y, deer_x + 330, deer_y + 150), fill=(142, 103, 70, 255))
    draw.ellipse((deer_x + 270, deer_y - 70, deer_x + 395, deer_y + 55), fill=(154, 114, 78, 255))
    for x in (deer_x + 58, deer_x + 250):
        draw.rectangle((x, deer_y + 120, x + 28, deer_y + 315), fill=(94, 68, 50, 255))
    draw.polygon([(deer_x + 315, deer_y - 45), (deer_x + 350, deer_y - 145), (deer_x + 360, deer_y - 40)], fill=(126, 91, 62, 255))
    draw.polygon([(deer_x + 355, deer_y - 42), (deer_x + 408, deer_y - 120), (deer_x + 392, deer_y - 28)], fill=(126, 91, 62, 255))
    draw.line((deer_x + 322, deer_y - 62, deer_x + 285, deer_y - 138), fill=(102, 74, 50, 255), width=8)
    draw.line((deer_x + 365, deer_y - 58, deer_x + 420, deer_y - 132), fill=(102, 74, 50, 255), width=8)
    draw.ellipse((deer_x + 350, deer_y - 22, deer_x + 365, deer_y - 7), fill=(20, 18, 16, 255))

    rabbit_x = 500 + (slide_index % 3) * 42
    rabbit_y = 795
    draw.ellipse((rabbit_x, rabbit_y, rabbit_x + 138, rabbit_y + 96), fill=(228, 222, 211, 255))
    draw.ellipse((rabbit_x + 92, rabbit_y - 48, rabbit_x + 162, rabbit_y + 28), fill=(230, 224, 214, 255))
    draw.ellipse((rabbit_x + 102, rabbit_y - 125, rabbit_x + 130, rabbit_y - 25), fill=(230, 224, 214, 255))
    draw.ellipse((rabbit_x + 132, rabbit_y - 116, rabbit_x + 158, rabbit_y - 22), fill=(230, 224, 214, 255))
    draw.ellipse((rabbit_x + 140, rabbit_y - 14, rabbit_x + 151, rabbit_y - 3), fill=(20, 18, 16, 255))

    if "mother" in prompt or "mommy" in prompt:
        mx, my = 1480, 790
        draw.ellipse((mx, my, mx + 160, my + 110), fill=(214, 205, 190, 255))
        draw.ellipse((mx - 35, my - 48, mx + 58, my + 40), fill=(218, 209, 195, 255))
        draw.ellipse((mx - 20, my - 130, mx + 10, my - 35), fill=(218, 209, 195, 255))
        draw.ellipse((mx + 20, my - 128, mx + 50, my - 35), fill=(218, 209, 195, 255))

    for idx in range(36):
        x = 110 + ((idx * 157 + slide_index * 79) % 1700)
        y = 115 + ((idx * 83 + slide_index * 61) % 650)
        radius = 4 + (idx % 4)
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow, "RGBA")
        gd.ellipse((x - 26, y - 26, x + 26, y + 26), fill=(255, 190, 72, 34))
        gd.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 219, 112, 230))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    vd.rectangle((0, 0, width, 120), fill=(0, 0, 0, 55))
    vd.rectangle((0, 0, 90, height), fill=(0, 0, 0, 50))
    vd.rectangle((width - 90, 0, width, height), fill=(0, 0, 0, 50))
    img = Image.alpha_composite(img.convert("RGBA"), vignette).filter(ImageFilter.SMOOTH_MORE).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=95)
    print(f"  [img] offline  {out_path.name}")


# ── Google Cloud TTS ──────────────────────────────────────────────────────────
def tts_to_file(text: str, voice_cfg: dict, out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        print(f"  [tts] cached  {out_path.name}")
        return
    ensure_google_tts_ready()
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    for voice_name in [voice_cfg["name"], voice_cfg.get("fallback", "")]:
        if not voice_name:
            continue
        try:
            audio_config = {
                "audio_encoding": texttospeech.AudioEncoding.MP3,
                "speaking_rate": voice_cfg.get("speaking_rate", 0.87),
                "pitch": voice_cfg.get("pitch", -1.5),
            }
            resp = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=voice_cfg["language_code"],
                    name=voice_name,
                ),
                audio_config=texttospeech.AudioConfig(**audio_config),
            )
            out_path.write_bytes(resp.audio_content)
            print(f"  [tts] ✓  {out_path.name}  ({voice_name})")
            return
        except Exception as e:
            message = str(e)
            if "does not support pitch parameters" in message and "pitch" in audio_config:
                try:
                    audio_config.pop("pitch", None)
                    resp = client.synthesize_speech(
                        input=texttospeech.SynthesisInput(text=text),
                        voice=texttospeech.VoiceSelectionParams(
                            language_code=voice_cfg["language_code"],
                            name=voice_name,
                        ),
                        audio_config=texttospeech.AudioConfig(**audio_config),
                    )
                    out_path.write_bytes(resp.audio_content)
                    print(f"  [tts] ✓  {out_path.name}  ({voice_name}, no pitch)")
                    return
                except Exception as retry_error:
                    print(f"  [WARN] {voice_name}: {retry_error}")
                    continue
            print(f"  [WARN] {voice_name}: {e}")
    raise RuntimeError(f"All TTS voices failed for {out_path.name}")


# ── ffmpeg helpers ────────────────────────────────────────────────────────────
def audio_duration(p: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(p),
    ])
    return float(out.strip())


_LOCAL_H264_ARGS: list[str] | None = None


def local_h264_args() -> list[str]:
    global _LOCAL_H264_ARGS
    if _LOCAL_H264_ARGS is not None:
        return list(_LOCAL_H264_ARGS)

    try:
        encoders = subprocess.check_output(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        encoders = ""

    if "h264_videotoolbox" in encoders:
        _LOCAL_H264_ARGS = ["-c:v", "h264_videotoolbox", "-b:v", "6M", "-pix_fmt", "yuv420p", "-r", "30"]
    else:
        _LOCAL_H264_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", "30"]
    return list(_LOCAL_H264_ARGS)


def ensure_openai_ready() -> None:
    if not OPENAI_API_KEY:
        raise SystemExit("❌  OPENAI_API_KEY not set in .env or environment for OpenAI image generation")


def ensure_google_tts_ready() -> None:
    if not GOOGLE_CREDS:
        raise SystemExit("❌  GOOGLE_APPLICATION_CREDENTIALS not set in .env or environment for Google TTS")


def ensure_fal_ready() -> None:
    if not FAL_KEY:
        raise SystemExit("❌  FAL_KEY not set in .env or environment for animated mode")

    response = httpx.post(
        "https://rest.fal.ai/storage/auth/token?storage_type=fal-cdn-v3",
        headers={"Authorization": f"Key {FAL_KEY}"},
        json={},
        timeout=30,
    )
    if response.status_code < 400:
        return

    detail = response.text
    try:
        payload = response.json()
        detail = payload.get("detail", detail)
    except ValueError:
        pass

    if response.status_code == 403 and "Exhausted balance" in detail:
        raise SystemExit(
            "❌  Fal account is locked because the balance is exhausted. "
            "Top up billing at https://fal.ai/dashboard/billing, then rerun animated mode."
        )

    raise SystemExit(f"❌  Fal authentication failed ({response.status_code}): {detail}")


def fal_exception_detail(exc: Exception) -> tuple[int | None, str]:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    detail = str(exc)
    if response is not None:
        detail = getattr(response, "text", detail)
        try:
            payload = response.json()
            detail = payload.get("detail", detail)
        except ValueError:
            pass
    return status_code, detail


def raise_fal_failure(prefix: str, exc: Exception) -> None:
    status_code, detail = fal_exception_detail(exc)
    if "Exhausted balance" in detail or "User is locked" in detail:
        raise SystemExit(
            "❌  Fal account is locked because the balance is exhausted. "
            "Top up billing at https://fal.ai/dashboard/billing, then rerun animated mode."
        ) from exc
    status_text = f" ({status_code})" if status_code else ""
    raise SystemExit(f"❌  {prefix} failed{status_text}: {detail}") from exc


def load_job_manifest(path: str | None) -> dict | None:
    if not path:
        return None
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists():
        raise SystemExit(f"❌  Job manifest not found: {manifest_path}")
    with manifest_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"❌  Expected a YAML object in job manifest: {manifest_path}")
    return data


def import_local_shot(shot_tag: str, out_path: Path, defaults: dict,
                      selfhosted_shot_dir: Path | None, force: bool) -> None:
    if out_path.exists() and not force:
        print(f"     [mov] cached  {out_path.name}")
        return
    if selfhosted_shot_dir is None:
        raise SystemExit(
            "❌  animation-provider=local requires --selfhosted-shot-dir with pre-generated shot MP4s."
        )

    cache_tag = animation_cache_tag(defaults)
    for candidate_name in shot_video_candidate_names(out_path, shot_tag, cache_tag):
        candidate = selfhosted_shot_dir / candidate_name
        if candidate.exists():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if candidate.resolve() != out_path.resolve():
                shutil.copy2(candidate, out_path)
            print(f"     [mov] imported  {candidate.name}")
            return

    expected = ", ".join(shot_video_candidate_names(out_path, shot_tag, cache_tag))
    raise SystemExit(
        "❌  Missing self-hosted shot clip. Looked for "
        f"{expected} in {selfhosted_shot_dir}."
    )


def generate_animated_shot(raw_img: Path | None, video_prompt: str, out_path: Path,
                           defaults: dict, duration: int, negative_prompt: str,
                           force: bool, provider: str,
                           selfhosted_shot_dir: Path | None,
                           shot_tag: str) -> None:
    if provider == "local":
        import_local_shot(shot_tag, out_path, defaults, selfhosted_shot_dir, force)
        return
    if out_path.exists() and not force:
        print(f"     [mov] cached  {out_path.name}")
        return
    import fal_client

    model = defaults["model"]
    image_url = None
    print(f"     [mov] generating  {out_path.name} …")
    if defaults.get("model_input") == "image":
        if raw_img is None:
            raise SystemExit("❌  Image-to-video model requires a source image.")
        try:
            image_url = fal_client.upload_file(raw_img)
        except httpx.HTTPStatusError as exc:
            raise_fal_failure("Fal upload", exc)
        except Exception as exc:
            raise_fal_failure("Fal upload", exc)

    try:
        handle = fal_client.submit(
            model,
            arguments=fal_arguments_for_model(model, video_prompt, image_url, duration, negative_prompt, defaults),
        )
        print(f"       [fal] request {handle.request_id} submitted")

        last_state: tuple[str, str | None] | None = None
        last_log_message = None
        event_count = 0
        for update in handle.iter_events(with_logs=True, interval=5.0):
            event_count += 1
            printed_update = False
            state_name = type(update).__name__
            position = getattr(update, "position", None)
            state = (state_name, str(position) if position is not None else None)
            if state != last_state:
                if position is not None:
                    print(f"       [fal] {state_name.lower()} position={position}")
                else:
                    print(f"       [fal] {state_name.lower()}")
                last_state = state
                printed_update = True

            logs = getattr(update, "logs", None) or []
            if logs:
                last = logs[-1]
                message = getattr(last, "message", None)
                if message is None and isinstance(last, dict):
                    message = last.get("message")
                if message and message != last_log_message:
                    print(f"       [fal] {message}")
                    last_log_message = message
                    printed_update = True

            if not printed_update and event_count % 6 == 0:
                print(f"       [fal] waiting for request {handle.request_id} …")

            error = getattr(update, "error", None)
            if error:
                error_type = getattr(update, "error_type", None)
                raise SystemExit(
                    f"❌  Fal generation completed with an error"
                    f"{f' ({error_type})' if error_type else ''}: {error}"
                )

        result = handle.get()
    except httpx.HTTPStatusError as exc:
        raise_fal_failure("Fal generation", exc)
    except Exception as exc:
        raise_fal_failure("Fal generation", exc)
    video_url = result["video"]["url"]
    urllib.request.urlretrieve(video_url, out_path)
    print(f"     [mov] ✓  {out_path.name}")


def make_segment(img: Path, audio: Path, out: Path,
                 head_sil: float = 0.6, tail_sil: float = 2.2,
                 force: bool = False) -> None:
    if out.exists() and not force:
        print(f"  [seg] cached  {out.name}")
        return
    a_dur = audio_duration(audio)
    total = head_sil + a_dur + tail_sil
    n_frames = max(1, int(total * 30))
    zoom_rate = 0.08 / n_frames
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{total:.3f}", "-i", str(img),
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{head_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-f", "lavfi", "-t", f"{tail_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-filter_complex",
        (
            "[0:v]scale=1940:1092:flags=lanczos,"
            f"zoompan=z='min(pzoom+{zoom_rate:.8f},1.08)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            "d=1:s=1920x1080:fps=30,format=yuv420p[v];"
            "[2:a][1:a][3:a]concat=n=3:v=0:a=1[aout]"
        ),
        "-map", "[v]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{total:.3f}", str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode()[-600:])
    print(f"  [seg] ✓  {out.name}")


def make_animated_segment(shot_videos: list[Path], overlay_png: Path,
                          audio: Path, out: Path,
                          head_sil: float = 0.6, tail_sil: float = 2.2,
                          force: bool = False) -> None:
    if not shot_videos:
        raise RuntimeError("No animated shot videos were generated for this slide")

    a_dur = audio_duration(audio)
    total = head_sil + a_dur + tail_sil
    if out.exists() and not force:
        try:
            existing_duration = audio_duration(out)
        except Exception:
            existing_duration = 0.0
        if existing_duration >= total - 0.25:
            print(f"  [seg] cached  {out.name}")
            return
        print(f"  [seg] rebuilding short/corrupt  {out.name}")
        out.unlink(missing_ok=True)

    share = total / len(shot_videos)

    cmd = ["ffmpeg", "-y"]
    for shot_video in shot_videos:
        cmd += ["-stream_loop", "-1", "-i", str(shot_video)]
    cmd += [
        "-loop", "1", "-t", f"{total:.3f}", "-i", str(overlay_png),
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{head_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-f", "lavfi", "-t", f"{tail_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
    ]

    filter_parts = []
    concat_inputs = []
    for idx, shot_video in enumerate(shot_videos):
        base_duration = max(0.1, audio_duration(shot_video))
        pts_scale = share / base_duration
        filter_parts.append(
            f"[{idx}:v]scale=1920:1080:flags=lanczos,"
            f"setpts=(PTS-STARTPTS)*{pts_scale:.6f},"
            f"trim=duration={share:.3f},setpts=PTS-STARTPTS,"
            f"fps=30,format=yuv420p[v{idx}]"
        )
        concat_inputs.append(f"[v{idx}]")

    overlay_input = len(shot_videos)
    audio_input = len(shot_videos) + 1
    head_input = len(shot_videos) + 2
    tail_input = len(shot_videos) + 3
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(shot_videos)}:v=1:a=0[vcat]")
    filter_parts.append(f"[vcat][{overlay_input}:v]overlay=0:0:shortest=1,format=yuv420p[vout]")
    filter_parts.append(f"[{head_input}:a][{audio_input}:a][{tail_input}:a]concat=n=3:v=0:a=1[aout]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]", "-map", "[aout]",
        *local_h264_args(),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{total:.3f}", str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode()[-800:])
    print(f"  [seg] ✓  {out.name}")


def make_hybrid_loop_segment(shot_videos: list[Path], overlay_png: Path,
                             audio: Path, out: Path,
                             head_sil: float = 0.6, tail_sil: float = 2.2,
                             force: bool = False) -> None:
    if not shot_videos:
        raise RuntimeError("No animated shot videos were generated for this slide")

    a_dur = audio_duration(audio)
    total = head_sil + a_dur + tail_sil
    if out.exists() and not force:
        try:
            existing_duration = audio_duration(out)
        except Exception:
            existing_duration = 0.0
        if existing_duration >= total - 0.25:
            print(f"  [seg] cached  {out.name}")
            return
        print(f"  [seg] rebuilding short/corrupt  {out.name}")
        out.unlink(missing_ok=True)

    share = total / len(shot_videos)

    cmd = ["ffmpeg", "-y"]
    for shot_video in shot_videos:
        cmd += ["-stream_loop", "-1", "-i", str(shot_video)]
    cmd += [
        "-loop", "1", "-t", f"{total:.3f}", "-i", str(overlay_png),
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{head_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-f", "lavfi", "-t", f"{tail_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
    ]

    filter_parts = []
    concat_inputs = []
    for idx, _shot_video in enumerate(shot_videos):
        filter_parts.append(
            f"[{idx}:v]scale=1920:1080:flags=lanczos:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,fps=30,format=yuv420p,"
            f"trim=duration={share:.3f},setpts=PTS-STARTPTS[v{idx}]"
        )
        concat_inputs.append(f"[v{idx}]")

    overlay_input = len(shot_videos)
    audio_input = len(shot_videos) + 1
    head_input = len(shot_videos) + 2
    tail_input = len(shot_videos) + 3
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(shot_videos)}:v=1:a=0[vcat]")
    filter_parts.append(f"[vcat][{overlay_input}:v]overlay=0:0:shortest=1,format=yuv420p[vout]")
    filter_parts.append(f"[{head_input}:a][{audio_input}:a][{tail_input}:a]concat=n=3:v=0:a=1[aout]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]", "-map", "[aout]",
        *local_h264_args(),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{total:.3f}", str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode()[-800:])
    print(f"  [seg] ✓  {out.name}")


def make_hybrid_hold_segment(shot_videos: list[Path], overlay_png: Path,
                             audio: Path, out: Path,
                             head_sil: float = 0.6, tail_sil: float = 2.2,
                             force: bool = False) -> None:
    if not shot_videos:
        raise RuntimeError("No animated shot videos were generated for this slide")

    a_dur = audio_duration(audio)
    total = head_sil + a_dur + tail_sil
    if out.exists() and not force:
        print(f"  [seg] cached  {out.name}")
        return

    share = total / len(shot_videos)
    cmd = ["ffmpeg", "-y"]
    for shot_video in shot_videos:
        cmd += ["-i", str(shot_video)]
    cmd += [
        "-loop", "1", "-t", f"{total:.3f}", "-i", str(overlay_png),
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{head_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-f", "lavfi", "-t", f"{tail_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
    ]

    filter_parts = []
    concat_inputs = []
    for idx, _shot_video in enumerate(shot_videos):
        filter_parts.append(
            f"[{idx}:v]scale=1920:1080:flags=lanczos:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,fps=30,format=yuv420p,"
            f"trim=duration={share:.3f},setpts=PTS-STARTPTS[v{idx}]"
        )
        concat_inputs.append(f"[v{idx}]")

    overlay_input = len(shot_videos)
    audio_input = len(shot_videos) + 1
    head_input = len(shot_videos) + 2
    tail_input = len(shot_videos) + 3
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(shot_videos)}:v=1:a=0[vcat]")
    filter_parts.append(f"[vcat][{overlay_input}:v]overlay=0:0:shortest=1,format=yuv420p[vout]")
    filter_parts.append(f"[{head_input}:a][{audio_input}:a][{tail_input}:a]concat=n=3:v=0:a=1[aout]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]", "-map", "[aout]",
        *local_h264_args(),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{total:.3f}", str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode()[-800:])
    print(f"  [seg] ✓  {out.name}")


def make_storybook_segment(img: Path, overlay_png: Path, audio: Path, out: Path,
                           slide_index: int,
                           head_sil: float = 0.6, tail_sil: float = 2.2,
                           force: bool = False) -> None:
    if out.exists() and not force:
        print(f"  [seg] cached  {out.name}")
        return

    a_dur = audio_duration(audio)
    total = head_sil + a_dur + tail_sil
    seed = slide_index * 0.73
    fireflies = []
    for idx in range(12):
        base_x = 120 + ((idx * 167 + slide_index * 53) % 1680)
        base_y = 120 + ((idx * 91 + slide_index * 47) % 680)
        amp_x = 18 + (idx % 4) * 8
        amp_y = 12 + (idx % 5) * 6
        speed = 0.18 + (idx % 6) * 0.035
        phase = seed + idx * 0.67
        size = 5 + (idx % 3) * 2
        alpha = 0.20 + (idx % 4) * 0.06
        fireflies.append(
            "drawbox="
            f"x='{base_x}+{amp_x}*sin(t*{speed:.3f}+{phase:.3f})':"
            f"y='{base_y}+{amp_y}*cos(t*{speed * 0.83:.3f}+{phase:.3f})':"
            f"w={size}:h={size}:color=0xffd36a@{alpha:.2f}:t=fill"
        )

    visual_filter = ",".join([
        "[0:v]scale=2200:1238:flags=lanczos:force_original_aspect_ratio=increase",
        "crop=2200:1238",
        (
            "zoompan="
            f"z='1.045+0.018*sin(on/130+{seed:.3f})':"
            f"x='iw/2-(iw/zoom/2)+48*sin(on/95+{seed:.3f})':"
            f"y='ih/2-(ih/zoom/2)+28*cos(on/125+{seed:.3f})':"
            "d=1:s=1920x1080:fps=30"
        ),
        "format=rgba",
        *fireflies,
        "format=yuv420p[vbase]",
    ])
    cmd = [
        "ffmpeg", "-y",
        "-framerate", "30", "-loop", "1", "-t", f"{total:.3f}", "-i", str(img),
        "-loop", "1", "-t", f"{total:.3f}", "-i", str(overlay_png),
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{head_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-f", "lavfi", "-t", f"{tail_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-filter_complex",
        (
            f"{visual_filter};"
            "[vbase][1:v]overlay=0:0:shortest=1,format=yuv420p[vout];"
            "[3:a][2:a][4:a]concat=n=3:v=0:a=1[aout]"
        ),
        "-map", "[vout]", "-map", "[aout]",
        *local_h264_args(),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{total:.3f}", str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode()[-800:])
    print(f"  [seg] ✓  {out.name}")


def concat_segments(mp4s: list, out_mp4: Path) -> None:
    listfile = out_mp4.parent / "_concat.txt"
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in mp4s))
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    listfile.unlink(missing_ok=True)
    dur = audio_duration(out_mp4)
    sz  = out_mp4.stat().st_size / (1024 * 1024)
    print(f"\n  ✅  {out_mp4.name}  {dur:.0f}s ({dur/60:.1f} min)  {sz:.1f} MB")
    print(f"  📁  {out_mp4.resolve()}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a bedtime story video")
    parser.add_argument("story", help="Path to story data file, e.g. stories/clever_crow.py")
    parser.add_argument("--force", action="store_true", help="Re-generate all (ignore cache)")
    parser.add_argument("--lang", default="en", choices=["en", "te"], help="Language")
    parser.add_argument(
        "--video-mode",
        default="still",
        choices=["still", "animated", "storybook"],
        help="Use still-image segments, animated Fal.ai motion clips, or local 2.5D storybook motion",
    )
    parser.add_argument(
        "--segment-strategy",
        choices=["hybrid_loop", "hybrid_hold"],
        help="Override the animated segment strategy; hybrid_hold recreates the old held-frame output profile",
    )
    parser.add_argument(
        "--offline-images",
        action="store_true",
        help="Create rough local PIL prototype source images instead of calling AI image generation",
    )
    parser.add_argument(
        "--image-provider",
        default="openai",
        choices=["openai", "fal", "offline", "existing"],
        help="Source image provider: openai gpt-image-1, fal FLUX, rough offline prototype images, or pre-generated existing stills",
    )
    parser.add_argument(
        "--animation-provider",
        choices=["fal", "local"],
        help="Override animated clip provider: Fal API or pre-generated local/self-hosted shot clips",
    )
    parser.add_argument(
        "--selfhosted-image-dir",
        help="Directory with pre-generated source stills named slide01_shot01_raw.jpg or slide01_raw.jpg",
    )
    parser.add_argument(
        "--selfhosted-shot-dir",
        help="Directory with pre-generated shot clips named slide01_shot01.mp4 or slide01_shot01_<cache>_anim.mp4",
    )
    parser.add_argument(
        "--job-manifest",
        help="Optional planned job manifest; when provided, animation defaults and local asset paths default to the manifest values",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the plan and cost guard without generating media")
    args = parser.parse_args()
    if args.offline_images:
        args.image_provider = "offline"

    job_manifest = load_job_manifest(args.job_manifest)
    if job_manifest:
        if args.video_mode == "still":
            args.video_mode = str(job_manifest.get("plan", {}).get("video_mode", args.video_mode))
        if args.image_provider == "openai":
            args.image_provider = str(job_manifest.get("source_images", {}).get("provider", args.image_provider))
        if args.animation_provider is None:
            args.animation_provider = job_manifest.get("animation", {}).get("provider")
        if not args.selfhosted_image_dir:
            args.selfhosted_image_dir = job_manifest.get("paths", {}).get("source_image_dir")
        if not args.selfhosted_shot_dir:
            args.selfhosted_shot_dir = job_manifest.get("paths", {}).get("shot_dir")

    story = load_story(args.story, args.lang)
    if job_manifest:
        manifest_story_id = job_manifest.get("story", {}).get("story_id")
        if manifest_story_id and manifest_story_id != story.STORY_ID:
            raise SystemExit(
                f"❌  Job manifest story_id {manifest_story_id} does not match story {story.STORY_ID}"
            )

    story_id = story.STORY_ID
    if story._is_yaml:
        channel = story.CHANNEL_TE if args.lang == "te" else story.CHANNEL_EN
    else:
        channel = getattr(story, "CHANNEL_NAME", "Mitra AI Stories")
    art   = story.ART_STYLE
    voice = story.VOICE_TE if args.lang == "te" and hasattr(story, "VOICE_TE") else story.VOICE_EN

    slide_records = story_slide_records(story, args.lang)
    if args.lang == "te" and not slide_records:
        print("  [WARN] Telugu slides not found in story file — falling back to English narration")
        slide_records = story_slide_records(story, "en")

    out_dir = ROOT / "output" / story_id
    out_dir.mkdir(parents=True, exist_ok=True)
    if job_manifest and job_manifest.get("animation", {}).get("merged_defaults"):
        animated_defaults = animated_defaults_for_story(
            SimpleNamespace(ANIMATED_DEFAULTS=job_manifest["animation"]["merged_defaults"])
        )
    else:
        animated_defaults = animated_defaults_for_story(story)
    if args.animation_provider:
        animated_defaults["provider"] = args.animation_provider
    if args.segment_strategy:
        animated_defaults["segment_strategy"] = args.segment_strategy
    existing_image_dir = Path(args.selfhosted_image_dir).expanduser() if args.selfhosted_image_dir else None
    selfhosted_shot_dir = Path(args.selfhosted_shot_dir).expanduser() if args.selfhosted_shot_dir else None
    cache_tag = animation_cache_tag(animated_defaults)
    output_tag = animation_output_tag(animated_defaults)
    animation_provider = str(animated_defaults.get("provider", "fal")).lower()
    if args.video_mode == "still":
        mode_suffix = ""
    elif args.video_mode == "storybook":
        mode_suffix = "_storybook_local_2p5d"
    else:
        mode_suffix = f"_{args.video_mode}_{output_tag}"
    final = out_dir / f"final_{story_id}_{args.lang}{mode_suffix}.mp4"

    print(f"\n🎬  {story.STORY_TITLE}  [{args.lang.upper()}]  →  {final.name}")
    print(f"    {len(slide_records)} slides  |  channel: {channel}  |  mode: {args.video_mode}\n")
    if args.image_provider == "offline":
        print("    [WARN] offline image provider is a rough prototype only; not channel-quality")
    elif args.image_provider == "existing":
        print("    source image provider: existing self-hosted stills")
    else:
        print(f"    source image provider: {args.image_provider}")
    print()

    segments: list[Path] = []

    if args.video_mode == "animated":
        workload = estimate_animated_workload(
            story,
            slide_records,
            out_dir,
            args.force,
            selfhosted_shot_dir,
            animated_defaults,
        )
        estimated_cost = estimated_animated_cost_usd(workload, animated_defaults)
        print(
            "    animation model: "
            f"{animated_defaults['model']} | provider: {animation_provider} | input: {animated_defaults.get('model_input')} | cache: {cache_tag}"
        )
        print(f"    output profile: {output_tag}")
        print(
            "    animated workload: "
            f"{workload['total_shots']} shots | "
            f"{workload['total_output_seconds']} output seconds"
        )
        pending_label = "billable this run" if animation_provider == "fal" else "missing this run"
        print(
            f"    {pending_label}: "
            f"{workload['billable_shots']} shots | "
            f"{workload['billable_output_seconds']} output seconds"
        )
        if estimated_cost is not None:
            cap = animated_defaults.get("max_estimated_cost_usd")
            cap_text = f" | cap ${cap:.2f}" if cap is not None else ""
            cost_label = "estimated Fal cost" if animation_provider == "fal" else "estimated provider cost"
            print(f"    {cost_label}: ${estimated_cost:.2f}{cap_text}")
        enforce_animated_budget(workload, animated_defaults)
        if args.force:
            if animation_provider == "fal":
                print("    [WARN] --force will regenerate cached animated shots and bill them again")
            else:
                print("    [WARN] --force will rebuild cached animated shots from the self-hosted clip directory")
        print()
        if args.dry_run:
            if animation_provider == "local":
                print("    dry run only; no TTS, local asset staging, or video assembly was started")
            else:
                print("    dry run only; no TTS, image, video, or Fal generation was started")
            return
        if animation_provider == "fal":
            ensure_fal_ready()
    elif args.video_mode == "storybook":
        print("    local 2.5D storybook mode: no Fal video generation")
        print("    source images and TTS are generated only when missing")
        print()
        if args.dry_run:
            print("    dry run only; no media generation was started")
            return
    elif args.dry_run:
        print("    dry run only; no media generation was started")
        return

    for i, slide in enumerate(slide_records, 1):
        tag = f"slide{i:02d}"
        eyebrow = slide.get("eyebrow", "")
        title = slide.get("title", "")
        scene_prompt = slide.get("dall_e_prompt", "")
        narration = slide.get("narration", "")
        print(f"── Slide {i:02d}/{len(slide_records)}: {title or '(title card)'}")

        raw_img = out_dir / f"{tag}_raw.jpg"
        ovr_img = out_dir / f"{tag}_overlay_{args.lang}.jpg"
        ovr_png = out_dir / f"{tag}_overlay_layer_{args.lang}.png"
        audio   = out_dir / f"{tag}_{args.lang}.mp3"
        seg_mp4 = out_dir / f"{tag}_{args.lang}{mode_suffix}.mp4"

        tts_to_file(narration, voice, audio, args.force)

        if args.video_mode == "animated":
            shots = resolve_slide_shots(story, slide_records, i - 1, animated_defaults)
            shot_videos: list[Path] = []
            print(f"  [plan] {len(shots)} animated shots")
            for shot_idx, shot in enumerate(shots, 1):
                shot_tag = f"{tag}_shot{shot_idx:02d}"
                shot_img = out_dir / f"{shot_tag}_raw.jpg"
                shot_vid = out_dir / f"{shot_tag}_{cache_tag}_anim.mp4"
                if animated_defaults.get("model_input") == "image":
                    generate_source_image(
                        art,
                        shot.get("image_prompt", scene_prompt),
                        shot_img,
                        args.force,
                        args.image_provider,
                        i,
                        existing_image_dir,
                    )
                generate_animated_shot(
                    shot_img if animated_defaults.get("model_input") == "image" else None,
                    video_prompt_for_shot(shot, scene_prompt, animated_defaults),
                    shot_vid,
                    animated_defaults,
                    int(shot.get("duration", animated_defaults["shot_duration_seconds"])),
                    shot.get("negative_prompt", animated_defaults["negative_prompt"]),
                    args.force,
                    animation_provider,
                    selfhosted_shot_dir,
                    shot_tag,
                )
                shot_videos.append(shot_vid)

            if not ovr_png.exists() or args.force:
                create_text_overlay_layer(title, eyebrow, channel, ovr_png)
                print(f"  [ovr] ✓  {ovr_png.name}")
            else:
                print(f"  [ovr] cached  {ovr_png.name}")

            if animated_defaults.get("segment_strategy") == "hybrid_loop":
                make_hybrid_loop_segment(shot_videos, ovr_png, audio, seg_mp4, force=args.force)
            elif animated_defaults.get("segment_strategy") == "hybrid_hold":
                make_hybrid_hold_segment(shot_videos, ovr_png, audio, seg_mp4, force=args.force)
            else:
                make_animated_segment(shot_videos, ovr_png, audio, seg_mp4, force=args.force)
        elif args.video_mode == "storybook":
            storybook_img = raw_img
            cached_shot_img = out_dir / f"{tag}_shot01_raw.jpg"
            if not args.force and not storybook_img.exists() and cached_shot_img.exists():
                storybook_img = cached_shot_img
                print(f"  [img] cached  {storybook_img.name}")
            else:
                generate_source_image(art, scene_prompt, storybook_img, args.force, args.image_provider, i, existing_image_dir)

            if not ovr_png.exists() or args.force:
                create_text_overlay_layer(title, eyebrow, channel, ovr_png)
                print(f"  [ovr] ✓  {ovr_png.name}")
            else:
                print(f"  [ovr] cached  {ovr_png.name}")

            make_storybook_segment(storybook_img, ovr_png, audio, seg_mp4, i, force=args.force)
        else:
            generate_source_image(art, scene_prompt, raw_img, args.force, args.image_provider, i, existing_image_dir)

            if not ovr_img.exists() or args.force:
                add_text_overlay(raw_img, title, eyebrow, channel, ovr_img)
                print(f"  [ovr] ✓  {ovr_img.name}")
            else:
                print(f"  [ovr] cached  {ovr_img.name}")

            make_segment(ovr_img, audio, seg_mp4, force=args.force)

        segments.append(seg_mp4)

    print(f"\n── Concatenating {len(segments)} segments …")
    concat_segments(segments, final)

    meta_file = out_dir / f"youtube_metadata_{args.lang}.txt"
    if story._is_yaml:
        meta_text = _format_youtube_meta(story._yaml_meta, args.lang)
        if meta_text:
            meta_file.write_text(meta_text, encoding="utf-8")
            print(f"  📝  YouTube metadata → {meta_file.name}")
    elif hasattr(story, "YOUTUBE_METADATA"):
        meta_file.write_text(story.YOUTUBE_METADATA)
        print(f"  📝  YouTube metadata → {meta_file.name}")


if __name__ == "__main__":
    main()
