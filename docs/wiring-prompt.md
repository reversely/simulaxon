# Wiring, in one agent prompt

Give the prompt below, unchanged, to a coding agent that has this repo checked out on the cluster and the Fuzzball CLI logged in. Before running it, finish onboarding steps 0 to 2 ([onboarding.md](onboarding.md)), so that `/data` and the weights exist.

```text
Wire Simulaxon so that it runs as drawn in docs/image.png. Read README.md, docs/image.png and docs/onboarding.md first. Change wiring only: paths, calls, launch and Fuzzfiles. Do not change how the frontend looks.

1. Frontend (frontend/)
   - vite.config.ts proxies /api and /media to http://127.0.0.1:8791. Point both at the app server, either as a service on the cluster or through the endpoint while developing.
   - It calls these routes, which must keep working:
     GET /api/datasets
     POST /api/datasets/load
     GET /api/datasets/{name}
     POST /api/datasets/{name}/view
     GET /api/datasets/{name}/samples/{sid}
     GET /api/datasets/{name}/samples/{sid}/track
     GET /api/datasets/{name}/samples/{sid}/track_full
     POST /api/agent
     GET /api/runs
     POST /api/runs/{name}/start
     POST /api/runs/{name}/stop
     GET /media/{path}
     the static files /brain/fsaverage5.json and /brain/fsaverage5.bin

2. App server (services/app-server/app_server/; it was the package vcl.data)
   - server.py: ROOT = parents[3] and UI = ROOT/app/dist. Serve the built frontend from frontend/dist. Resolve data paths under /data, and media under /data.
   - server.py, POST /api/agent: it runs `claude -p` with an MCP config that starts `python -m vcl.data.agent_tools`. Replace that with a tool-calling loop against the planner's OpenAI-compatible API at http://planner/v1. Use the same tools as agent_tools.py, the same AGENT_SYSTEM prompt, and the same reply shape: {reply, tool_calls, show}.
   - store.py: DB = parents[2]/data/datasets.duckdb. Move it to /data/log/datasets.duckdb.
   - loaders.py: sources are read relative to ROOT. Read them relative to /data. The one source kept is sources/observer_demo.json.
   - runs.py: it runs the commands in backend/runs/*.json as local subprocesses. Submit each run as a Fuzzball workflow with the injected FB_TOKEN and FB_API_HOST (`fuzzball workflow start <fuzzfile>`); report status from `fuzzball workflow describe`; stop with `fuzzball workflow stop`.
   - Run it as the service app-server in fuzzball/simulaxon.fz: FastAPI under uvicorn, /data mounted, a persistent endpoint named simulaxon.

3. render-score (services/render-score/)
   - One container: Isaac Sim 6.2, the Cosmos framework at c3a2e37, TRIBE v2 at af58661, and the three warm workers. Each worker reads JSON lines on stdin and answers one JSON line per job; jobs.py is their queue.
   - Drop jobs.py's Modal remote lane and its memory juggling: Fuzzball sizes the container.
   - Add a small HTTP front named render-score: a scene goes in; render (isaac/), restyle (cosmos/), predict (tribe/); the paths of the chunk and prediction files under /data come out.
   - tribe/tribe_worker.py: it imports fast_tribe from parents[2]/feasibility, with cache parents[2]/feasibility/cache_fast. Import it from tribe/; put the cache at /data/weights.
   - cosmos/cosmos_worker.py: SRC is feasibility/cosmos-src, CK is SRC/checkpoints/Cosmos3-Nano-Sim-Transfer, WORK is feasibility/out/cosmos_worker. Set SRC to the pinned source in the image, CK to /data/weights, WORK to /data/chunks.
   - isaac/isaac_body_worker.py: it adds feasibility/observer to sys.path for body_scene.py, which now lives in studies/observer/. isaac/isaac_scene_worker.py uses isaac/render_fit.py. Both need OMNI_KIT_ACCEPT_EULA=YES and the libgomp preload in the container's environment.
   - Run it as the service render-score in fuzzball/simulaxon.fz: nvidia.com/gpu: 1, /data mounted, persist: true, a readiness probe.

4. Planner
   - Service planner in fuzzball/simulaxon.fz: vLLM serving Nemotron Super 120B (NVFP4) from /data/weights, OpenAI-compatible, with tool calling on, and --gpu-memory-utilization starting at 0.7.

5. The observer study (studies/observer/)
   - Paths to change:
     - render.py, analyse.py and body_scene.py add ../egobody, ../isaac, ../observer and ../tribev2-src to sys.path. All their imports are now in this folder, plus TRIBE v2 in the image.
     - ~/data/egobody, ~/data/body_models and ~/data/observer become /data/studies/observer.
   - run_demo.sh uses .venv, isaac/env.sh and memwait. Replace it with fuzzball/observer.fz:
     - motions (CPU)
     - a task array of renders, one task per moment from moments.json
     - TRIBE over the clips
     - analyse, then maps, then app_dataset
     - retry on node loss
     - outputs written to /data/studies/observer
   - The app server starts it through POST /api/runs/{name}/start.

6. Placement
   - render-score on Node A; planner and app-server on Node B, through node annotations requested in resource.annotations.

Done when:
- every check in docs/onboarding.md passes, steps 3 to 7;
- the browser shows the observer study's dataset;
- the agent box answers through the planner;
- `fuzzball workflow list --parent <app-server workflow id>` lists the study run.
Report each check with its output.
```
