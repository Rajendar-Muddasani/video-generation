#!/usr/bin/env python3
"""
generate_story.py — Story video engine
Generates a YouTube-ready MP4 from any story data file.

Usage:
    python generate_story.py stories/clever_crow.py
    python generate_story.py stories/clever_crow.py --force   # re-generate all
    python generate_story.py stories/clever_crow.py --lang te # Telugu version

Each story file must export:
    STORY_ID   : str  — used for output folder name, e.g. "clever-crow"
    STORY_TITLE: str  — human-readable title
    SLIDES     : list[tuple[eyebrow, title, dall_e_prompt, narration]]
    VOICE_EN   : dict — Google TTS voice config for English
    VOICE_TE   : dict — (optional) Telugu voice config
    ART_STYLE  : str  — prepended to every DALL-E prompt for visual consistency
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

# ── Environment ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_CREDS   = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

if not OPENAI_API_KEY:
    raise SystemExit("❌  OPENAI_API_KEY not set in .env")
if not GOOGLE_CREDS:
    raise SystemExit("❌  GOOGLE_APPLICATION_CREDENTIALS not set in .env")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDS

FONT_BOLD    = str(ROOT / "fonts/NotoSansTelugu-Bold.ttf")
FONT_REGULAR = str(ROOT / "fonts/NotoSansTelugu-Regular.ttf")


# ── Load story module dynamically ─────────────────────────────────────────────
def load_story(path: str):
    p = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("story", p)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── DALL-E 3 image generation ─────────────────────────────────────────────────
def generate_image(art_style: str, scene_prompt: str,
                   out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        print(f"  [img] cached  {out_path.name}")
        return
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    print(f"  [img] generating  {out_path.name} …")
    resp = client.images.generate(
        model="dall-e-3",
        prompt=art_style + scene_prompt,
        size="1792x1024",   # 16:9 landscape for YouTube
        quality="standard", # change to "hd" for richer detail at 2× cost
        n=1,
    )
    urllib.request.urlretrieve(resp.data[0].url, out_path)
    print(f"         ✓ saved")


# ── PIL text overlay ──────────────────────────────────────────────────────────
def add_text_overlay(raw_img: Path, title: str, eyebrow: str,
                     channel: str, out_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(raw_img).convert("RGB").resize((1920, 1080), Image.LANCZOS)
    W, H = 1920, 1080
    d    = ImageDraw.Draw(img)

    # Gradient dark bar at bottom for readability
    bar = Image.new("RGBA", (W, 230), (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    for y in range(230):
        bd.line([(0, y), (W, y)], fill=(0, 0, 0, int(185 * y / 230)))
    img.paste(bar, (0, H - 230), bar)

    try:
        f_sm    = ImageFont.truetype(FONT_REGULAR, 28)
        f_eye   = ImageFont.truetype(FONT_REGULAR, 34)
        f_title = ImageFont.truetype(FONT_BOLD,    68)
    except Exception:
        f_sm = f_eye = f_title = ImageFont.load_default()

    # Channel name — top right
    d.text((W - 28, 28), channel,
           fill=(255, 255, 255, 200), font=f_sm, anchor="ra")

    # Eyebrow (e.g. "PART 1") — lower left
    if eyebrow:
        d.text((48, H - 210), eyebrow.upper(), fill=(245, 158, 11), font=f_eye)

    # Title — centred, near bottom, word-wrapped
    words, lines, cur = title.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if d.textbbox((0, 0), t, font=f_title)[2] < W - 120:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    y = H - 155
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=f_title)
        x  = (W - (bb[2] - bb[0])) / 2
        d.text((x + 2, y + 2), ln, fill=(0, 0, 0, 220), font=f_title)  # shadow
        d.text((x,     y),     ln, fill=(255, 255, 255), font=f_title)
        y += int(f_title.size * 1.2)

    img.save(out_path, "JPEG", quality=95)


# ── Google Cloud TTS ──────────────────────────────────────────────────────────
def tts_to_file(text: str, voice_cfg: dict, out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        print(f"  [tts] cached  {out_path.name}")
        return
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    for voice_name in [voice_cfg["name"], voice_cfg.get("fallback", "")]:
        if not voice_name:
            continue
        try:
            resp = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=voice_cfg["language_code"],
                    name=voice_name,
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=voice_cfg.get("speaking_rate", 0.87),
                    pitch=voice_cfg.get("pitch", -1.5),
                ),
            )
            out_path.write_bytes(resp.audio_content)
            print(f"  [tts] ✓  {out_path.name}  ({voice_name})")
            return
        except Exception as e:
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


def make_segment(img: Path, audio: Path, out: Path,
                 head_sil: float = 0.6, tail_sil: float = 1.8) -> None:
    if out.exists():
        print(f"  [seg] cached  {out.name}")
        return
    a_dur = audio_duration(audio)
    total = head_sil + a_dur + tail_sil
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{total:.3f}", "-i", str(img),
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{head_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-f", "lavfi", "-t", f"{tail_sil:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-filter_complex", "[2:a][1:a][3:a]concat=n=3:v=0:a=1[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode()[-600:])
    print(f"  [seg] ✓  {out.name}")


def concat_segments(mp4s: list, out_mp4: Path) -> None:
    listfile = out_mp4.parent / "_concat.txt"
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in mp4s))
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
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
    parser.add_argument("story",    help="Path to story data file, e.g. stories/clever_crow.py")
    parser.add_argument("--force",  action="store_true", help="Re-generate all (ignore cache)")
    parser.add_argument("--lang",   default="en", choices=["en", "te"], help="Language")
    args = parser.parse_args()

    story = load_story(args.story)

    story_id = story.STORY_ID
    channel  = getattr(story, "CHANNEL_NAME", "Mitra AI Stories")
    slides   = story.SLIDES
    art      = story.ART_STYLE
    voice    = story.VOICE_TE if args.lang == "te" and hasattr(story, "VOICE_TE") else story.VOICE_EN

    out_dir = ROOT / "output" / story_id
    out_dir.mkdir(parents=True, exist_ok=True)
    final   = out_dir / f"final_{story_id}_{args.lang}.mp4"

    print(f"\n🎬  {story.STORY_TITLE}  [{args.lang.upper()}]  →  {final.name}")
    print(f"    {len(slides)} slides  |  channel: {channel}\n")

    segments: list[Path] = []

    for i, (eyebrow, title, scene_prompt, narration) in enumerate(slides, 1):
        tag = f"slide{i:02d}"
        print(f"── Slide {i:02d}/{len(slides)}: {title or '(title card)'}")

        raw_img  = out_dir / f"{tag}_raw.jpg"
        ovr_img  = out_dir / f"{tag}_overlay.jpg"
        audio    = out_dir / f"{tag}_{args.lang}.mp3"
        seg_mp4  = out_dir / f"{tag}_{args.lang}.mp4"

        generate_image(art, scene_prompt, raw_img, args.force)

        if not ovr_img.exists() or args.force:
            add_text_overlay(raw_img, title, eyebrow, channel, ovr_img)
            print(f"  [ovr] ✓  {ovr_img.name}")
        else:
            print(f"  [ovr] cached  {ovr_img.name}")

        tts_to_file(narration, voice, audio, args.force)
        make_segment(ovr_img, audio, seg_mp4)
        segments.append(seg_mp4)

    print(f"\n── Concatenating {len(segments)} segments …")
    concat_segments(segments, final)

    # Write YouTube metadata
    if hasattr(story, "YOUTUBE_METADATA"):
        meta_file = out_dir / "youtube_metadata.txt"
        meta_file.write_text(story.YOUTUBE_METADATA)
        print(f"  📝  YouTube metadata → {meta_file.name}")


if __name__ == "__main__":
    main()
