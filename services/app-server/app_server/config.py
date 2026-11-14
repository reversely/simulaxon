"""Where the app server finds things. Each setting comes from the environment, with the cluster's layout as default.

  SIMULAXON_DATA    data root; dataset files, media and the DuckDB log live under it (default /data)
  SIMULAXON_UI      built frontend to serve (default frontend/dist in the repo)
  PLANNER_URL       OpenAI-compatible API of the planner (default http://planner:8000/v1)
  PLANNER_MODEL     model name the planner serves (default nvidia/nemotron-3-super)
  FUZZBALL          the Fuzzball CLI; inside a workflow it reads FB_TOKEN and FB_API_HOST (default fuzzball)
  RENDER_SCORE_URL  render-score's base URL, where previews and runs render (render_score_url() finds it when unset)
  GRAFANA_URL       Grafana as the browser reaches it, where /dashboard sends people (default http://localhost:13000,
                    which `sh fuzzball/grafana.sh` forwards to the observability workflow). Set it empty where there is
                    no Grafana, such as the Spark: the app then shows no Dashboard link
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


class _RenderScore:
    """render-score's base URL. RENDER_SCORE_URL when set; otherwise, inside a Fuzzball workflow, the newest running
    workflow with a render-score service, which any workflow in the group reaches as render-score.<workflow id>:8100.
    The answer is kept until a job finds it unreachable (forget), since a restart of render-score changes the ID."""
    def __init__(self): self.url, self.at = None, 0.0

    def forget(self): self.url = None

    def __call__(self) -> str:
        import json, subprocess, time
        if os.environ.get('RENDER_SCORE_URL'): return os.environ['RENDER_SCORE_URL'].rstrip('/')
        if self.url and time.time() - self.at < 600: return self.url
        try:
            listed = json.loads(subprocess.run([FUZZBALL, 'workflow', 'list', '-o', 'json'], capture_output=True, text=True, timeout=60).stdout or '[]')
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return self.url or ''
        for w in sorted(listed, key=lambda w: w.get('createTime', ''), reverse=True):
            if 'STARTED' not in str(w.get('status', '')): continue
            if any(j.get('name') == 'render-score' for j in (w.get('jobs') or [])) or w.get('name') == 'render-score':
                self.url, self.at = f"http://render-score.{w['id']}:8100", time.time(); return self.url
        return ''


render_score_url = _RenderScore()
