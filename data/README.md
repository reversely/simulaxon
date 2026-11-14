# /data

The VAST volume in [docs/image.png](../docs/image.png), mounted at `/data` by every service. Nothing in this folder is committed.

| Folder | Holds | Written by |
|---|---|---|
| `/data/weights` | TRIBE v2, V-JEPA 2, Cosmos3-Nano-Sim-Transfer with its tokenizer and VAE, Nemotron Super 120B (NVFP4) | Onboarding step 2 |
| `/data/chunks` | Cosmos output, one chunk per restyled clip | render-score |
| `/data/predictions` | TRIBE output, one cortical map per second | render-score |
| `/data/log` | The DuckDB log (`datasets.duckdb`) | app-server |
| `/data/egobody` | EgoBody: the six recordings, scene meshes, SMPL-X fits and `work/` (episodes, kinematics, Isaac renders), in the Spark's `~/data/egobody` layout | Onboarding step 2, from the Spark |
| `/data/body_models/models/smplx` | SMPL-X v1.1 body model | Onboarding step 2, from the Spark |
| `/data/observer` | The observer study's clips, predictions and results | The observer study's workflow |
| `/data/studies/<study>` | Inputs and outputs of later studies | The study's workflow |

The study code reads `~/data/egobody`, `~/data/body_models` and `~/data/observer`, so each container links `~/data` to `/data`.

The shared provisioner holds sample data and sample models.
