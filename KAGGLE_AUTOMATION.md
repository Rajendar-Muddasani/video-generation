# Kaggle Automation

This is the Kaggle-first launcher flow built on top of the manifest pipeline.

## Goal

Move only the expensive clip generation to Kaggle while keeping planning, final assembly, and validation local.

The pipeline now has three handoff commands:

1. `orchestration/publish_job_bundle.py`
2. `orchestration/kaggle_worker.py`
3. `orchestration/sync_job_results.py`

## Storage Choice

The current automation uses a private Hugging Face dataset repo as the shared handoff layer.

The GitHub repo and the Hugging Face repo are separate concerns:

- GitHub hosts the source code for this project.
- Hugging Face dataset storage holds the staged job bundle, manifest state, and rendered clips.

Why:

- Kaggle can read and write it with `huggingface_hub`
- the same storage layer also works later from Colab or a rented GPU
- each job can live under `jobs/<job-id>/...` without changing the manifest model

## Hugging Face Prerequisites

Before Step 2 or Step 3, all of these must be true:

1. You have a real Hugging Face access token, not another provider key.
2. The token has permission to read and write dataset repos.
3. The `repo_id` uses a Hugging Face namespace that actually exists for your account or HF organization.
4. Step 2 completes successfully at least once, so the dataset repo and `jobs/<job-id>/input/` bundle exist before Kaggle tries to download them.

Important:

- Your GitHub organization name does not automatically become a Hugging Face namespace.
- If your Hugging Face profile is `https://huggingface.co/rajendarmuddasani`, then the safe default namespace is `rajendarmuddasani/...`.
- If you want an organization namespace on Hugging Face, create that HF organization first and make sure your token can access it.
- A valid Hugging Face token typically starts with `hf_`.

Quick local token check:

```bash
source .venv/bin/activate
pip install -r requirements-orchestration.txt
python - <<'PY'
import os
from huggingface_hub import HfApi

token = os.environ.get("HF_TOKEN")
if not token:
  raise SystemExit("HF_TOKEN is not set")

api = HfApi(token=token)
print(api.whoami())
PY
```

If that fails, do not continue to Kaggle yet.

Local orchestration scripts now auto-load the repo `.env` when available. They accept `HF_TOKEN`, `HUGGINGFACE_HUB_TOKEN`, or `HF_KEY` for local Hugging Face operations.

## Install Local Orchestration Dependencies

```bash
source .venv/bin/activate
pip install -r requirements-orchestration.txt
```

## Step 1: Plan The Job

```bash
python orchestration/plan_job.py \
  stories/the-deer-and-the-firefly-path.yaml \
  --profile profiles/bedtime-lowcost-v1.yaml
```

## Step 2: Publish The Bundle

Set your Hugging Face token locally first:

```bash
export HF_TOKEN=hf_your_token_here
```

If you already keep the token in the repo `.env`, local orchestration scripts can also read `HF_KEY=...` or `HF_TOKEN=...` from there.

That must be on one line. Do not split it into `export HF_TOKEN` and a second line with the value.

Do not commit the token into the repo or leave a real token in this document.

Then publish the manifest plus source stills:

```bash
python orchestration/publish_job_bundle.py \
  jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml \
  --repo-id rajendarmuddasani/video-generation-jobs \
  --private \
  --force
```

If the token has permission to create dataset repos, this step creates the Hugging Face dataset repo automatically when it does not already exist.

If you change any bundled runtime file like `orchestration/render_job.py` or `orchestration/kaggle_worker.py`, rerun Step 2 with `--force` before retrying Kaggle so the updated worker code is uploaded into `jobs/<job-id>/input/`.

This step is not successful unless you see a line like:

```text
[bundle] uploaded to <repo-id>:jobs/<job-id>/input
```

If you only see the staging-directory error, Kaggle will still fail because nothing was uploaded yet.

That uploads a portable input bundle to:

```text
jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1/input/
```

## Step 3: Run On Kaggle

This step happens inside a Kaggle notebook.

### 3A. Create the notebook session

1. In Kaggle, click `Create` -> `New Notebook`.
2. In the right-side `Settings` pane, keep `Internet` turned on.
3. In the same pane, set `Accelerator` to `GPU`.
4. Wait for the GPU session to start before running the cells.

### 3B. Add the Hugging Face secret

1. In the notebook editor, open the `Secrets` panel. In some Kaggle layouts it appears directly in the right sidebar; in others it is under `Add-ons`.
2. Click `Add a new secret`.
3. Set the name to `HF_TOKEN`.
4. Paste your Hugging Face access token as the value.
5. Make sure the notebook is allowed to read that secret.

### 3C. Run these notebook cells

Cell 1: load the secret and define the job.

```python
import os

from kaggle_secrets import UserSecretsClient

user_secrets = UserSecretsClient()
os.environ["HF_TOKEN"] = user_secrets.get_secret("HF_TOKEN")

REPO_ID = "rajendarmuddasani/video-generation-jobs"
JOB_ID = "the-deer-and-the-firefly-path__bedtime-lowcost-v1"
```

Use the exact same `REPO_ID` that succeeded in Step 2. Do not switch namespaces between local publish and Kaggle.

If the error URL contains `yourname/bedtime-story-jobs`, you are still running an older placeholder value instead of the real dataset repo id.

Cell 2: install the small bootstrap dependencies.

```python
!pip install -q huggingface-hub pyyaml
```

Optional sanity check cell:

```python
from huggingface_hub import HfApi

api = HfApi(token=os.environ["HF_TOKEN"])
print(api.whoami())
print(api.repo_info(repo_id=REPO_ID, repo_type="dataset"))
```

If this cell fails with `401` or `RepositoryNotFoundError`, the problem is still on the Hugging Face side: wrong token, wrong namespace, missing repo, or missing permissions.

Cell 3: download the staged bundle into the notebook working directory.

```python
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

snapshot_root = Path(snapshot_download(
  repo_id=REPO_ID,
  repo_type="dataset",
  token=os.environ["HF_TOKEN"],
  allow_patterns=[f"jobs/{JOB_ID}/input/**"],
))

source = snapshot_root / f"jobs/{JOB_ID}/input"
target = Path("job-input")

if target.exists():
  shutil.rmtree(target)

shutil.copytree(source, target)
print(f"Bundle copied to {target.resolve()}")
```

Cell 4: run the bundled worker.

```python
import subprocess
import sys

command = [
  sys.executable,
  "-u",
  "job-input/orchestration/kaggle_worker.py",
  "--repo-id",
  REPO_ID,
  "--job-id",
  JOB_ID,
  "--bundle-dir",
  "job-input",
  "--install-deps",
]

result = subprocess.run(command, check=False)
if result.returncode != 0:
  raise SystemExit(
    f"Kaggle worker failed with exit code {result.returncode}. "
    "Scroll up to the first traceback or pip error in the worker logs above; "
    "the outer notebook wrapper is not the root cause."
  )
```

If you are retrying an older already-published bundle on Kaggle, the quickest compatibility override is to append `"--dtype", "float16"` to that command. If the GPU still runs out of memory, try `"--cpu-offload"` or test only one slide first with `"--slides", "1"`.

During long Kaggle renders, the worker now uploads the refreshed manifest and any finished clip files incrementally, so `python orchestration/sync_job_results.py jobs/<job>.yaml` can show partial progress before the full render finishes.

If you prefer fewer cells, combine Cells 2-4 into one notebook cell:

```python
import os
import shutil
import subprocess
import sys
from pathlib import Path

!pip install -q huggingface-hub pyyaml

from huggingface_hub import snapshot_download

snapshot_root = Path(snapshot_download(
  repo_id=REPO_ID,
  repo_type="dataset",
  token=os.environ["HF_TOKEN"],
  allow_patterns=[f"jobs/{JOB_ID}/input/**"],
))

source = snapshot_root / f"jobs/{JOB_ID}/input"
target = Path("job-input")

if target.exists():
  shutil.rmtree(target)

shutil.copytree(source, target)

result = subprocess.run(
  [
    sys.executable,
    "-u",
    "job-input/orchestration/kaggle_worker.py",
    "--repo-id",
    REPO_ID,
    "--job-id",
    JOB_ID,
    "--bundle-dir",
    "job-input",
    "--install-deps",
  ],
  check=False,
)

if result.returncode != 0:
  raise SystemExit(
    f"Kaggle worker failed with exit code {result.returncode}. "
    "Scroll up to the first traceback or pip error in the worker logs above; "
    "the outer notebook wrapper is not the root cause."
  )
```

### 3D. What success looks like

At the end of the worker run you should see logs showing:

1. the manifest state refreshed
2. missing shots rendered or skipped if already present
3. updated manifest uploaded to `jobs/<job-id>/state/`
4. generated clips uploaded to `jobs/<job-id>/results/`

What it does:

1. downloads the published input bundle
2. installs orchestration and self-hosted render deps when asked
3. runs `orchestration/render_job.py` inside the downloaded bundle
4. uploads the updated manifest to `jobs/<job-id>/state/`
5. uploads generated clips to `jobs/<job-id>/results/`

## Step 4: Sync Results Back Locally

```bash
python orchestration/sync_job_results.py \
  jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml
```

That pulls back:

- the updated manifest state
- generated clip files under `selfhosted/...`

## Step 5: Assemble And Validate Locally

```bash
python orchestration/assemble_job.py \
  jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml \
  --validate
```

## Partial Retries

You can publish or render only selected slides.

Example:

```bash
python orchestration/publish_job_bundle.py \
  jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml \
  --repo-id rajendarmuddasani/video-generation-jobs \
  --slides 3,7-8 \
  --force
```

And on Kaggle:

```bash
python job-input/orchestration/kaggle_worker.py \
  --repo-id rajendarmuddasani/video-generation-jobs \
  --job-id the-deer-and-the-firefly-path__bedtime-lowcost-v1 \
  --bundle-dir job-input \
  --slides 3,7-8 \
  --install-deps
```

## Offline Validation Mode

You can validate most of the transport flow locally without touching HF or Kaggle:

```bash
python orchestration/publish_job_bundle.py \
  jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml \
  --repo-id dummy/local \
  --dry-run \
  --force

python orchestration/kaggle_worker.py \
  --repo-id dummy/local \
  --job-id the-deer-and-the-firefly-path__bedtime-lowcost-v1 \
  --bundle-dir .job-bundles/the-deer-and-the-firefly-path__bedtime-lowcost-v1 \
  --status-only \
  --skip-upload \
  --outbox-dir .job-bundles/the-deer-and-the-firefly-path__bedtime-lowcost-v1-outbox

python orchestration/sync_job_results.py \
  jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml \
  --from-dir .job-bundles/the-deer-and-the-firefly-path__bedtime-lowcost-v1-outbox
```

## Limits

Two things are still intentionally outside this repo:

- starting the Kaggle session itself
- supplying your own `HF_TOKEN`

Those are account-scoped operations and cannot be completed from local code alone.