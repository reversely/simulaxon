# Log

## Open documents (2026-11-14)
- review   README.md
- review   docs/onboarding.md § 7
- review   docs/wiring-prompt.md § 1-2
- decide   branch lab-app: the lab app and server

## 2026-11-14
- **The lab app and its server replace the data browser, on branch lab-app.** At the owner's word: "it's still on visual cortex lab rather than simulaxon". `frontend/` is the lab app, named Simulaxon; `services/app-server/app_server/` is the lab server (the research repo's vcl and vcl.lab), with every data path read from `SIMULAXON_HOME`. The render-score workers and queue are updated to the copies the lab runs now. Checked on the Spark: the server answers all 60 tools and serves the built app, which opens on the agent's chat with an empty store and plays the examples. Open for the owner: the app has no route that submits the observer study as a Fuzzball workflow (onboarding § 7).
