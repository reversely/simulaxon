# Repository

How the code is laid out and where to start on a cluster. The product itself is described in the [README](../README.md).

## Start here

1. [onboarding.md](onboarding.md): the steps from an empty cluster to the architecture in [image.png](image.png), each with its check.
2. [wiring-prompt.md](wiring-prompt.md): one agent prompt that wires the frontend, the app server and the services together.

## Layout

| Folder | What it is | In the architecture |
|---|---|---|
| `frontend/` | The app interface: React and Vite. Chats with the agent, projects, experiments, examples | Browser app |
| `services/app-server/` | FastAPI and DuckDB: the lab's tools, runs, papers, datasets, the agent's chats | App server, Node B |
| `services/render-score/` | Isaac Sim 6.2, Cosmos3 Nano and TRIBE v2 workers, to run as one container | render-score service, Node A |
| `services/planner/` | Nemotron Super 120B (NVFP4), served by vLLM; configuration only, no code | Nemotron Super 120B, Node B |
| `studies/observer/` | The first study: a humanoid's look and motion, read by TRIBE as the observer's cortex | Submitted by the app server as a workflow |
| `fuzzball/` | The Fuzzfiles that start the services and run the studies | Fuzzball Orchestrate |
| `data/` | The layout of the VAST volume mounted at `/data` | VAST volume, shared provisioner |
| `docs/demo/` | The demo page, served by the app at `/demo/` | |
