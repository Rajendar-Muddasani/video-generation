# Completed Stories Tracker

Updated: 1 June 2026

Current production stack: bilingual YAML stories, GPT-4o story drafting, Google Cloud Text-to-Speech narration, Fal.ai Wan 2.5 text-to-video or Wan-I2V animation, and ffmpeg final assembly.

## Completed Stories

| S.No. | Story Title | Source | Final Output | Duration | Size | Status | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| 1 | The Clever Crow | `stories/clever_crow.py` | Not kept in `output/` | N/A | N/A | Done | Legacy Python story. Old output was cleaned because it is reproducible. |
| 2 | The Moon That Forgot to Shine | `stories/the-moon-that-forgot-to-shine.yaml` | `output/the-moon-that-forgot-to-shine/final_the-moon-that-forgot-to-shine_en_animated_wan-25-preview-text-to-video_text_480p_5s_5shots.mp4` | 396.696s / 6.6 min | 141 MB | Done | English 5-shot Wan animated final kept and validated. |
| 3 | The Fireflies' Path Home | `stories/the-fireflies-path-home.yaml` | Full-loop EN: `output/the-fireflies-path-home/final_the-fireflies-path-home_en_animated_wan-i2v_image_720p_5s_1shots.mp4`<br>Full-loop TE: `output/the-fireflies-path-home/final_the-fireflies-path-home_te_animated_wan-i2v_image_720p_5s_1shots.mp4`<br>Paused EN: `output/the-fireflies-path-home/final_the-fireflies-path-home_en_animated_wan-i2v_image_720p_5s_1shots_hybrid-hold.mp4`<br>Paused TE: `output/the-fireflies-path-home/final_the-fireflies-path-home_te_animated_wan-i2v_image_720p_5s_1shots_hybrid-hold.mp4` | Full-loop EN: 469.177s / 7.8 min<br>Full-loop TE: 472.332s / 7.9 min<br>Paused EN: 469.215s / 7.8 min<br>Paused TE: 472.383s / 7.9 min | Full-loop EN: 344.7 MB<br>Full-loop TE: 347.9 MB<br>Paused EN: 43.2 MB<br>Paused TE: 43.8 MB | Done | Wan-I2V 720p hybrid. 10 shared Fal clips, estimated $4.00 Fal cost, reused for English and Telugu. Telugu narration was rewritten into modern spoken Telugu. Full-loop finals and recreated paused/held-frame finals decode-validated at 1920x1080 30fps. Slide 10 reused the safe home-scene visual cache after OpenAI image billing hit a hard limit. |
| 4 | The Deer and the Firefly Path | `stories/the-deer-and-the-firefly-path.yaml` | EN: `output/the-deer-and-the-firefly-path/final_the-deer-and-the-firefly-path_en_animated_wan-i2v_image_720p_5s_1shots.mp4`<br>TE: `output/the-deer-and-the-firefly-path/final_the-deer-and-the-firefly-path_te_animated_wan-i2v_image_720p_5s_1shots.mp4` | EN: 471.700s / 7.9 min<br>TE: 519.151s / 8.7 min | EN: 345.7 MB<br>TE: 380.9 MB | Done | Real-quality cute animated animal build using Fal FLUX source images and Wan-I2V 720p clips. English and Telugu finals decode-validated at 1920x1080 30fps. Opening continuity was corrected so slide 1 now starts with the deer alone before meeting the baby rabbit. Rejected offline prototype and continuity-rebuild attempts are quarantined under `output/the-deer-and-the-firefly-path/`. |
| 5 | The River That Learned to Listen | `stories/the-river-that-learned-to-listen.yaml` | `output/the-river-that-learned-to-listen/final_the-river-that-learned-to-listen_en_animated_wan-25-preview-text-to-video_text_480p_5s_5shots.mp4` | 443.710s / 7.4 min | 229 MB | Done | English 5-shot Wan animated final generated and decode-validated. |

## Next Open Candidate

| S.No. | Story Title | Planning Source | Target Style | Estimated Fal Cost | Status | Notes |
| --- | --- | --- | --- | ---: | --- | --- |
| 6 | The Little Lamp in the Rain | Backlog idea | TBD after story brief | TBD | Open | A small lamp keeps glowing through rain and teaches steady courage. |

## Cost Notes

- Old per-second Wan text-to-video math: 1 shot per slide = 10 clips = 50 output seconds = about $2.50 Fal, but motion feels slow.
- Old per-second Wan text-to-video 2-shot plan: 20 clips = 100 output seconds = about $5.00 Fal, but still stretches too much for a 7-minute story.
- Better Story 3 target: flat-rate Wan I2V/FLF2V. At verified Fal pricing, 10 x 480p FLF2V clips is about $2.00 plus optional image cost; 10 x 720p I2V clips is about $4.00 plus optional image cost.
- Best practical budget plan: generate 10 controlled source images, animate each slide once with `fal-ai/wan-i2v` or `fal-ai/wan-flf2v`, then extend locally with ffmpeg camera motion, fog/firefly overlays, loops, and crossfades.
- Story 3 actual Fal plan: 10 x `fal-ai/wan-i2v` 720p image-to-video clips, estimated $4.00 Fal. The same cached clips were reused for English and Telugu, then locally looped into full-length video streams for each narration segment.
- Story 4 final Fal route: Fal FLUX source stills plus `fal-ai/wan-i2v` 720p clips. Initial remaining resume cost was $0.80, then selected moon-artifact fixes regenerated only accepted clips; Telugu reused the same visual cache at $0.00 additional Wan cost.
- Higher-motion moon/river style: 5 shots per slide = 50 clips = 250 output seconds = about $12.50 Fal before any accidental rebilling.
- If Fal dashboard spend is higher than the formula, it usually means earlier tests, model changes, failed jobs that still produced outputs, or `--force`/regeneration caused additional billable clips.
- Use dry-run before paid generation unless the user explicitly approves a direct paid run.
- Do not use `--force` on animated mode unless rebilling cached clips is explicitly approved.

## Story 3 Hybrid Video Plan

Recommended prototype for `The Fireflies' Path Home`:

1. Draft 7-10 story scenes in YAML, keeping the final runtime at 7+ minutes through narration pacing.
2. Generate one strong source image per scene or slide with consistent moonlit forest style and animal details.
3. Animate each source image with `fal-ai/wan-i2v` at 720p, or use paired start/end images with `fal-ai/wan-flf2v` at 480p/720p when a scene needs a controlled transition.
4. Build each long slide segment locally using ffmpeg: native AI clip, ping-pong loop, slow zoom/pan, fog overlay, firefly particles, glow, and crossfade.
5. Assemble a master visual track once, then mux it separately with English and Telugu TTS audio.
6. Validate final files with `ffmpeg -v error -xerror -i <final> -map 0 -f null -` before marking Done.