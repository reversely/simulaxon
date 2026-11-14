# Fuzzfiles

| File | Does | Onboarding |
|---|---|---|
| `check-data.fz` | Mounts `simulaxon-data` at `/data` and the organizers' `datasets` at `/shared`, makes the `/data` folders, lists both | Step 1 check |
| `weights/1-tribev2.fz` … `weights/5-nemotron-super-nvfp4.fz` | Download the model weights from Hugging Face into `/data/weights`, one workflow per repo | Step 2 |
| `receive.fz` | Holds `/data` open so files can be streamed in with `fuzzball workflow exec` | Step 2 |
| `simulaxon.fz` | Not written yet: the services `render-score` (Node A), `planner` and `app-server` (Node B), with `/data` mounted | Steps 3 to 5 |
| `observer.fz` | Not written yet: the observer study: motions, a task array of renders, TRIBE, analysis, maps, the app dataset | Step 7 |

Validate each Fuzzfile before it runs: `fuzzball workflow validate <file>`. Syntax: CIQ's [Fuzzfile Syntax Guide](https://docs.ciq.com/fuzzball/appendices/workflow-syntax). CLI setup and debugging: [../docs/fuzzball-cli.md](../docs/fuzzball-cli.md).
