#!/bin/sh
# Opens the Simulaxon Grafana at http://localhost:13000: finds the running `observability` workflow (its ID changes on
# every restart) and forwards its grafana service to this machine. Ctrl-C closes it.
#   sh fuzzball/grafana.sh [local-port]
PORT=${1:-13000}
W=$(fuzzball workflow list | awk -F'|' '$4 ~ /Started/ && $5 ~ /^ *observability *$/ {gsub(/ /, "", $1); print $1; exit}')
[ -n "$W" ] || { echo "No running observability workflow. Start one: fuzzball workflow start -n observability fuzzball/observability.fz" >&2; exit 1; }
echo "Grafana from workflow $W at http://localhost:$PORT"
exec fuzzball workflow port-forward "$W" grafana "$PORT:13000"
