---
description: "Write a complete new bedtime story file for this project."
name: "New Story"
argument-hint: "Story name and theme, e.g. 'The Tortoise and the Hare — Indian village setting'"
---

# New Story Writer

Write a new story file following the exact structure of `stories/clever_crow.py`.

## Rules
- Export: `STORY_ID`, `STORY_TITLE`, `CHANNEL_NAME`, `ART_STYLE`, `VOICE_EN`, `SLIDES`, `YOUTUBE_METADATA`
- 10 slides total: slide 1 = title card, slide 10 = goodnight card
- Slides 2–9: eyebrow like "Part 1"…"Part 8", proper title, vivid DALL-E scene, narration
- Narration word counts: title/goodnight = 40–50 words; story slides = 110–140 words
- DALL-E prompts: describe the scene only (no art style — it is prepended automatically)
- Language: simple, warm English. Indian setting preferred.
- Moral: clear and child-friendly (age 3–8)
- `ART_STYLE`: match the mood — watercolor for classic fables, flat vector for modern stories
- Save to `stories/<story_name>.py`

## After writing the file, tell me:
1. The exact run command: `python generate_story.py stories/<filename>.py`
2. Estimated video duration (total words ÷ 150 words/min at 0.85× rate)
3. Estimated cost (10 images × $0.08 + TTS)
