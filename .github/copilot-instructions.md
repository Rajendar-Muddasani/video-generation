# Copilot Instructions — Bed-Time Stories

## What this project does
Generates faceless YouTube bedtime story videos:
- DALL-E 3 for illustrated scene images (1792×1024)
- Google Cloud TTS for soothing voice narration
- PIL for text overlay on images
- ffmpeg for assembling the final MP4

## Project conventions
- `generate_story.py` is the reusable engine — do not break its interface
- Every story lives in `stories/<story_name>.py` and exports: `STORY_ID`, `STORY_TITLE`, `SLIDES`, `ART_STYLE`, `VOICE_EN`, `YOUTUBE_METADATA`
- `output/` is git-ignored — videos are uploaded to YouTube, not committed
- `.env` holds API keys — never include them in code

## When asked to write a new story file
- Follow the exact structure of `stories/clever_crow.py`
- Each slide: `(eyebrow, title_overlay, dall_e_scene_prompt, narration_text)`
- Aim for 110–140 words per slide (50–65 seconds at 0.85× speaking rate)
- Title card (slide 1) and goodnight card (slide 10): 40–50 words
- DALL-E prompts: vivid scene description WITHOUT the art style prefix (it is added automatically)
- Narration: simple English, calm pacing, no jargon, suitable for children 3–8 years

## When asked to improve video quality
- For richer images: change `quality="standard"` → `quality="hd"` in `generate_story.py` (doubles image cost)
- For different visual style: change `ART_STYLE` in the story file
- For different voice: change `name` in `VOICE_EN` — see https://cloud.google.com/text-to-speech/docs/voices
- For pacing: adjust `speaking_rate` (lower = slower) and `tail_sil` in `make_segment()`

## Tone and content rules
- Stories must be safe for children (3–8 years)
- Use gentle, warm, reassuring language
- Indian settings and characters are preferred but not required
- Every story should have a clear, simple moral
- Never include scary, violent, or stressful content

## Languages supported
- English: `--lang en` (default) — voice: `en-US-Chirp3-HD-Aoede`
- Telugu: `--lang te` — voice: `te-IN-Chirp3-HD-Kore`
- To add Hindi: add `VOICE_HI` dict to the story file with `language_code: "hi-IN"`
