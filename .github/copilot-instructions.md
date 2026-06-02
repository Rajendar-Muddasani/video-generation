# Copilot Instructions - Bed-Time Stories

## What this project does
Generates faceless YouTube bedtime story videos for Mitra AI Stories:
- GPT-4o drafts bilingual English/Telugu story YAML from `story_info.txt` through `craft_story.py`.
- `gpt-image-1` creates still/source images for still mode and image-based workflows.
- Google Cloud Text-to-Speech creates soothing narration.
- Fal.ai Wan 2.5 text-to-video creates real animated motion clips.
- Pillow/PIL creates text overlays.
- ffmpeg/ffprobe assemble and validate final MP4s.

## Project conventions
- `generate_story.py` is the reusable engine; preserve its CLI unless the user asks for an engine change.
- `craft_story.py` is the preferred story-authoring helper: `story_info.txt -> stories/<story-id>.yaml`.
- New stories should be YAML, not legacy Python, unless the user explicitly asks for the old format.
- Legacy `stories/clever_crow.py` remains supported.
- Story YAML exports/provides: `story_id`, `story_title`, `story_title_te`, `art_style`, `youtube_en`, `youtube_te`, `slides_en`, `slides_te`, `voice_en`, `voice_te`, and `animated_defaults`.
- `output/` is git-ignored; generated videos are uploaded to YouTube, not committed.
- `.env` holds API keys; never include secrets in code or docs.

## Current animation defaults
- Provider: Fal.ai
- Model: `fal-ai/wan-25-preview/text-to-video`
- Model input: text
- Clip length: 5 seconds
- Resolution: 480p
- Estimated cost: `$0.05` per generated output second
- Cheap future-story default: 1 shot/slide, about `$2.50` per English animated story
- Higher-motion current moon profile: 5 shots/slide, 250 generated seconds, about `$12.50` if nothing is cached

## Cost safety rules
- Always run animated work with `--dry-run` before real generation.
- Never use `--force` on animated mode unless the user explicitly approves rebilling cached Fal clips.
- Preserve paid Wan cache files named `*_wan-25-preview-text-to-video_text_480p_5s_anim.mp4` during cleanup.
- If changing `shots_per_slide`, make sure output profile names include the shot count so old segments are not reused incorrectly.
- If the dry-run estimate exceeds the YAML `max_estimated_cost_usd`, stop and ask before changing the cap.

## When asked to write a new story
- Prefer updating `story_info.txt`, then running or preparing `craft_story.py` output as YAML.
- Follow the existing structure in `stories/the-moon-that-forgot-to-shine.yaml`.
- Each slide has `eyebrow`, `title`, `dall_e_prompt`, and `narration`.
- Use exactly 10 English slides and 10 Telugu slides.
- Slide 1 and slide 10 are shorter title/goodnight cards.
- Slides 2-9 carry the main story.
- Aim for about 7 minutes total at calm TTS pacing.
- DALL-E prompts should describe the scene only; the art style is prepended automatically.
- Narration should be simple, calm, warm, and suitable for children aged 3-8.
- Telugu narration should be modern spoken Telugu that parents and children use today. Avoid old, literary, Sanskrit-heavy, or hard-to-understand Telugu.

## When asked to improve video quality
- For richer still images: change `quality="medium"` to `quality="high"` in `generate_story.py` after warning about added OpenAI image cost.
- For different visual style: change `art_style` in the story YAML.
- For different voice: change the `name` in `voice_en` or `voice_te`; see https://cloud.google.com/text-to-speech/docs/voices.
- For calmer pacing: lower `speaking_rate` or adjust `head_sil` / `tail_sil` in segment generation.
- For smoother animated motion: increase `shots_per_slide`, but dry-run first because each added 5-second shot costs money.

## Tone and content rules
- Stories must be safe for children aged 3-8.
- Use gentle, warm, reassuring language.
- Indian settings and characters are welcome but not required.
- Every story should have a clear, simple moral.
- Never include scary, violent, or stressful content.

## Languages supported
- English: `--lang en`; current voice `en-US-Chirp3-HD-Aoede`, fallback `en-US-Neural2-F`.
- Telugu: `--lang te`; current voice `te-IN-Chirp3-HD-Kore`, fallback `te-IN-Standard-B`.
- To add Hindi, add `voice_hi` support in YAML loading and a Hindi TTS voice config.
