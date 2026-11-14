#!/bin/bash
# Opens the running Simulaxon app at http://127.0.0.1:18791 and keeps it there across restarts.
#
# Finds the newest running workflow named "simulaxon", forwards its app-server port 8791 to 127.0.0.1:18791, and
# checks every 30 s: when a newer simulaxon workflow replaces it, or the forward drops, it forwards again. Fuzzball
# 4.3 has no persistent endpoints and its endpoint hostnames use the cluster's private CA, so this is the stable
# address. Uses your own CLI login; stores nothing. Stop with Ctrl-C.
#
# usage: fuzzball/open-app.sh [local-port]
FB=${FUZZBALL:-fuzzball}; PORT=${1:-18791}; WF=""; PF=""
trap '[ -n "$PF" ] && kill $PF 2>/dev/null; exit 0' INT TERM

current() {   # the newest simulaxon workflow whose status is started
  "$FB" workflow list --name simulaxon -o json 2>/dev/null | python3 -c '
import json, sys
w = [x for x in json.load(sys.stdin) if x.get("name") == "simulaxon" and x.get("status") == "STAGE_STATUS_STARTED"]
print(max(w, key=lambda x: x["createTime"])["id"] if w else "")'
}

while :; do
  NEW=$(current)
  if [ -z "$NEW" ]; then
    [ -n "$PF" ] && kill $PF 2>/dev/null; PF=""; WF=""
    echo "$(date +%H:%M:%S) no running simulaxon workflow; checking again in 30 s"
  elif [ "$NEW" != "$WF" ] || ! kill -0 "$PF" 2>/dev/null; then
    [ -n "$PF" ] && kill $PF 2>/dev/null
    "$FB" workflow port-forward "$NEW" app-server "$PORT:8791" > /dev/null 2>&1 &
    PF=$!; WF=$NEW
    echo "$(date +%H:%M:%S) http://127.0.0.1:$PORT is workflow $NEW"
  fi
  sleep 30
done
