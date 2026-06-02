# Reusable Pipeline

This layer turns the repo from a one-off story runner into a reusable production pipeline.

## Why This Exists

For a 100-story roadmap, the repo needs a stable contract between three stages:

1. Story content
2. GPU clip generation
3. Local assembly and validation

The contract is a job manifest generated from a story file and a reusable channel profile.

## Files

- `profiles/*.yaml`: reusable production profiles by genre or channel
- `orchestration/plan_job.py`: builds a concrete job manifest from a story plus profile
- `orchestration/render_job.py`: renders only missing self-hosted clips from a manifest
- `orchestration/assemble_job.py`: assembles one or more final outputs from a manifest
- `orchestration/publish_job_bundle.py`: stages and uploads a portable remote-render bundle
- `orchestration/kaggle_worker.py`: remote worker that runs a staged bundle and pushes results back
- `orchestration/sync_job_results.py`: syncs updated manifest state and rendered clips back locally
- `jobs/*.yaml`: generated run manifests

## Profile Schema

Each profile should define:

- `profile_id`
- `display_name`
- `genre`
- `plan.languages`
- `plan.video_mode`
- `source_images.provider`
- `source_images.dir_template`
- `animation.provider`
- `animation.backend`
- `animation.model`
- `animation.generate_script`
- `animation.output_dir_template`
- `animation.defaults_override`
- `animation.worker_args`
- `budget`

This keeps creative choices out of the story YAML and makes the same story runnable under different channel strategies.

## Manifest Schema

`orchestration/plan_job.py` writes a manifest with these top-level sections:

- `schema_version`
- `job_id`
- `created_at`
- `story`
- `profile`
- `plan`
- `paths`
- `source_images`
- `animation`
- `assembly`
- `budget`
- `quality_control`
- `commands`
- `summary`
- `slides`

The important design rule is simple: the manifest is the frozen run contract. If you regenerate the same `job_id`, you should get the same clip directory, command surface, and shot map.

## Planner Command

Example:

```bash
source .venv/bin/activate
python orchestration/plan_job.py \
  stories/the-deer-and-the-firefly-path.yaml \
  --profile profiles/bedtime-lowcost-v1.yaml
```

That writes:

```text
jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml
```

The manifest includes ready-to-run commands for:

- manifest-driven clip generation via `orchestration/render_job.py`
- direct low-level clip generation via `scripts/generate_ltx_shots.py`
- EN assembly
- TE assembly when the profile enables it

## Execution Flow

Local status refresh:

```bash
python orchestration/render_job.py jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml --status-only
```

GPU render on Kaggle or Colab:

```bash
python orchestration/render_job.py jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml
```

Local assembly from the same manifest:

```bash
python orchestration/assemble_job.py jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml --validate
```

The important point is that the manifest is now the source of truth for both rendering and assembly. Profile overrides in the manifest feed back into `generate_story.py` through `--job-manifest`, so shot count, shot duration, cache tags, and final output names stay aligned.

## Kaggle Handoff

The remote loop is now:

1. `python orchestration/publish_job_bundle.py jobs/<job>.yaml --repo-id <dataset-repo>`
2. Run the bundled or repo-local `orchestration/kaggle_worker.py` on Kaggle
3. `python orchestration/sync_job_results.py jobs/<job>.yaml`
4. `python orchestration/assemble_job.py jobs/<job>.yaml --validate`

The bundle includes the worker entrypoint, the manifest, and only the required source stills, so the expensive GPU step can run remotely without shipping the full repo.

## Current Starter Profiles

- `profiles/bedtime-lowcost-v1.yaml`: the production-ready budget-first path for the current bedtime channel
- `profiles/technical-explainer-v1.yaml`: a starter profile for future technical explainer videos
- `profiles/entertainment-cinematic-v1.yaml`: a starter profile for future entertainment or series workflows

Only the bedtime profile is tuned to the current bilingual bedtime workflow. The other two are meant to lock the profile shape early so you do not fork the codebase by genre later.

## Next Extension

The next layer beyond this repo is scheduler automation: starting Kaggle or Colab sessions themselves and rotating through queued jobs. The current code already covers the handoff, execution, result sync, and local assembly surfaces.