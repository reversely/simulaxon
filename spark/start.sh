#!/bin/bash
# The lab on the Spark, run the way the node runs it: Simulaxon's worker server (services/render-score) with Simulaxon's
# own workers, and Simulaxon's app server sending every job to it. The lab's data, environments, TRIBE cache and Cosmos
# checkpoint stay in visual-cortex-lab, the repo that keeps working without the cluster.
#
#   spark/start.sh          start the worker server (port 8100) and the app server (port 8790), both on this machine only
#   spark/start.sh stop     stop both; their workers end with them
#
# The page is the Vite dev server in frontend/:  LAB_API=http://127.0.0.1:8790 npx vite --host 100.97.186.57 --port 5176
set -e
S=$(cd "$(dirname "$0")/.." && pwd)
V=/home/springbuilt/Repos/visual-cortex-lab
PY=$V/feasibility/.venv/bin/python
LOG=$V/backend/data

stop() {
  for pat in "app_server.lab.serve --port 8790" "services/render-score/server.py"; do   # the app server first: a run in progress is kept and resumes, rather than failing on a vanished worker
    for p in $(pgrep -f "^$PY .*$pat"); do kill "$p"; for i in $(seq 1 20); do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done; done
  done
}

if [ "$1" = stop ]; then stop; exit 0; fi
stop

cd "$S/services/render-score"
SIMULAXON_DATA=$V/backend/data SIMULAXON_ENVS=$V/backend/data/envs TRIBE_CACHE=$V/feasibility/cache_fast \
COSMOS_SRC=$V/feasibility/cosmos-src COSMOS_CHECKPOINT=$V/feasibility/cosmos-src/checkpoints/Cosmos3-Nano-Sim-Transfer \
  setsid nohup $PY "$S/services/render-score/server.py" --host 127.0.0.1 --port 8100 >> $LOG/render_score.log 2>&1 < /dev/null &

cd "$S/services/app-server"
SIMULAXON_HOME=$V SIMULAXON_AGENT=claude PYTHONPATH=. RENDER_SCORE_URL=http://127.0.0.1:8100 \
  setsid nohup $PY -m app_server.lab.serve --port 8790 --db $V/backend/data/lab_main.duckdb >> $LOG/lab_server.log 2>&1 < /dev/null &

for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:8100/health && curl -s -o /dev/null http://127.0.0.1:8790/tools && break; sleep 1; done
echo "worker server: $(curl -s http://127.0.0.1:8100/health)"
echo "app server: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/tools)"
