# Fuzzfiles

| File | Does | Onboarding |
|---|---|---|
| `check-data.fz` | Mounts `simulaxon-data` at `/data` and the organizers' `datasets` at `/shared`, makes the `/data` folders, lists both | Step 1 check |
| `weights/1-tribev2.fz` … `weights/5-nemotron-super-nvfp4.fz` | Download the model weights from Hugging Face into `/data/weights`, one workflow per repo, run one after another | Step 2 |
| `receive.fz` | Holds `/data` open so files can be streamed in with `fuzzball workflow exec` (the repo, the Spark's study data) | Step 2 |
| `pull-status.py` | Terminal chart of the weight downloads: `python3 fuzzball/pull-status.py --watch 15` | Step 2 |
| `render-env.fz` | NVIDIA's graphics libraries, the Hugging Face cache layout, and render-score's three Python environments on `/data` | Step 3 |
| `simulaxon.fz` | The UI build and the services `render-score`, `planner` and `app-server` | Steps 3 to 6 |
| `observer.fz` | The observer study: motions, a task array of renders, TRIBE, analysis, maps, the app dataset | Step 7 |

Validate each Fuzzfile before it runs: `fuzzball workflow validate <file>`. Syntax: CIQ's [Fuzzfile Syntax Guide](https://docs.ciq.com/fuzzball/appendices/workflow-syntax); the cluster runs Fuzzball 4.3.1, so fields the 4.4 guide marks as new (`retry.on`, persistent endpoints) are refused. CLI setup and debugging: [../docs/fuzzball-cli.md](../docs/fuzzball-cli.md).
