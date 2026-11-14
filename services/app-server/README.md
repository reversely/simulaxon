# app-server

Node B in [docs/image.png](../../docs/image.png): FastAPI and DuckDB, about 2 GB.
- It serves the browser app.
- It calls the planner at `http://planner` and render-score at `http://render-score`.
- It submits study workflows to Fuzzball.

| File | Does |
|---|---|
| `app_server/server.py` | The HTTP routes the frontend calls, and the agent route |
| `app_server/store.py` | The DuckDB store of datasets |
| `app_server/loaders.py` | Loads a source description into a dataset |
| `app_server/views.py` | Saved views of a dataset |
| `app_server/runs.py` | Starts and stops runs |
| `app_server/agent_tools.py` | The data tools the agent may call |
| `sources/observer_demo.json` | The observer study as a dataset source |

Wiring: [docs/wiring-prompt.md](../../docs/wiring-prompt.md), section 2.
