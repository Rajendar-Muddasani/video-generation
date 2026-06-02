# Story 3 Video Workflow Top 10

Updated: 31 May 2026

Scope:
- Story 3: The Fireflies' Path Home
- Target final runtime: 7+ minutes
- Shared visual generation reused for both English and Telugu
- Costs below are visual-generation costs only; TTS and local ffmpeg work are excluded
- Assumes local post-processing is allowed: ffmpeg, overlays, zoom/pan, loops, crossfades, optional interpolation
- Rankings below combine ideas proposed by Claude, GPT, and Gemini, then normalize them against verified Fal pricing

Important corrections after verification:
- `fal-ai/wan-25-preview/text-to-video` is billed per second
- `fal-ai/wan-i2v` is flat-rate per video: $0.20 at 480p, $0.40 at 720p
- `fal-ai/wan-flf2v` is flat-rate per video: $0.20 at 480p, $0.40 at 720p
- `fal-ai/ltxv-2/image-to-video/fast` is $0.04/sec at 1080p and currently advertises 6-20 second clips, so some earlier 5-second math from other models needed correction

## Ranked Table

| Rank | Workflow Idea | Source Model(s) | Est. Paid Visual Cost | Motion Quality | Image Quality | 7+ Min Final Length | Verdict |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| 1 | Wan I2V 720p + local ambient extension | Gemini + verified Fal pages | About $4.30 | 8/10 | 8.5/10 | Yes, with local extension | Best strict-under-$5 plan. Generate 10 clips at 720p, then extend with fog, fireflies, loops, and camera motion. |
| 2 | Wan FLF2V 480p + local upscale/interpolation | Gemini + verified Fal pages | About $2.60 | 7.5/10 | 7.5/10 after upscale | Yes, with local extension | Cheapest serious hybrid. Good when start/end frames are well designed, but 480p needs local upscale. |
| 3 | Wan 7-scene x 3-shot hybrid | GPT-derived, corrected to current Wan T2V pricing | About $5.25 | 8.5/10 | 8.5/10 | Yes, naturally | Best low-cost per-second Wan concept if you loosen budget slightly above $5. Much better motion coverage than 10-slide x 2-shot. |
| 4 | Wan 10-slide x 3-shot hybrid | GPT | About $7.50 | 8.5/10 | 8.5/10 | Yes, naturally | Strong motion coverage and easy fit with current repo, but exceeds the strict $5 target. |
| 5 | LTX-2 Fast 1080p budget hybrid (20 clips x 6s) | Claude, corrected with verified LTX duration/pricing | About $4.80 | 7.5/10 | 9/10 | Yes, with local extension | Attractive 1080p option on paper. Biggest risk is that LTX may be less reliable for animal consistency than Wan. |
| 6 | LTX-2 Fast 1080p richer hybrid (25 clips x 6s) | Claude, corrected | About $6.00 | 8/10 | 9/10 | Yes, with local extension | Better motion than the strict-budget LTX plan. Good if you accept a little extra spend. |
| 7 | Kling hero scenes + LTX support scenes | Claude | About $6.78 | 8.8/10 | 9/10 | Yes, with local extension | Strong quality mix: use Kling only on the most important moments, LTX on the calmer scenes. More complex pipeline. |
| 8 | Wan 10-slide x 4-shot hybrid | GPT | About $10.00 | 9/10 | 8.8/10 | Yes, naturally | First Wan plan that starts to feel clearly premium, but well above your current target budget. |
| 9 | Wan I2V 720p chained continuity plan | Gemini | About $8.30 | 8.7/10 | 8.8/10 | Yes, naturally | Better sense of continuous scene action, but chaining can drift character details between clip generations. |
| 10 | Kling O3 Standard premium hybrid | Claude | About $10.08 | 9.2/10 | 9.2/10 | Yes, naturally | Best premium motion in this list, but cost is far beyond the $5 goal. Use only if quality matters more than budget. |

## Short Read

### Best strict-under-$5 option
Wan I2V 720p + local ambient extension.

Why:
- Verified flat-rate cost works under the cap
- Better native quality than 480p per-second Wan text-to-video
- Easy to reuse one visual track for both English and Telugu
- Works with the existing Python + ffmpeg structure with smaller changes than switching the whole pipeline

### Cheapest acceptable option
Wan FLF2V 480p + local upscale/interpolation.

Why:
- Lowest paid visual cost that still produces real motion
- Good if you can design strong first/last frames for each slide
- More local processing needed to make it feel upload-ready

### Best value if you can go slightly above $5
Wan 7-scene x 3-shot hybrid.

Why:
- Big jump in motion quality for a relatively small jump in cost
- Better viewer experience than spreading too few shots across too many slides
- Keeps the current repo's Wan text-to-video style mostly intact

## Recommendation for Story 3

If you must stay under $5:
- Choose `fal-ai/wan-i2v` at 720p
- Generate 10 strong clips, one per scene or slide
- Extend locally with ffmpeg zoom/pan, fog, fireflies, ping-pong loops, and crossfades
- Reuse the same finished visual track for English and Telugu

If you can allow a little budget flexibility:
- Prefer a 7-scene, 3-shot Wan hybrid around $5.25-$6.00 total visual spend
- It is more likely to feel like a proper animated story instead of a cleverly extended slideshow

## Practical Quality Bands

| Budget Band | Realistic Result |
| --- | --- |
| $2.50-$4.30 | Good hybrid bedtime video with smart local extension |
| $5.00-$6.00 | Clearly better motion if you choose the right model and limit scene count |
| $7.50-$10.00 | Strong, more premium motion coverage with less stretching |
| $12.50+ | Moon/River style full-motion comfort zone |

## Final Take

For Story 3 specifically, the best decision today is:
1. Prototype `wan-i2v` 720p hybrid first
2. Keep the video visual generation under about $4.30
3. Spend your quality effort on scene planning, consistent source images, and local extension design
4. Only fall back to the older per-second Wan text-to-video plan if I2V quality disappoints in testing
