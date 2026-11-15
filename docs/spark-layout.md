# The lab on the Spark

How the lab app runs on the Spark (15 Nov 2026 onward), the same way it runs on the cluster node.

## What runs

| Piece | Code | Started by |
| --- | --- | --- |
| Worker server, `127.0.0.1:8100` | `services/render-score/server.py` | `spark/start.sh` |
| Isaac, TRIBE and Cosmos workers | `services/render-score/{isaac,tribe,cosmos}/` | the worker server, on first use |
| Study code the workers and the app import | `studies/observer/` | |
| App server, `127.0.0.1:8790` | `services/app-server/` | `spark/start.sh`; sends every job to the worker server (`RENDER_SCORE_URL`) |
| The page, http://100.97.186.57:5176 | `frontend/` | `LAB_API=http://127.0.0.1:8790 npx vite --host 100.97.186.57 --port 5176`, in `frontend/` |

All code comes from this repo. `spark/start.sh` starts or restarts the two servers; `spark/start.sh stop` stops them and their workers. A run in progress resumes on its own after a restart, and clips already made come from cache.

## What stays in visual-cortex-lab

visual-cortex-lab (`~/Repos/visual-cortex-lab`) is the app's home folder here (`SIMULAXON_HOME`), as `/data` is on the node. It holds no code the app runs:

- `backend/data/`: the database (`lab_main.duckdb`), files, fetched datasets, logs (`lab_server.log`, `render_score.log`), and `envs/`, which links the three environments (`isaac`, `tribe`, `cosmos`) the workers run in.
- `feasibility/`: the environments themselves, the TRIBE cache (`cache_fast`), the Cosmos source and checkpoint (`cosmos-src`), TRIBE's source (`tribev2-src`, for the region masks), the search indexes and finished runs.

visual-cortex-lab also keeps its own research scripts and their copies of the study and TRIBE code (`feasibility/observer/`, `feasibility/fast_tribe.py`, `feasibility/isaac/g1_*.py`), so its research runs without this repo or the cluster. The app does not use those copies.

## Branches

`spark-transfer` holds the Spark's work since the 6 pm freeze on 14 Nov; `main` is the node's.
