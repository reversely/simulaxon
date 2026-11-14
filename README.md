# Simulaxon

Neural experiments in simulated worlds. A world is built and rendered in Isaac Sim, restyled toward photoreal by Cosmos, and read by TRIBE v2 as a person's predicted cortical response. A planner model and the app server run studies on that pipeline. Fuzzball places every piece on a GB10 cluster.

![Target architecture](docs/image.png)

## Start here

1. [docs/onboarding.md](docs/onboarding.md): the steps from an empty cluster to the picture above, each with its check.
2. [docs/wiring-prompt.md](docs/wiring-prompt.md): one agent prompt that wires the frontend, the app server and the services together.

## Layout

| Folder | What it is | In the picture |
|---|---|---|
| `frontend/` | The app interface: React and Vite, with the brain mesh assets | Browser app |
| `services/app-server/` | FastAPI and DuckDB: datasets, runs, the agent route | App server, Node B |
| `services/render-score/` | Isaac Sim 6.2, Cosmos3 Nano and TRIBE v2 workers, to run as one container | render-score service, Node A |
| `services/planner/` | Nemotron Super 120B (NVFP4), served by vLLM; configuration only, no code | Nemotron Super 120B, Node B |
| `studies/observer/` | The first study: a humanoid's look and motion, read by TRIBE as the observer's cortex | Submitted by the app server as a workflow |
| `fuzzball/` | The Fuzzfiles that start the services and run the studies | Fuzzball Orchestrate |
| `data/` | The layout of the VAST volume mounted at `/data` | VAST volume, shared provisioner |

## Third-party code and licences

| Component | Source | Pinned at | Licence |
|---|---|---|---|
| TRIBE v2 | `github.com/facebookresearch/tribev2` | `af58661` | CC BY-NC 4.0 |
| Cosmos framework (Cosmos3-Nano-Sim-Transfer) | `github.com/NVIDIA/cosmos-framework` | `c3a2e37` | NVIDIA's terms |
| Isaac Sim 6.2 | NVIDIA | 6.2 | NVIDIA's licence |
| EgoBody, SMPL-X | Their owners, after registration | | Each dataset's own terms; never committed |
