#!/bin/sh
# Logs a GPU job's GPU readings and busiest processes to its own stdout, for fuzzball/gpu-usage.py to read back with
# `fuzzball workflow log`. Start it from a GPU job's script, before the job's main command:
#   (sh /data/src/simulaxon/fuzzball/gpu-log.sh $$ &)
# The parentheses keep it out of the script's own jobs, so a `wait` in the script does not wait for it. It stops when
# process $$ (the script, or what it `exec`s) exits. GPU_LOG_EVERY sets the interval in seconds (default 15).
#
# Lines, one reading every interval:
#   gpulog <utc time> gpu util=<%> power=<W> temp=<C> sm=<MHz> mem=<container bytes>
#   gpulog <utc time> proc pid=<pid> cpu=<%> rss=<KiB> age=<s> cmd=<command line>
# The GB10 shares memory with the CPU and reports no GPU memory, so mem is the container's cgroup memory. The container
# has its own process namespace, so the processes are this job's only. Images without ps get the same fields from /proc,
# with cpu=-.
#
# Each reading is also appended as one JSON object to
#   /data/log/metrics/gpu/${FB_WORKFLOW_ID}_${FB_JOB_NAME}_${FB_TASK_ID:-0}.jsonl
# for the app's dashboard: t (unix seconds), workflow, job, task, gpu_util_pct, power_w, temp_c, sm_clock_mhz,
# mem_used_bytes, top ([{pid, cpu_pct, rss_kib, cmd}]). A field the GPU or image does not report is left out.
# The container cannot see which node it is on (its hostname is the job name); fuzzball/gpu-usage.py takes the node from
# `fuzzball workflow describe`. GPU_LOG_DIR moves the folder; the file is skipped when the folder cannot be written.
P=${1:-$PPID}
EVERY=${GPU_LOG_EVERY:-15}
TOP=5
DIR=${GPU_LOG_DIR:-/data/log/metrics/gpu}
OUT=$DIR/${FB_WORKFLOW_ID:-local}_${FB_JOB_NAME:-job}_${FB_TASK_ID:-0}.jsonl
mkdir -p "$DIR" 2>/dev/null && touch "$OUT" 2>/dev/null || OUT=

# /sys/fs/cgroup is the host's tree; the job's own memory is under the path /proc/self/cgroup names.
CG=/sys/fs/cgroup$(sed -n 's/^0:://p' /proc/self/cgroup 2>/dev/null)
mem() { cat "$CG/memory.current" 2>/dev/null || echo -; }

procs() {  # pid cpu rss age cmd, busiest first; the snapshot is taken before any filter runs, so only the logger's
           # own shell and ps appear in it, and those are dropped
  if command -v ps >/dev/null 2>&1; then
    snap=$(ps -eo pid=,pcpu=,rss=,etimes=,args= --sort=-pcpu 2>/dev/null)
  else
    snap=$(for d in /proc/[0-9]*; do
      cmd=$(tr '\0' ' ' < $d/cmdline 2>/dev/null) && [ -n "$cmd" ] || continue
      echo "${d#/proc/} - $(awk '/^VmRSS/ {print $2}' $d/status 2>/dev/null) - $cmd"
    done)
    snap=$(printf '%s\n' "$snap" | sort -k3 -n -r)
  fi
  printf '%s\n' "$snap" | awk -v top=$TOP 'NF < 5 || $5 ~ /^(ps|tr|awk|sort)$/ || /gpu-log\.sh/ || /\/proc\/\[0-9\]/ {next} n++ < top'
}

while kill -0 "$P" 2>/dev/null; do
  t=$(date -u +%s)
  now=$(date -u -d "@$t" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)
  gpu=$(nvidia-smi --query-gpu=utilization.gpu,power.draw,temperature.gpu,clocks.sm \
    --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d ' ')
  # Line 1 is the GPU reading, the rest the processes; awk prints the stdout lines and, with OUT set, the JSON object.
  { echo "${gpu:-,,,},$(mem)"; procs; } | awk -v now="$now" -v t="$t" -v out="$OUT" \
    -v wf="$FB_WORKFLOW_ID" -v job="$FB_JOB_NAME" -v task="${FB_TASK_ID:-0}" '
    function q(s) { gsub(/\\/, "\\\\", s); gsub(/"/, "\\\"", s); gsub(/\t/, "\\t", s); gsub(/[\001-\037]/, " ", s); return "\"" s "\"" }
    function n(v) { return v ~ /^[0-9]+(\.[0-9]+)?$/ }
    function f(k, v) { return n(v) ? ", \"" k "\": " (v + 0) : "" }
    NR == 1 {
      split($0, g, ","); for (i = 1; i <= 5; i++) if (g[i] == "") g[i] = "-"
      print "gpulog " now " gpu util=" g[1] " power=" g[2] " temp=" g[3] " sm=" g[4] " mem=" g[5]
      js = "{\"t\": " t ", \"workflow\": " q(wf) ", \"job\": " q(job) ", \"task\": " (task + 0) \
           f("gpu_util_pct", g[1]) f("power_w", g[2]) f("temp_c", g[3]) f("sm_clock_mhz", g[4]) \
           f("mem_used_bytes", g[5]) ", \"top\": ["
      next
    }
    {
      cmd = $0; for (i = 1; i <= 4; i++) sub(/^[ \t]*[^ \t]+/, "", cmd); sub(/^[ \t]+/, "", cmd); sub(/[ \t]+$/, "", cmd)
      print "gpulog " now " proc pid=" $1 " cpu=" $2 " rss=" $3 " age=" $4 " cmd=" cmd
      js = js (NR > 2 ? ", " : "") "{\"pid\": " ($1 + 0) f("cpu_pct", $2) f("rss_kib", $3) ", \"cmd\": " q(cmd) "}"
    }
    END { if (out != "") print js "]}" >> out; fflush() }'
  sleep "$EVERY"
done
