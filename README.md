# Bed-Time Stories - AI Video Generator

Faceless YouTube bedtime story generator for the Mitra AI Stories channel. The project creates calm, child-safe story videos in English and Telugu from reusable story source files.

The current preferred workflow is:

1. Write a short idea in `story_info.txt`.
2. Generate/review a bilingual YAML story with `craft_story.py`.
3. Render a still or animated MP4 with `generate_story.py`.
4. Upload the final MP4 and YouTube metadata from `output/<story-id>/`.

Legacy Python story files like `stories/clever_crow.py` still work, but new stories should use YAML.

## Current Status

| Item | Status | Notes |
|---|---:|---|
| Story engine | Done | `generate_story.py` supports YAML and legacy Python story files |
| Story crafter | Done | `craft_story.py` creates bilingual English/Telugu YAML from `story_info.txt` |
| Still videos | Done | Uses `gpt-image-1`, Google TTS, PIL overlays, and ffmpeg |
| Animated videos | Done | Uses Fal.ai Wan 2.5 text-to-video clips and ffmpeg stitching |
| Current final video | Done | `output/the-moon-that-forgot-to-shine/final_the-moon-that-forgot-to-shine_en_animated_wan-25-preview-text-to-video_text_480p_5s_5shots.mp4` |
| Story tracker | Done | See `stories_list.txt` |

## Tech Stack

| Area | Tooling |
|---|---|
| Runtime | Python 3, virtualenv |
| Story drafting | OpenAI GPT-4o via `craft_story.py` |
| Still images | OpenAI `gpt-image-1` |
| Narration | Google Cloud Text-to-Speech |
| Animated motion | Fal.ai `fal-ai/wan-25-preview/text-to-video` |
| Image/text overlays | Pillow/PIL with Noto Sans Telugu fonts |
| Video assembly | ffmpeg and ffprobe |
| Config | `.env`, `python-dotenv`, YAML |
| Python packages | See `requirements.txt` |

## Costs And Safety

Always run animated videos with `--dry-run` before starting paid Fal generation.

| Mode | Typical Cost Shape | Notes |
|---|---:|---|
| Still | OpenAI images + small TTS cost | Cached images/audio are reused unless `--force` is used |
| Wan animated, 1 shot/slide | About 50 generated seconds | About `$2.50` at `$0.05/sec` |
| Wan animated, 5 shots/slide | About 250 generated seconds | About `$12.50` total if no cache exists; current moon run reused 10 shots and added about `$10.00` |
| Re-run with cache | `$0.00` Fal | Current moon dry-run shows 0 billable shots |

Do not use `--force` on animated mode unless you deliberately want to regenerate cached paid clips and spend again.

## First-Time Setup

```bash
cd /Users/rajendarmuddasani/AIML/bed-time-stories
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```bash
OPENAI_API_KEY=...
GOOGLE_APPLICATION_CREDENTIALS=/path/to/google-tts-service-account.json
FAL_KEY=...
```

Install ffmpeg if it is not already available:

```bash
brew install ffmpeg
```

## Create A New Story

Edit `story_info.txt`:

```text
TITLE: The Moon That Forgot to Shine
MORAL: Even the brightest hearts sometimes need help.
TARGET_MINUTES: 7
DESCRIPTION: Short story description...
KEY_BEATS: Beat 1, beat 2, beat 3...
ART_STYLE: Soft watercolor children's book illustration...
```

Generate a bilingual YAML draft:

```bash
source .venv/bin/activate
python craft_story.py -i story_info.txt
```

Or choose an explicit output path:

```bash
python craft_story.py -i story_info.txt -o stories/my-new-story.yaml
```

Review the YAML before generating video. New story YAML should include:

- `story_id`
- `story_title`
- `story_title_te`
- `art_style`
- `youtube_en` and `youtube_te`
- `slides_en` and `slides_te`, 10 slides each
- `voice_en` and `voice_te`
- `animated_defaults`

## Generate Videos

Still English video:

```bash
source .venv/bin/activate
python generate_story.py stories/the-moon-that-forgot-to-shine.yaml --lang en
```

Still Telugu video:

```bash
python generate_story.py stories/the-moon-that-forgot-to-shine.yaml --lang te
```

Animated English dry run:

```bash
python generate_story.py stories/the-moon-that-forgot-to-shine.yaml --lang en --video-mode animated --dry-run
```

Animated English generation:

```bash
python generate_story.py stories/the-moon-that-forgot-to-shine.yaml --lang en --video-mode animated
```

Animated Telugu dry run:

```bash
python generate_story.py stories/the-moon-that-forgot-to-shine.yaml --lang te --video-mode animated --dry-run
```

Only use `--force` when you intentionally want new images, audio, segments, or paid animation clips.

## Self-Hosted Short Clips

The repo now supports a self-hosted short-clip path for budget control.

- Use `scripts/generate_ltx_shots.py` to create local slide clips from cached stills.
- Use `--animation-provider local` and `--selfhosted-shot-dir` to assemble those clips into the final story MP4.
- Use `--image-provider existing` and `--selfhosted-image-dir` to avoid accidental paid still generation.

See `SELF_HOSTED_STACK.md` for the concrete model choice, commands, GPU-hour estimate, and the hard `$5` recipe.

## Reusable Pipeline

For batch production, use `orchestration/plan_job.py` with a reusable profile in `profiles/`.

- Profiles define channel strategy like bedtime, technical explainer, or entertainment.
- The planner freezes one `jobs/<story-id>__<profile-id>.yaml` manifest with shot mapping, paths, budget, and ready-to-run commands.
- `orchestration/render_job.py` renders only missing manifest shots on your GPU worker.
- `orchestration/assemble_job.py` assembles EN and TE from the same manifest locally.
- `orchestration/publish_job_bundle.py`, `orchestration/kaggle_worker.py`, and `orchestration/sync_job_results.py` provide the remote Kaggle handoff loop.
- This keeps Kaggle or Colab generation separate from local assembly while remaining regeneratable.

See `ORCHESTRATION.md` for the manifest format and starter profiles, and `KAGGLE_AUTOMATION.md` for the remote execution flow.

## Output And Cleanup Policy

Generated media lives in `output/` and is ignored by git.

The recommended cleanup policy is:

- Keep the final MP4 you uploaded or want to review.
- Keep paid Wan cache files named `*_wan-25-preview-text-to-video_text_480p_5s_anim.mp4`.
- Keep `youtube_metadata_*.txt` files.
- Remove old still segments, old one-shot finals, overlay images, TTS audio, raw images, Python caches, and `.DS_Store` files when they are no longer needed.

The current moon output was cleaned to keep only the 5-shot final MP4, 50 Wan paid clips, and YouTube metadata. A dry run still reports `$0.00` Fal cost because the paid cache remains.

## Project Structure

```text
bed-time-stories/
|-- generate_story.py        # reusable video engine
|-- craft_story.py           # story_info.txt -> bilingual YAML generator
|-- story_info.txt           # input brief for the next story
|-- stories_list.txt         # 10-story status tracker
|-- stories/
|   |-- clever_crow.py       # legacy Python story format
|   `-- the-moon-that-forgot-to-shine.yaml
|-- fonts/                   # Noto Sans Telugu fonts for overlays
|-- output/                  # generated media, git-ignored
|-- .env.example             # environment variable template
|-- requirements.txt
`-- .github/
    |-- copilot-instructions.md
    `-- prompts/new-story.prompt.md
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `OPENAI_API_KEY not set` | Add it to `.env` |
| `GOOGLE_APPLICATION_CREDENTIALS not set` | Point it to your Google TTS service account JSON |
| Fal auth or billing error | Check `FAL_KEY` and account balance |
| Animated cost looks too high | Stop and adjust `shots_per_slide` or `max_estimated_cost_usd` before running without `--dry-run` |
| Video generation fails at ffmpeg | Confirm `ffmpeg` and `ffprobe` are installed and on PATH |
| Telugu text does not render | Confirm the Noto Sans Telugu font files exist in `fonts/` |
