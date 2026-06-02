#!/usr/bin/env python3
"""
craft_story.py — AI story content generator

Reads a story_info.txt file and calls GPT-4o to generate a complete
10-slide bedtime story YAML with English and Telugu content.

Usage:
    python craft_story.py -i story_info.txt
    python craft_story.py -i story_info.txt -o stories/my_story.yaml
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    raise SystemExit("❌  OPENAI_API_KEY not set in .env")

EN_EDGE_WORDS = (55, 75)
EN_BODY_WORDS = (120, 150)
TE_EDGE_WORDS = (40, 55)
TE_BODY_WORDS = (75, 100)
EN_TOTAL_WORDS = (1050, 1350)
TE_TOTAL_WORDS = (650, 850)


# ── Parse story_info.txt ──────────────────────────────────────────────────────
def parse_story_info(path: Path) -> dict:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip().upper()] = val.strip()
    return data


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


# ── GPT-4o prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are an expert children's bedtime story writer who creates gentle, warm, soothing stories
for children aged 3–8 years. You write both English and Telugu versions.

Slide structure rules:
- Slide 1  (Title Card):    eyebrow="", EN 55–75 words, TE 40–55 words, sets the scene warmly
- Slides 2–9 (Story):       eyebrow="" (empty), EN 120–150 words, TE 75–100 words
- Slide 10 (Goodnight Card): eyebrow="", EN 55–75 words, TE 40–55 words, ends with "Goodnight, little one."
- Target total runtime: around 7 minutes when spoken slowly with short pauses between slides
- English total narration target: 1050–1350 words
- Telugu total narration target: 650–850 Telugu words
- Do not summarize the story. Write full, gentle, expanded bedtime narration for each slide.

DALL-E prompt rules:
- Vivid, specific scene description (50–80 words)
- Do NOT include any art style — it is prepended automatically
- No text or letters visible in the image
- Safe, gentle, dreamlike imagery appropriate for children

Telugu narration rules:
- Simple, clear Telugu suitable for young children
- Calm and soothing tone
- Conveys the same story beats as the English version naturally in Telugu
- Telugu slide titles should be natural Telugu translations

Output ONLY valid JSON — no markdown fences, no extra commentary."""


def build_user_prompt(info: dict) -> str:
    target_minutes = info.get("TARGET_MINUTES", "7")
    return f"""\
Create a complete 10-slide children's bedtime story with these details:

TITLE (English) : {info.get("TITLE", "")}
MORAL           : {info.get("MORAL", "")}
DESCRIPTION     : {info.get("DESCRIPTION", "")}
KEY_BEATS       : {info.get("KEY_BEATS", "")}
ART_STYLE_HINT  : {info.get("ART_STYLE", "soft watercolor, dreamy night sky, pastel colours")}
TARGET_RUNTIME  : about {target_minutes} minutes total video length

Return a JSON object with EXACTLY this structure (no extra keys):
{{
  "story_id": "kebab-case-slug-from-title",
  "story_title": "English title",
  "story_title_te": "Telugu title",
  "art_style": "Full art style string to prepend to every DALL-E prompt (60–80 words)",
  "youtube_en": {{
    "title": "Engaging YouTube title in English (include story title + keywords)",
    "description": "YouTube description, 3–4 sentences, parent-friendly",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6"]
  }},
  "youtube_te": {{
    "title": "YouTube title in Telugu",
    "description": "YouTube description in Telugu, 3–4 sentences",
    "tags": ["Telugu tag1", "Telugu tag2", "Telugu tag3", "tag4", "tag5"]
  }},
  "slides_en": [
    {{
      "eyebrow": "",
      "title": "Slide title in English",
      "dall_e_prompt": "Detailed scene description for DALL-E",
      "narration": "English narration for this slide"
    }}
  ],
  "slides_te": [
    {{
      "eyebrow": "",
      "title": "Slide title in Telugu",
      "dall_e_prompt": "Same or adapted scene description for DALL-E",
      "narration": "Telugu narration for this slide"
    }}
  ]
}}

IMPORTANT:
- slides_en must contain EXACTLY 10 slide objects
- slides_te must contain EXACTLY 10 slide objects
- ALL slides eyebrow must be "" (empty string) for all 10 slides
- English narration must be long enough for about {target_minutes} minutes total runtime:
  - Slide 1 and 10: {EN_EDGE_WORDS[0]}–{EN_EDGE_WORDS[1]} words each
  - Slides 2–9: {EN_BODY_WORDS[0]}–{EN_BODY_WORDS[1]} words each
  - Total English narration: {EN_TOTAL_WORDS[0]}–{EN_TOTAL_WORDS[1]} words
- Telugu narration should match the English pacing naturally:
  - Slide 1 and 10: {TE_EDGE_WORDS[0]}–{TE_EDGE_WORDS[1]} Telugu words each
  - Slides 2–9: {TE_BODY_WORDS[0]}–{TE_BODY_WORDS[1]} Telugu words each
  - Total Telugu narration: {TE_TOTAL_WORDS[0]}–{TE_TOTAL_WORDS[1]} Telugu words
- Telugu dall_e_prompt can be identical to the English one (DALL-E ignores language)
- The moral to weave in naturally: {info.get("MORAL", "")}
"""


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def target_range(slides_key: str, slide_index: int) -> tuple[int, int]:
    is_edge = slide_index in (0, 9)
    if slides_key == "slides_te":
        return TE_EDGE_WORDS if is_edge else TE_BODY_WORDS
    return EN_EDGE_WORDS if is_edge else EN_BODY_WORDS


def length_issues(data: dict) -> list[str]:
    issues = []
    for slides_key, total_range in (("slides_en", EN_TOTAL_WORDS), ("slides_te", TE_TOTAL_WORDS)):
        slides = data.get(slides_key, [])
        if len(slides) != 10:
            issues.append(f"{slides_key} has {len(slides)} slides; expected 10")
            continue
        counts = [word_count(slide.get("narration", "")) for slide in slides]
        total = sum(counts)
        if total < total_range[0] or total > total_range[1]:
            issues.append(f"{slides_key} total is {total} words; target {total_range[0]}-{total_range[1]}")
        for idx, count in enumerate(counts):
            low, high = target_range(slides_key, idx)
            if count < low or count > high:
                issues.append(f"{slides_key} slide {idx + 1:02d} is {count} words; target {low}-{high}")
    return issues


# ── Main generation ───────────────────────────────────────────────────────────
def craft_yaml(info: dict, out_path: Path) -> None:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)

    print("🤖  Calling GPT-4o to craft the story …")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_prompt(info)},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )

    raw = resp.choices[0].message.content
    data = json.loads(raw)
    issues = length_issues(data)
    if issues:
        print("  ⚠️  Draft length check warnings:")
        for issue in issues[:16]:
            print(f"     - {issue}")
        print("  The YAML will still be written so you can review or expand it manually.")

    # Validate slide counts
    en_count = len(data.get("slides_en", []))
    te_count = len(data.get("slides_te", []))
    if en_count != 10 or te_count != 10:
        print(f"  ⚠️  Got {en_count} EN slides and {te_count} TE slides (expected 10 each)")
        print("  You may need to edit the YAML manually to complete any missing slides.")
    if issues:
        print("  ⚠️  Final draft still needs manual length review before video generation.")

    # Inject fixed fields
    data["channel_en"] = "Mitra AI Stories"
    data["channel_te"] = "మిత్ర AI కథలు"
    data["voice_en"] = {
        "language_code": "en-US",
        "name":           "en-US-Chirp3-HD-Aoede",
        "fallback":       "en-US-Neural2-F",
        "speaking_rate":  0.80,
        "pitch":          -2.0,
    }
    data["voice_te"] = {
        "language_code": "te-IN",
        "name":           "te-IN-Chirp3-HD-Kore",
        "fallback":       "te-IN-Standard-B",
        "speaking_rate":  0.78,
        "pitch":          -1.0,
    }
    data["animated_defaults"] = {
        "provider": "fal",
        "model": "fal-ai/wan-25-preview/text-to-video",
        "model_input": "text",
        "shot_duration_seconds": 5,
        "shots_per_slide": 1,
        "aspect_ratio": "16:9",
        "resolution": "480p",
        "estimated_cost_per_second": 0.05,
        "max_estimated_cost_usd": 3.0,
        "negative_prompt": (
            "blur, distort, low quality, flicker, jitter, warped anatomy, "
            "extra limbs, text, watermark"
        ),
        "enable_prompt_expansion": True,
        "enable_safety_checker": True,
    }

    # Write YAML with Unicode support (essential for Telugu)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )

    print(f"\n✅  Story YAML written → {out_path}")
    print(f"    EN slides : {en_count}")
    print(f"    TE slides : {te_count}")
    print(f"\n📝  Review and edit {out_path.name} before generating the video.")
    print(f"    Then run:")
    print(f"      python generate_story.py {out_path} --lang en")
    print(f"      python generate_story.py {out_path} --lang te")


def main() -> None:
    parser = argparse.ArgumentParser(description="Craft a bedtime story YAML from story_info.txt")
    parser.add_argument("-i", "--input",  required=True, help="Path to story_info.txt")
    parser.add_argument("-o", "--output", help="Output .yaml path (default: stories/<slug>.yaml)")
    args = parser.parse_args()

    info_path = Path(args.input)
    if not info_path.exists():
        raise SystemExit(f"❌  Not found: {info_path}")

    info = parse_story_info(info_path)
    if not info.get("TITLE"):
        raise SystemExit("❌  story_info.txt must contain a TITLE: line")

    if args.output:
        out_path = Path(args.output)
    else:
        slug     = slugify(info["TITLE"])
        out_path = ROOT / "stories" / f"{slug}.yaml"

    craft_yaml(info, out_path)


if __name__ == "__main__":
    main()
