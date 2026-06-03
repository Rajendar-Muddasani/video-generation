# Self-Hosted Short-Clip Stack

This is the concrete budget-first path for making a stitched ~7 minute bedtime story video without paying a hosted video API for every clip.

## 1. Dependencies To Add

Base repo dependencies stay in `requirements.txt`.

Optional self-hosted video dependencies live in `requirements-selfhosted.txt`.

Install torch separately on the GPU machine so it matches the runtime:

```bash
pip install -r requirements-selfhosted.txt
# Then install torch with the correct CUDA wheel for your host.
# Example only; choose the right command from pytorch.org for your machine.
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

Recommended model choice:

- Primary budget path: `Lightricks/LTX-Video` via Diffusers `LTXImageToVideoPipeline`
- Fallback higher-VRAM path: `THUDM/CogVideoX-5b-I2V`

Why this choice:

- The generic `Lightricks/LTX-Video` Diffusers repo is the safe target for this code path because it includes a packaged `model_index.json` pipeline layout.
- Some newer 2B checkpoint repos are raw checkpoint drops without Diffusers packaging, so `from_pretrained()` cannot load them directly.
- Diffusers documents quantized CogVideoX 5B around `~16GB` VRAM, which is less budget-friendly.
- For a hard `$5` recipe, LTX is the safer first target.

## 2. Commands To Run

Generate or curate one still per slide first. The cheapest first pass is to keep the existing still-generation path and self-host only the short motion clips.

Example directory layout for self-hosted clips:

```text
selfhosted/story-id/clips/
  slide01_shot01.mp4
  slide02_shot01.mp4
  ...
```

Generate local LTX clips from cached stills:

```bash
source .venv/bin/activate
python scripts/generate_ltx_shots.py \
  stories/the-deer-and-the-firefly-path.yaml \
  --image-dir output/the-deer-and-the-firefly-path \
  --output-dir selfhosted/the-deer-and-the-firefly-path/clips \
  --model Lightricks/LTX-Video \
  --seconds 4 \
  --fps 24 \
  --steps 6 \
  --dtype float16 \
  --cpu-offload \
  --guidance-scale 1.0
```

Dry-run local assembly with those clips:

```bash
python generate_story.py stories/the-deer-and-the-firefly-path.yaml \
  --lang en \
  --video-mode animated \
  --animation-provider local \
  --image-provider existing \
  --selfhosted-image-dir output/the-deer-and-the-firefly-path \
  --selfhosted-shot-dir selfhosted/the-deer-and-the-firefly-path/clips \
  --dry-run
```

Build the English final:

```bash
python generate_story.py stories/the-deer-and-the-firefly-path.yaml \
  --lang en \
  --video-mode animated \
  --animation-provider local \
  --image-provider existing \
  --selfhosted-image-dir output/the-deer-and-the-firefly-path \
  --selfhosted-shot-dir selfhosted/the-deer-and-the-firefly-path/clips
```

Reuse the same clips for Telugu at `$0.00` extra clip generation cost:

```bash
python generate_story.py stories/the-deer-and-the-firefly-path.yaml \
  --lang te \
  --video-mode animated \
  --animation-provider local \
  --image-provider existing \
  --selfhosted-image-dir output/the-deer-and-the-firefly-path \
  --selfhosted-shot-dir selfhosted/the-deer-and-the-firefly-path/clips
```

## 3. What Changed In `generate_story.py`

The repo now supports a self-hosted short-clip handoff instead of assuming Fal for every animated shot.

New flags:

- `--animation-provider local`
- `--selfhosted-shot-dir /path/to/clips`
- `--image-provider existing`
- `--selfhosted-image-dir /path/to/stills`

Behavior:

- `generate_story.py` can now stage pre-generated shot clips like `slide01_shot01.mp4`.
- It can also stage pre-generated stills like `slide01_shot01_raw.jpg`.
- Global OpenAI and Google credential checks were made lazy, so the script no longer exits at import time when you are only assembling local assets.

This keeps TTS, overlays, segment building, and final concat in one place while letting the expensive motion generation happen on your own rented GPU.

## 4. Hard `$5` Production Recipe

Use this exact recipe for the first self-hosted test:

- `10` slides total
- `1` clip per slide
- `4` seconds per clip
- `24` fps output clips
- `6` denoising steps on the 2B distilled LTX model
- `480x704` or similar low-cost resolution
- Reuse the same `10` clips for English and Telugu
- Reject bad stills before generating motion clips
- Rerun only failed or weak slides, never the whole story

Planning estimate for one 10-slide story:

| GPU | Practical use | Planning GPU hours | Budget note |
| --- | --- | ---: | --- |
| T4 | Cheapest but slowest | about `3-5h` | Can fit budget, but iteration is slow |
| L4 | Best first target | about `1-2h` | Good balance for a hard `$5` goal |
| A10G | Comfortable | about `0.8-1.5h` | Usually still under budget if retries are low |

Budget rule of thumb:

- First clean pass: roughly `$2-$4` on a rented L4/A10G class machine
- Add one or two slide retries: still aim to stay under `$5`
- First prototype with experimentation: budget `$5-$8`

Quality target:

- Similar overall quality to Story 4 is realistic if the stills are strong.
- The motion will not exactly match the hosted Wan look on every slide.
- For bedtime-story videos, strong stills plus careful local stitching matter more than chasing full continuous AI generation.