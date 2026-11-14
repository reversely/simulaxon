# Onboarding: from an empty cluster to the picture

The target is [image.png](image.png). Each step below adds one box or arrow from it, and ends with a check that shows it works. The Fuzzball commands are from CIQ's documentation (v4.4).

| In the picture | Built in step |
|---|---|
| VAST volume at `/data`, shared provisioner | 1, 2 |
| render-score service on Node A (Isaac Sim 6.2 → Cosmos3 Nano → TRIBE v2) | 3 |
| Nemotron Super 120B on Node B, at `http://planner` | 4 |
| App server on Node B (FastAPI, DuckDB), submitting workflows | 5 |
| Browser app over HTTPS | 6 |
| A study, end to end | 7 |

## 0. Before you start

- Fuzzball runs on the cluster (Rocky Linux), and both nodes appear in `fuzzball node list --available-resources` with `nvidia.com/gpu`.
- Your CLI is logged in: `fuzzball context login`, then `fuzzball group use <team group>`.
- A Hugging Face token is stored as a secret: `fuzzball secret create secret://user/hf-token --type hf '{"token":"hf_…"}'`.

## 1. The volume at `/data`

- Add the storage provisioner for the VAST export (Volume Configuration and Management, Driver Types).
- Create one persistent volume, mounted at `/data` by every service, with the folders in [../data/README.md](../data/README.md).
- Put sample data and sample models on the shared provisioner.

**Check:** a one-line job that mounts the volume and runs `ls /data` prints `weights chunks predictions log studies`.

## 2. Weights and study data on `/data`

| What | Goes to | Used by |
|---|---|---|
| TRIBE v2 (`facebook/tribev2`) and V-JEPA 2 | `/data/weights/` | render-score |
| Cosmos3-Nano-Sim-Transfer, its text tokenizer, the Wan2.2 VAE | `/data/weights/` | render-score |
| Nemotron Super 120B, NVFP4 | `/data/weights/` | planner |
| SMPL-X v1.1 body model | `/data/studies/observer/` | observer study |
| EgoBody: the six recordings in `studies/observer` | `/data/studies/observer/` | observer study |

The six EgoBody recordings:
- `recording_20210923_S05_S13_02`
- `recording_20211002_S03_S18_02`
- `recording_20211004_S12_S20_01`
- `recording_20220218_S02_S23_02`
- `recording_20220225_S25_S24_01`
- `recording_20220315_S21_S30_05`

**Check:** every row in the table is present, at the size its source lists.

## 3. render-score on Node A

One container running Isaac Sim 6.2, Cosmos3 Nano and TRIBE v2, with a small HTTP front.
- The Isaac worker renders a clip, which is the conditioning video.
- The Cosmos worker restyles it into chunks.
- The TRIBE worker writes one prediction per chunk to `/data/predictions`.

Code: [../services/render-score/](../services/render-score/).

**Image.** Build it with an `images:` section in the Fuzzfile, so it is built on the cluster for its own architecture and CUDA version:
- Isaac Sim 6.2
- the Cosmos framework at `c3a2e37`
- TRIBE v2 at `af58661`
- torch with CUDA

**Service.** In `fuzzball/simulaxon.fz`:

| Field | Setting |
|---|---|
| Name | `render-score`, so the app server reaches it at `http://render-score` |
| Mounts | `/data` |
| GPU | `nvidia.com/gpu: 1` |
| Memory | Sized from the picture: 78 of 128 GB on Node A |
| Port | One named port, with a readiness probe on it |
| `persist` | `true` |

**Check:** send one scene to `http://render-score` and get a prediction file under `/data/predictions`. Node A's memory should be near the picture's 78 GB.

## 4. The planner on Node B

- Serve Nemotron Super 120B (NVFP4) with vLLM, as service `planner` in the same Fuzzfile. Use the catalog's general `vllm` entry as the reference for its settings.
- The model file comes from `/data/weights`.
- On GB10's unified memory, start `--gpu-memory-utilization` at 0.7, not vLLM's default 0.9; CIQ's DGX Spark guide gives this value.
- Turn tool calling on (`--enable-auto-tool-choice` with Nemotron's tool-call parser). The app server's agent calls tools.

**Check:** `curl http://planner:<port>/v1/models` from another service lists the model. Node B's memory should be near the picture's 72 GB once the app server runs too.

## 5. The app server on Node B

- Run FastAPI and DuckDB, from [../services/app-server/](../services/app-server/), as service `app-server` in the same Fuzzfile.
- The DuckDB log lives at `/data/log`.
- It calls `http://planner` for the agent and `http://render-score` for previews.
- It submits study workflows to Fuzzball with the token Fuzzball injects into every container (`FB_TOKEN`, `FB_API_HOST`). Each study it starts is recorded as its child: `fuzzball workflow list --parent <app-server workflow id>`.
- Give it an endpoint (`fuzzball endpoint create simulaxon`, with `persistent: true` on the service), so the browser's URL survives redeploys.

**Check:** `curl https://<endpoint>/tools` lists the tools, 60 of them.

## 6. The browser app

- Build `frontend/` with Vite and serve it from the app server. `server.py` already serves a built UI folder when one is present.
- Or run `npm run dev` locally, with the proxy pointed at the endpoint.

**Check:** the interface opens over HTTPS on the agent's chat; New project shows the examples playing; a message to the agent is answered through the planner.

## 7. One study, end to end

Open for the owner: the app runs a project's clips through render-score, one job each, and has no route yet that submits the observer study as a Fuzzball workflow. The study runs as a workflow from its Fuzzfile ([../studies/observer/](../studies/observer/)):
1. Moments and motions.
2. A task array that renders 6 moments × 4 cells (two bodies, two motions).
3. TRIBE on the 24 clips.
4. Analysis.
5. Region maps.
6. The study's dataset, written into the app.

**Check:** 24 clips and 24 predictions under `/data/studies/observer`. In the app, the humanoid project (New project, A robot that moves like a person) runs the same 24 cells through render-score.

**Baseline for the move:** the same 24 clips' predictions, against those computed before the move. Per-vertex r should be about 1.0, since the weights and inputs are the same.

## Placing services on Node A and Node B

Fuzzball places each service on a node with room for it. To hold the picture's split, give each node a provision definition with its own annotation, and request it in each service's `resource.annotations`. The Provisioner Configuration and Fuzzfile Syntax pages cover both.
