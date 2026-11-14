# Moving to the Spark when the VAST server goes down

The owner (2026-11-14): "You're going to need to work on the version that is most recent as of 6 pm because the VAST server is going down. Please be prepared to pull functional UI updates and organize a policy for the least painful transfer, though the routes are different."

The procedure behind this plan is the `painless-transfer` skill (`~/.claude/skills/painless-transfer/SKILL.md`).

## 1. The version to work from

| | |
|---|---|
| Freeze time | 6:00 pm Chicago, 14 Nov 2026 (00:00 UTC, 15 Nov) |
| How | At 6:00 pm, one `git fetch` records every branch and the last commits on `main`. A **local** tag, `vast-final-2026-11-14`, marks `origin/main` as it was then |
| Last seen before the freeze | `038e743` fix(app-server): give the lab ffmpeg on the cluster, 5:35 pm |

Pushing the tag to GitHub is the owner's call.

## 2. Before the server goes down: the owner's steps

Run these on the VAST machine, in the Simulaxon checkout:
```bash
git status --short; git stash list
git log --branches --not --remotes --oneline     # commits that are not pushed
git push --all origin                             # only if the line above printed anything
du -sh /data/log /data/studies /data/backend/data/sessions 2>/dev/null   # data that exists only there
```
The store at `/data/log/lab.duckdb`, the study outputs and the chats exist only on the cluster. Copying them is the owner's decision. The Spark keeps its own store: `lab_main.duckdb`, the lab's store with the harness merged in.

## 3. What changed on `main` since the lab app went in

| Area | Commits | Carried over to the Spark |
|---|---|---|
| UI | A Dashboard link in the header; large uploads sent gzipped; `/api` and `/dashboard` added to the dev proxy | Yes, with the same code. The Dashboard link shows only where Grafana answers (§ 5) |
| App logic | Undo takes back a whole step and leaves nothing behind failed tools; uploads stream to disk | Yes, with the same code |
| Agent | The planner (Nemotron, OpenAI-compatible) runs the lab's chats on the cluster | Present. The Spark keeps Claude: `SIMULAXON_AGENT=claude` |
| Renders | Previews and runs go to render-score's `POST /job`; render-score runs the same queue file | Present. The Spark uses its own warm workers when `RENDER_SCORE_URL` and `FB_WORKFLOW_ID` are unset |
| Cluster only | Fuzzball Fuzzfiles, the planner's speculative decoding, Grafana and Prometheus, the observer study as a workflow | Kept in the repo; nothing on the Spark runs them |

No database change: the store code changed only how Undo works, so the Spark's store opens as it is. The server's packages are already in the Spark's environment. Three are at slightly older versions than `requirements.txt` asks for: fastapi 0.162 against 0.163, numpy 2.2.6 against 2.5.4, pydantic 2.14.2 against 2.14.3.

## 4. The routes, cluster against Spark

| What | On the cluster | On the Spark | Switched by |
|---|---|---|---|
| Renders, TRIBE, Cosmos | render-score, `POST /job` on port 8100 | Warm workers started by the app server's own queue | `RENDER_SCORE_URL`, `FB_WORKFLOW_ID`, both unset here |
| The agent | Planner at `http://planner:8000/v1` | `claude -p` with the lab's tool server | `SIMULAXON_AGENT=claude`; `PLANNER_URL` unset |
| Data and research tools | `/data` | `~/Repos/visual-cortex-lab` | `SIMULAXON_HOME`, `SIMULAXON_DATA` |
| Store | `/data/log/lab.duckdb` | `backend/data/lab_main.duckdb` | `--db` |
| Address | `0.0.0.0:8791`, endpoint `simulaxon` | `127.0.0.1:8790`; the dev page on the tailnet at port 5176 | `--host`, `--port`; `LAB_API` for the dev page |
| Dashboard, `/dashboard` | Grafana, forwarded by `fuzzball/grafana.sh` | None: the link is hidden and `/dashboard` answers 404 | `GRAFANA_URL`, set empty here |
| Studies as workflows, `/api/runs` | Fuzzball CLI | None, since the Fuzzball CLI isn't installed | `FUZZBALL` |

## 5. Policy

1. **One source of truth.** After the freeze, app work lands in this repo: `frontend/` and `services/app-server/`. The app copy in visual-cortex-lab (`archive/app_v1/`, `backend/vcl/`) is frozen for app code; research scripts stay there. Checked at 5:40 pm: that copy has nothing newer than `main`. The only differences are `main`'s own additions.
2. **Places differ by settings, never by forked code.** Every row of § 4 is an environment variable with a default. A change made for one place reads its setting and works in the other.
3. **No dead controls.** A control that needs a cluster-only route shows only where that place has the route. The Dashboard link shows only when `GRAFANA_URL` is set, and the Spark sets it empty; done on this branch. The lab app has no control for `/api/runs`.
4. **Pulling more UI updates.** If work continues on another copy after the freeze, each commit comes over as a patch with its paths mapped (the skill, § 4), on a branch, and merges after the checks in § 6.
5. **Never force-push, and never rewrite others' commits.** Work goes on branches with pull requests.

## 6. Switching the Spark to this version

Once the freeze tag exists:
```bash
cd ~/Repos/simulaxon && git switch main && git merge --ff-only vast-final-2026-11-14
cd frontend && npm ci && npx vite build
cd ../services/app-server
V=~/Repos/visual-cortex-lab
SIMULAXON_HOME=$V SIMULAXON_DATA=$V/backend/data SIMULAXON_AGENT=claude GRAFANA_URL= PYTHONPATH=. \
  $V/feasibility/.venv/bin/python -m app_server.lab.serve --port 8790 --db $V/backend/data/lab_main.duckdb
```
This takes over port 8790 from the research repo's server, after these steps in order:
1. Test the frozen version against a scratch home first: an empty store and chat folder, with links to the files. A server that resumes runs and chats at start must not touch live ones in a test.
2. Check: type-check and build; all tools answer; the page opens at 1394 × 749 with no overlapping text; the examples play; the Room of the last finished project shows its trials and time course; a known project's numbers match the research repo's server.
3. Stop the research repo's server only when no run is going, back up `lab_main.duckdb`, and start the frozen version on 8790.
4. Point the dev page on 5176 at `frontend/` in this repo.
