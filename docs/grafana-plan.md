# Grafana: the compute story, and how the film shows it

The owner, 15 Nov: "the script and the narrative need to target: rocky linux usage, potentially rlc pro ai (?) and then fuzzball usage, uptime monitoring, use of both clusters in a way that isn't totally absurd. i think plan for when we get back online would be going based off real usage screenshots, so think about the data story and visualization path first in grafana itself and how that would map on elegantly. the dashboard should reflect a focus on compute optimization etc"

This plan comes first; the dashboard changes and the screenshots follow it once the cluster is back online. Ticket: #35.

## 1. The data story

Five questions, in the order a viewer asks them. Each is one Grafana row, and one card in the film.

| # | Question | Answer shown by | What it proves |
|---|---|---|---|
| 1 | Where do the GPU hours go? | GPU busy-seconds per service, stacked: planner, Isaac, Cosmos, TRIBE v2 | The pipeline's cost is visible per stage, so it can be cut per stage |
| 2 | Is a GPU working while it is held? | Utilisation while allocated, per job, as a heatmap over time | Renders run as tasks that release the GPU (`99e9939`), not an always-on service that holds it idle (#3) |
| 3 | Does each node fit in 128 GB? | Memory per node, the services stacked, a line at 128 GB | The 150 GB pipeline split across two nodes; the planner at 0.75 of GPU memory, after 0.85 died during FlashInfer's autotuning (`docs/onboarding.md` § 4) |
| 4 | How much work per GPU-hour? | Clips per hour; TRIBE v2 compute seconds per second of video; planner tokens per second and time to first token | Optimizations show as lines that move: identical V-JEPA 2 windows encoded once (#13), speculative decoding on the planner (#2) |
| 5 | Is it up, and what failed? | Node state over time; Prometheus scrape health; each failed step with Fuzzball's error | Uptime as a fact with history: control-plane outages on 14 Nov were recorded, and Prometheus history survives restarts (10-minute snapshots on `/data`) |

Question 1 is the thesis of the section: compute is measured per stage, so it can be optimized per stage. Questions 2 to 4 are three optimizations, each with a before and after. Question 5 is what keeps the numbers trustworthy.

## 2. What the dashboard has now, and what it needs

Now (`services/observability/grafana/dashboards/simulaxon.json`): Nodes, Study steps, Failures, GPU jobs (utilisation, power, job memory, temperature, busiest commands), Planner (requests, tokens per second, KV cache, time to first token, request time), Workflows, Weights.

| Question | Have | Missing |
|---|---|---|
| 1 | Utilisation per job, as a percentage | A counter of busy GPU-seconds per job, labelled by service and study run, so hours add up |
| 2 | Utilisation per job | Allocation time per job (from Fuzzball's stage start and end), so busy can be divided by held |
| 3 | Node memory available, job memory (CPU side) | Memory per service on each node, stacked; the GB10 reports no GPU memory to nvidia-smi, so this is the container's memory from its cgroup |
| 4 | Planner tokens per second, time to first token | Clips per hour and TRIBE v2 seconds per second of video, from render-score's job log; windows reused per clip |
| 5 | Node state, scrape health, failures | Uptime percentage per node over 24 h and 7 d, as a stat |

Row order changes to the story's order: a top row of five numbers (GPU-hours today, busy while held, clips per hour, planner tokens per second, uptime), then rows 1 to 5. Workflows and Weights move below, as reference.

Constraints already measured (`services/observability/README.md`): GPU utilisation is nvidia-smi's share of time any kernel ran; the GB10 gives unprivileged containers no SM or tensor-core metrics and no GPU memory; job memory is CPU-side only. Panels say so in their descriptions rather than imply more.

## 3. From Grafana to the film

The film's motion grammar is one card, one interaction (`docs/film.md`). Grafana already has that interaction: hovering a panel shows the value at a moment. So each film card is a real screenshot of one panel at 1920 by 1080, cropped to the panel, with the cursor moving to one point and Grafana's own tooltip showing the value there.

| Film card | Panel | The hover lands on |
|---|---|---|
| GPU hours by stage | Row 1, stacked | The observer study's run: Isaac, then TRIBE v2 |
| Busy while held | Row 2, heatmap | A render task: busy from start to release |
| 128 GB, two nodes | Row 3, stacked memory | The planner's band, under the 128 GB line |
| Work per GPU-hour | Row 4, TRIBE v2 seconds per video second | Before and after #13 |
| Up, and what failed | Row 5, node state | An outage on 14 Nov, then recovery |

Screenshots are taken from the live Grafana (`sh fuzzball/grafana.sh`, port 13000), with the time range set to a real run, never edited data.

## 4. Two machines, each doing what it is for

| Machine | Role | Why |
|---|---|---|
| DGX Spark | The desk: the lab app, interactive previews, the agent while a study is designed | One person, fast turns, warm workers |
| fb-hack Fuzzball cluster (GB10 nodes, Rocky Linux) | Production: the planner as a service, study runs as workflows and task arrays, Prometheus and Grafana | Scheduled, monitored, shared VAST storage, every run's clips and log kept |

The same study code runs in both: on the cluster in `rockylinux/rockylinux:10` containers (`fuzzball/observer.fz`), on the Spark from the same repo. The cluster run matched the Spark's predictions at median per-clip r 0.9991 (`baseline-compare`).

RLC Pro AI is CIQ's claim for this split: "Same OS for dev and production environments" and "A host driver upgrade doesn't mean rebuilding the container" (ciq.com/products/rocky-linux/ai). Simulaxon did not run on RLC Pro AI. What it shows is the work that claim would remove: `fuzzball/render-env.fz` extracts NVIDIA's graphics libraries for driver 580.173.02 onto the volume, because the cluster's GPU containers get compute libraries only. Whether the film names RLC Pro AI is the owner's decision.

## 5. Open

- The owner to confirm the two machines above are the "both clusters" meant.
- The Spark's operating system, to be checked before the film names it.
- The exporter additions in § 2 are code; they go in once the cluster is back and can be checked against live readings.
