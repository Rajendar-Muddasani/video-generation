---
description: "Write a complete new bilingual bedtime story YAML for this project."
name: "New Story"
argument-hint: "Story name and theme, e.g. 'The Little Lamp in the Rain - kindness and courage'"
---

# New Story Writer

Create a new story using the current YAML workflow.

Preferred workflow:

1. Convert the user's idea into `story_info.txt` fields if needed.
2. Create or update `stories/<story-id>.yaml` using the structure of `stories/the-moon-that-forgot-to-shine.yaml`.
3. Keep the story gentle, safe, and suitable for children aged 3-8.

## YAML Rules

- Include `story_id`, `story_title`, `story_title_te`, `art_style`, `youtube_en`, `youtube_te`, `slides_en`, `slides_te`, `channel_en`, `channel_te`, `voice_en`, `voice_te`, and `animated_defaults`.
- Use exactly 10 English slides and 10 Telugu slides.
- Slide 1 is a title card; slide 10 is a goodnight card.
- Slides 2-9 are the main story beats.
- Each slide must include `eyebrow`, `title`, `dall_e_prompt`, and `narration`.
- Keep `eyebrow` empty unless the user asks for section labels.
- DALL-E prompts should describe only the scene, not the global art style.
- Narration should be calm, simple, warm, and child-safe.
- Include a clear moral, woven naturally into the story.
- Telugu narration must use modern spoken Telugu that parents and kids use now. Avoid old, literary, Sanskrit-heavy, or hard-to-understand wording.

## Default Animation Settings

Use these safe defaults for new stories unless the user approves more spend:

```yaml
animated_defaults:
	provider: fal
	model: fal-ai/wan-25-preview/text-to-video
	model_input: text
	shot_duration_seconds: 5
	shots_per_slide: 1
	aspect_ratio: '16:9'
	resolution: 480p
	estimated_cost_per_second: 0.05
	max_estimated_cost_usd: 3.0
	negative_prompt: blur, distort, low quality, flicker, jitter, warped anatomy, extra limbs, text, watermark
	enable_prompt_expansion: true
	enable_safety_checker: true
```

## After Writing The Story

Report these commands:

```bash
source .venv/bin/activate
python generate_story.py stories/<story-id>.yaml --lang en --video-mode animated --dry-run
python generate_story.py stories/<story-id>.yaml --lang en --video-mode animated
python generate_story.py stories/<story-id>.yaml --lang te --video-mode animated --dry-run
```

Also report:

- Estimated runtime.
- Estimated Fal cost from dry-run assumptions.
- Whether English/Telugu slides are both complete.
- Reminder not to use `--force` unless paid regeneration is intended.
