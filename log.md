# Log

## Open documents (2026-11-14)
- review   README.md
- review   docs/onboarding.md § 7
- review   docs/wiring-prompt.md § 1-2
- review   docs/spark-transfer.md

## 2026-11-14
- **The Spark runs the 6 pm version.** The freeze: `74f5a3e`, fetched at 6:00:48 pm Chicago, tagged locally `vast-final-2026-11-14`. Port 8790 runs `services/app-server` from branch spark-transfer, which is the freeze plus the Spark Dashboard fix, against the lab's merged store; the dev page on 5176 serves `frontend/`. Same store, same answers: project and tool counts, three projects' samples and results, a time course and the examples all match the research repo's server, read before the switch. The store was backed up first (`backend/data/backup/` in visual-cortex-lab). → docs/spark-transfer.md
- **Plan for moving to the Spark when the VAST server goes down at 6 pm Chicago.** At the owner's word: work from the version most recent as of 6 pm, ready to pull functional UI updates, with a policy for the least painful transfer although the routes differ. The freeze is a fetch at 6 pm and a local tag `vast-final-2026-11-14`. Every route that differs between the cluster and the Spark is switched by a setting, not by code; the two with no Spark counterpart, `/dashboard` and `/api/runs`, are to show only where they answer. The procedure is the `painless-transfer` skill. → docs/spark-transfer.md
- **The lab app and its server replace the data browser, on branch lab-app.** At the owner's word: "it's still on visual cortex lab rather than simulaxon". `frontend/` is the lab app, named Simulaxon; `services/app-server/app_server/` is the lab server (the research repo's vcl and vcl.lab), with every data path read from `SIMULAXON_HOME`. The render-score workers and queue are updated to the copies the lab runs now. Checked on the Spark: the server answers all 60 tools and serves the built app, which opens on the agent's chat with an empty store and plays the examples. Open for the owner: the app has no route that submits the observer study as a Fuzzball workflow (onboarding § 7).
