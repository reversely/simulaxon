# observability

Prometheus and Grafana for every team13 workflow, run as their own workflow: `fuzzball/observability.fz`.

| Part | Does |
|---|---|
| `exporter.py` | Serves Prometheus metrics on port 19100: the latest GPU reading of each GPU job (`fuzzball/gpu-log.sh` writes them to `/data/log/metrics/gpu`), the state and node of every job in a running workflow, and each workflow that failed in the last 24 hours with its failed step, error and last log lines. `/targets` lists each running planner as `planner.<workflow id>:8000`, which any workflow in the group can reach. |
| `prometheus.yml` | Scrapes the exporter, every planner's vLLM `/metrics`, and itself, every 15 s. |
| `grafana/` | The Prometheus data source and the Simulaxon dashboard (failures, GPU jobs, planner, workflows), loaded from these files at start. |

Open Grafana: `fuzzball workflow port-forward <workflow-id> grafana 13000:13000`, then `http://localhost:13000`. Viewers need no login; the dashboard changes only through these files.

Limits:
- Prometheus keeps its database on the container's own disk, because its docs do not support NFS storage. History lasts as long as the workflow. The GPU readings stay on `/data` as JSON lines.
- The services use the node's network, so their ports (19100, 19090, 13000) must be free on the node; 9100 was taken on a GB10.
- GPU utilisation is nvidia-smi's: the share of time any kernel ran. The GB10 offers no SM or tensor-core metrics to unprivileged containers, and its GPU memory is not reported; job memory is the container's CPU-side memory only.
- Changes to these files reach the cluster after a re-stream of the code to `/data/src/simulaxon`. Grafana reloads the dashboard on its own; the exporter and Prometheus need the workflow restarted.
