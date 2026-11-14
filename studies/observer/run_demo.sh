#!/bin/bash
# The observer demo, end to end on one Spark (doc 24 § 13). Every stage resumes from its outputs.
#   1 build    observer/motions.py   moments by a fixed rule; recorded and robotic motion for the human and the G1
#   2 render   observer/render.py    Isaac Sim, four clips per moment (waits for 30 GB available before each moment)
#   3 run      egobody/tribe_clips.py  TRIBE v2 on every clip (writes <clip>.tribe.npy; skips clips already done)
#   4 compare  observer/analyse.py   contrasts with baselines
#   5 show     observer/maps.py      contrast maps with TRIBE's plotter
#   6 app      observer/app_dataset.py  the clips, tracks and fields in the app
# relaunch (from feasibility/): setsid nohup bash observer/run_demo.sh > /dev/null 2>&1 < /dev/null &
# log: ~/data/observer/logs/run.log
cd "$(dirname "$0")/.." || exit 1
FEAS=$(pwd); O=~/data/observer; mkdir -p $O/logs; LOG=$O/logs/run.log
log() { echo "$(date '+%F %T') $*" >> $LOG; }
N=${N:-6}
log "start, N=$N"
.venv/bin/python observer/motions.py $N >> $O/logs/motions.log 2>&1; log "motions exit $?"
for mk in $(.venv/bin/python -c "import json; print(' '.join(f\"{m['rec']}:{m['k']}\" for m in json.load(open('$O/moments.json'))['moments']))"); do
  rec=${mk%%:*}; k=${mk##*:}; kk=$(printf '%03d' $k)
  if [ $(ls $O/clips/${rec}_${kk}_*.mp4 2>/dev/null | wc -l) -ge 4 ]; then log "render $rec $k: done before"; continue; fi
  .venv/bin/python -c "import sys; sys.path.insert(0, '$FEAS/egobody'); import memwait; memwait.wait(30, 'observer render')"
  ( cd isaac && source env.sh && .venv/bin/python ../observer/render.py $rec $k ) > $O/logs/render_${rec}_${kk}.log 2>&1
  log "render $rec $k exit $? ($(ls $O/clips/${rec}_${kk}_*.mp4 2>/dev/null | wc -l) clips)"
done
.venv/bin/python egobody/tribe_clips.py $O/clips 4 >> $O/logs/tribe.log 2>&1; log "tribe exit $? ($(ls $O/clips/*.tribe.npy 2>/dev/null | wc -l) predictions)"
.venv/bin/python observer/analyse.py > $O/logs/analyse.log 2>&1; log "analyse exit $?"
.venv/bin/python observer/maps.py > $O/logs/maps.log 2>&1; log "maps exit $?"
python3 observer/app_dataset.py > $O/logs/app.log 2>&1; log "app exit $?"
log "done"
