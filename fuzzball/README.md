# Fuzzfiles

| File | Does | Onboarding |
|---|---|---|
| `check-data.fz` | Mounts `simulaxon-data` at `/data` and the organizers' `datasets` at `/shared`, makes the `/data` folders, lists both | Step 1 check |
| `weights/1-tribev2.fz` … `weights/5-nemotron-super-nvfp4.fz` | Download the model weights from Hugging Face into `/data/weights`, one workflow per repo, run one after another | Step 2 |
| `receive.fz` | Holds `/data` open so files can be streamed in with `fuzzball workflow exec` (the repo, the Spark's study data) | Step 2 |
| `pull-status.py` | Terminal chart of the weight downloads: `python3 fuzzball/pull-status.py --watch 15` | Step 2 |
| `render-env.fz` | NVIDIA's graphics libraries, the Hugging Face cache layout, and render-score's three Python environments on `/data` | Step 3 |
| `simulaxon.fz` | The UI build and the long-running task: `planner` (Nemotron) and `app-server` | Steps 4 to 6 |
| `render-score.fz` | Optional: render-score as an always-on service for instant previews; holds a GPU node while it runs | Step 3 |
| `observer.fz` | The observer study: motions, a task array of renders, TRIBE, analysis, maps, the app dataset | Step 7 |
| `gpu-log.sh` | Started in the background by every GPU job: every 15 s, the GPU's utilisation, power, temperature and SM clock, the job's memory, and its busiest commands, as `gpulog` lines in the job's log and JSON lines in `/data/log/metrics/gpu` for the app's dashboard | |
| `gpu-usage.py` | Reads the `gpulog` lines back, per job and task: `python3 fuzzball/gpu-usage.py [workflow-id ...] [--watch 30] [--json]`; no IDs reads every running workflow | |

Validate each Fuzzfile before it runs: `fuzzball workflow validate <file>`. Syntax: CIQ's [Fuzzfile Syntax Guide](https://docs.ciq.com/fuzzball/appendices/workflow-syntax); the cluster runs Fuzzball 4.3.1, so fields the 4.4 guide marks as new (`retry.on`, persistent endpoints) are refused. CLI setup and debugging: [../docs/fuzzball-cli.md](../docs/fuzzball-cli.md).
