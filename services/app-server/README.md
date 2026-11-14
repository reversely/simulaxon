# app-server

Node B in [docs/image.png](../../docs/image.png): FastAPI and DuckDB.
- It serves the browser app and every tool the app and the agent call.
- It calls the planner at `http://planner` for the agent and `render-score` for renders, restyles and TRIBE.
- Run it: `SIMULAXON_HOME=/data PYTHONPATH=. python -m app_server.lab.serve --port 8790 --db /data/log/lab.duckdb`.

| File | Does |
|---|---|
| `app_server/home.py` | Where the data and research tools live: `SIMULAXON_HOME` |
| `app_server/server.py` | `/tools`, `/tools/{name}` and the `/events` stream over the one tool registry |
| `app_server/store.py` | The DuckDB store: every row, every step, undo |
| `app_server/jobs.py` | The queue and its warm workers, by lane |
| `app_server/lab/serve.py` | The app: chats, uploads, files, thumbnails, the built frontend |
| `app_server/lab/tools.py` | The lab's tools: projects, papers, datasets, regions, experiments, runs, examples |
| `app_server/lab/sessions.py` | Chats with the agent, in discuss or all-the-way-through mode |
| `app_server/lab/experiment.py` | Experiments from any paper and any stimuli: trials, Cosmos, TRIBE, baselines |
| `app_server/lab/runner.py` | Runs a project's clips and analyses |
| `app_server/lab/preview.py` | One render and TRIBE read, and the connectors for Isaac, TRIBE and Cosmos |
| `app_server/lab/papers.py`, `datasets.py` | Finding and fetching papers and open datasets |
| `app_server/lab/regions.py`, `maps.py` | Brain areas from the HCP and Destrieux atlases, and brain maps |
| `app_server/lab/templates.py`, `plans.py`, `worlds.py`, `selection.py` | Project templates, plans, Isaac worlds, stimulus selection |
| `app_server/lab/examples.py` | The seeded examples: classic experiments with what has run here |
| `app_server/lab/demos.py`, `demo_writer.py`, `demo_data/` | Demos that play the app through its own tool calls |
| `app_server/scene/` | Scenes: import, layout, USD |

Wiring: [docs/wiring-prompt.md](../../docs/wiring-prompt.md), section 2.
