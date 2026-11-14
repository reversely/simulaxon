"""Where the app server finds things. Each setting comes from the environment, with the cluster's layout as default.

  SIMULAXON_DATA    data root; dataset files, media and the DuckDB log live under it (default /data)
  SIMULAXON_UI      built frontend to serve (default frontend/dist in the repo)
  PLANNER_URL       OpenAI-compatible API of the planner (default http://planner:8000/v1)
  PLANNER_MODEL     model name the planner serves (default nvidia/nemotron-3-super)
  FUZZBALL          the Fuzzball CLI; inside a workflow it reads FB_TOKEN and FB_API_HOST (default fuzzball)
  GRAFANA_URL       Grafana as the browser reaches it, where /dashboard sends people (default http://localhost:13000,
                    which `sh fuzzball/grafana.sh` forwards to the observability workflow)
"""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]                      # the repository
APP = Path(__file__).resolve().parents[1]                       # services/app-server
DATA = Path(os.environ.get('SIMULAXON_DATA', '/data'))
UI = Path(os.environ.get('SIMULAXON_UI', ROOT / 'frontend' / 'dist'))
SOURCES = APP / 'sources'
RUNS = APP / 'runs'
PLANNER_URL = os.environ.get('PLANNER_URL', 'http://planner:8000/v1').rstrip('/')
PLANNER_MODEL = os.environ.get('PLANNER_MODEL', 'nvidia/nemotron-3-super')
FUZZBALL = os.environ.get('FUZZBALL', 'fuzzball')
GRAFANA_URL = os.environ.get('GRAFANA_URL', 'http://localhost:13000').rstrip('/')
