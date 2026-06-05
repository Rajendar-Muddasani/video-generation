# Colab Automation

Use this when Kaggle keeps failing or when you prefer a cleaner GPU runtime.

## Manual Steps

1. Open a new Google Colab notebook.
2. In `Runtime -> Change runtime type`, choose `GPU`.
3. In the Colab Secrets panel, add a secret named `HF_TOKEN`.
4. Run the cells below in order.

## Cell 1: Load Token And Job Settings

```python
import os

REPO_ID = "rajendarmuddasani/video-generation-jobs"
JOB_ID = "the-deer-and-the-firefly-path__bedtime-lowcost-v1"

try:
    from google.colab import userdata
except ImportError as exc:
    raise RuntimeError("This notebook is intended to run inside Google Colab.") from exc

token = userdata.get("HF_TOKEN")
if not token:
    raise RuntimeError("Colab secret HF_TOKEN is missing.")

os.environ["HF_TOKEN"] = token
print("HF token loaded")
print("REPO_ID:", REPO_ID)
print("JOB_ID:", JOB_ID)
```

## Cell 2: Download Bundle And Run Worker

```python
import os
import shutil
import subprocess
import sys
from pathlib import Path

!pip install -q huggingface-hub pyyaml

from huggingface_hub import HfApi, snapshot_download

api = HfApi(token=os.environ["HF_TOKEN"])
print(api.whoami()["name"])
print(api.repo_info(repo_id=REPO_ID, repo_type="dataset").id)

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
    raise RuntimeError(
        f"Remote worker failed with exit code {result.returncode}. "
        "Scroll up to the first traceback or pip error in the logs above; "
        "the final wrapper error is not the root cause."
    )
```

## What Success Looks Like

Look for lines like:

```text
[setup] installing dependencies from requirements-selfhosted.txt
[info] LTX load policy (...)
[gen] slide01_shot01 -> ...
```

If Colab fails, capture the output starting at the first `[info] LTX load policy ...` line through the traceback.

## Local Follow-Up

After the cloud run starts uploading clips, sync locally:

```bash
source .venv/bin/activate
python orchestration/sync_job_results.py jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml
```

After all clips are synced, assemble locally:

```bash
source .venv/bin/activate
python orchestration/assemble_job.py jobs/the-deer-and-the-firefly-path__bedtime-lowcost-v1.yaml --validate
```
