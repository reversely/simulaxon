# /data

The VAST volume in [docs/image.png](../docs/image.png), mounted at `/data` by every service. Nothing in this folder is committed.

| Folder | Holds | Written by |
|---|---|---|
| `/data/weights` | TRIBE v2, V-JEPA 2, Cosmos3-Nano-Sim-Transfer with its tokenizer and VAE, Nemotron Super 120B (NVFP4) | Onboarding step 2 |
| `/data/chunks` | Cosmos output, one chunk per restyled clip | render-score |
| `/data/predictions` | TRIBE output, one cortical map per second | render-score |
| `/data/log` | The DuckDB log (`datasets.duckdb`) | app-server |
| `/data/weights/hf/hub` | A Hugging Face cache made of symlinks to the folders above, at the revisions the workers pin | `fuzzball/render-env.fz` |
| `/data/studies/observer` | The Spark's `~/data` for the observer study: `egobody/` (the six recordings, their scene meshes, SMPL-X fits, calibrations, gaze and `work/`), `body_models/`, `robots/`, and `observer/` (the Spark's 24 clips, predictions and results) | Onboarding step 2, from the Spark |
| `/data/studies/observer/cluster-run` | The observer study's outputs from Fuzzball | `fuzzball/observer.fz` |
| `/data/envs` | render-score's environments (`isaac`, `tribe`, `cosmos`), their Pythons, and NVIDIA's graphics libraries (`nvidia-gl`) | `fuzzball/render-env.fz` |
| `/data/src` | The repo (`simulaxon`) and `cosmos-framework` at `c3a2e37` | `fuzzball/receive.fz`, `fuzzball/render-env.fz` |
| `/data/app/dist` | The built frontend | `fuzzball/simulaxon.fz`, job `build-ui` |

The study code reads `~/data/egobody`, `~/data/body_models` and `~/data/observer`, so each container links `~/data` to `/data/studies/observer`.

The shared provisioner holds sample data and sample models.
