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
- Your CLI is logged in: `fuzzball context login`, then `fuzzball group use <team group>`. Install and context setup for the hackathon cluster: [fuzzball-cli.md](fuzzball-cli.md).
- A Hugging Face token is stored as a secret: `fuzzball secret create secret://user/hf-token --type hf '{"token":"hf_…"}'`.

## 1. The volume at `/data`

- On the hackathon cluster the organizers provide a storage provisioner per team (`team13`, NFS on the VAST export) and a read-only `datasets` volume on the `shared` provisioner. Elsewhere, add the provisioner yourself (Volume Configuration and Management, Driver Types).
- Create one persistent volume, mounted at `/data` by every service: `fuzzball volume create team13 simulaxon-data`.
- Run [../fuzzball/check-data.fz](../fuzzball/check-data.fz). It makes the folders in [../data/README.md](../data/README.md).

**Check:** the job's log lists `chunks log predictions studies weights` under `/data`.

## 2. Weights and study data on `/data`

| What | Goes to | Source | Used by |
|---|---|---|---|
| TRIBE v2 | `/data/weights/facebook--tribev2` | `hf://facebook/tribev2` | render-score |
| V-JEPA 2 | `/data/weights/facebook--vjepa2-vitg-fpc64-256` | `hf://facebook/vjepa2-vitg-fpc64-256` | render-score |
| Cosmos3-Nano-Sim-Transfer | `/data/weights/nvidia--cosmos3-nano-sim-transfer` | `hf://nvidia/Cosmos3-Nano-Sim-Transfer` | render-score |
| Cosmos3-Nano text tokenizer, Wan2.2 VAE | `/data/weights/nvidia--cosmos3-nano/text_tokenizer`, `/data/weights/wan-ai--wan2.2-ti2v-5b` | Single files at the revisions `cosmos_worker.py` pins | render-score |
| Nemotron 3 Super 120B, NVFP4 | `/data/weights/nvidia--nemotron-3-super-120b-a12b-nvfp4` | `hf://nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` | planner |
| SMPL-X v1.1 body model | `/data/studies/observer/body_models` | The Spark's `~/data/body_models` | observer study |
| EgoBody: the six recordings, scene meshes, fits and `work/` | `/data/studies/observer/egobody` | The Spark's `~/data/egobody` | observer study |
| Observer outputs from the Spark | `/data/studies/observer/observer` | The Spark's `~/data/observer` | baseline, app |

The weights come from Hugging Face. Every repo above is public, so no token is needed. Run the five files in [../fuzzball/weights/](../fuzzball/weights/) one at a time, each after the previous finishes. Thirteen transfers in one workflow stalled its volume stage until Fuzzball cancelled it.

The study code reads the Spark's layout under `~/data` (`motion_lib.py`, `body_scene.py`, `g1_execute.py`), so the study data keeps that layout at `/data/studies/observer`, and each container links `~/data` there. The SMPL-X and EgoBody files sit behind registration and come from the Spark: start [../fuzzball/receive.fz](../fuzzball/receive.fz) and stream a tar into it with `fuzzball workflow exec` (see the file's header). The copy that ran on 2026-11-14 took 1.76 GB, 77,457 entries, in 23 minutes over a home connection.

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

**Image and environments.** The hackathon cluster builds no images (`features.enableWorkflowImageBuilds` is off), runs containers as the team user, and mounts only NVIDIA's compute libraries into GPU containers (`/gpu-libs`). So:
- The service runs on NVIDIA's `nvcr.io/nvidia/isaac-sim:6.2.0` (arm64), which carries Isaac Sim's system libraries.
- [../fuzzball/render-env.fz](../fuzzball/render-env.fz) puts the rest on `/data` once:
  - NVIDIA's graphics libraries for the host driver 580.173.02 (Vulkan, EGL, RTX, OptiX), from NVIDIA's installer, in `/data/envs/nvidia-gl`.
  - `/data/envs/isaac` (Isaac Sim 6.2) and `/data/envs/tribe` (TRIBE v2 at `af58661`), from lock files frozen from the Spark in [../services/render-score/env/](../services/render-score/env/).
  - `/data/envs/cosmos`, from `cosmos-framework` at `c3a2e37` and its `uv.lock`. The Spark's `feasibility/cosmos-src` is a clean checkout of that commit, so nothing is vendored.
  - A Hugging Face cache in `/data/weights/hf/hub`, symlinked to the downloaded weights at the revisions the workers pin.

**Service.** Rendering runs as batch tasks the app launches (`fuzzball/observer.fz`), each reading and writing `/data`, as in the team's sketch. For instant previews, `fuzzball/render-score.fz` runs the same workers as an always-on service:

| Field | Setting |
|---|---|
| Name | `render-score`, so the app server reaches it at `http://render-score` |
| Mounts | `/data` |
| GPU | `nvidia.com/gpu: 1` |
| Memory | 96 GiB requested; the picture's 78 GB plus headroom |
| Port | One named port, with a readiness probe on it |
| `persist` | `true` |

**Check:** send one scene to `http://render-score` and get a prediction file under `/data/predictions`. Node A's memory should be near the picture's 78 GB.

## 4. The planner on Node B

- Serve Nemotron Super 120B (NVFP4) with vLLM, as service `planner` in the same Fuzzfile. Use the catalog's general `vllm` entry as the reference for its settings.
- The model file comes from `/data/weights`.
- The settings come from NVIDIA's model card, section "vLLM on DGX Spark": vLLM `v0.27.1`, Marlin NVFP4 kernels, fp8 KV cache, the `super_v3` reasoning parser shipped in the model repo. `--gpu-memory-utilization` starts at 0.85, between CIQ's DGX Spark guide (0.7) and the model card (0.9), since the 80 GB of weights leave little KV cache at 0.7.
- Turn tool calling on (`--enable-auto-tool-choice` with Nemotron's tool-call parser). The app server's agent calls tools.

**Check:** `curl http://planner:<port>/v1/models` from another service lists the model. Node B's memory should be near the picture's 72 GB once the app server runs too.

## 5. The app server on Node B

- Run FastAPI and DuckDB, from [../services/app-server/](../services/app-server/), as service `app-server` in the same Fuzzfile.
- The DuckDB log lives at `/data/log`.
- It calls `http://planner` for the agent and `http://render-score` for previews.
- It submits study workflows to Fuzzball with the token Fuzzball injects into every container (`FB_TOKEN`, `FB_API_HOST`). Each study it starts is recorded as its child: `fuzzball workflow list --parent <app-server workflow id>`.
- Give it a workflow endpoint (`type: subdomain`, `scope: group`). Fuzzball 4.3 has no persistent endpoints, so the URL changes with each new workflow: `fuzzball workflow endpoints <workflow-id>`. The endpoint's certificate comes from the cluster's private CA, so a browser warns; `fuzzball workflow port-forward <workflow-id> app-server 18791:8791` opens the app at `http://127.0.0.1:18791` without it.

**Check:** `curl http://127.0.0.1:18791/api/datasets` through the port-forward returns the dataset list.

## 6. The browser app

- Build `frontend/` with Vite and serve it from the app server. `server.py` already serves a built UI folder when one is present.
- Or run `npm run dev` locally, with the proxy pointed at the endpoint.

The `build-ui` job in `simulaxon.fz` builds it into `/data/app/dist`, outside the source tree, so refreshing the code on the volume leaves the running app's UI in place.

**Check:** the interface opens, lists the datasets, and the agent box answers through the planner.

## 7. One study, end to end

From the app, start the observer study ([../studies/observer/](../studies/observer/)). The app server submits it as a workflow:
1. Moments and motions.
2. A task array that renders 6 moments × 4 cells (two bodies, two motions).
3. TRIBE on the 24 clips.
4. Analysis.
5. Region maps.
6. The study's dataset, written into the app.

**Check:** 24 clips and 24 predictions under `/data/studies/observer`; the dataset opens in the app with a video and a TRIBE track on each sample.

**Baseline for the move:** the same 24 clips' predictions, against those computed before the move. Per-vertex r should be about 1.0, since the weights and inputs are the same.

## Placing services on Node A and Node B

Fuzzball places each service on a node with room for it. To hold the picture's split, give each node a provision definition with its own annotation, and request it in each service's `resource.annotations`. The Provisioner Configuration and Fuzzfile Syntax pages cover both.
