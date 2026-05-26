# Bed-Time Stories — AI Video Generator

Faceless YouTube bedtime story channel.
Each story is a Python data file. One engine generates all of them.

## Costs
| Item | Cost |
|------|------|
| 10 × DALL-E 3 images per story | ~$0.80 |
| Google TTS (~10k chars) | ~$0.16 |
| **Per story total** | **~$1.00** |

## First-time setup

```bash
# 1. Clone / open this folder in VS Code
cd /Users/rajendarmuddasani/AIML/bed-time-stories

# 2. Create virtual environment and install packages
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Copy .env.example → .env and fill in your keys
cp .env.example .env
# edit .env: add OPENAI_API_KEY and path to your Google TTS JSON key
```

## Generate a story

```bash
source .venv/bin/activate

# English (default)
python generate_story.py stories/clever_crow.py

# Telugu
python generate_story.py stories/clever_crow.py --lang te

# Re-generate everything (new DALL-E images + new TTS audio)
python generate_story.py stories/clever_crow.py --force
```

Output goes to `output/clever-crow/final_clever_crow_en.mp4`

## Add a new story

1. Copy `stories/clever_crow.py` → `stories/my_new_story.py`
2. Change `STORY_ID`, `STORY_TITLE`, `SLIDES`, `ART_STYLE`, `YOUTUBE_METADATA`
3. Run `python generate_story.py stories/my_new_story.py`

Ask Copilot:
> "Write a new story file for stories/tortoise_and_hare.py following the same
> structure as stories/clever_crow.py. Use Indian village setting and gentle
> bedtime pacing. Include 10 slides with DALL-E prompts and English narration."

## Improve quality with Copilot

Ask Copilot in this workspace to:
- Rewrite narration to be more lyrical / simpler / longer
- Change `ART_STYLE` to "Studio Ghibli style" or "flat vector illustration"
- Add background music (see `.github/prompts/add-bgm.prompt.md`)
- Add intro / outro card
- Generate a Telugu translation of the narration

## Project structure

```
bed-time-stories/
├── generate_story.py      ← video engine (do not edit unless improving the engine)
├── stories/
│   ├── clever_crow.py     ← story data: slides, narration, voice, art style
│   └── (add more here)
├── fonts/                 ← Noto Sans for text overlay
├── output/                ← generated videos (git-ignored)
├── .env                   ← API keys (git-ignored)
├── .env.example           ← template
├── requirements.txt
└── .github/
    ├── copilot-instructions.md
    └── prompts/
        └── new-story.prompt.md
```
