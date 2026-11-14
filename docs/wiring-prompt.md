# Wiring, in one agent prompt

Give the prompt below, unchanged, to a coding agent that has this repo checked out on the cluster and the Fuzzball CLI logged in. Before running it, finish onboarding steps 0 to 2 ([onboarding.md](onboarding.md)), so that `/data` and the weights exist.

```text
Wire Simulaxon so that it runs as drawn in docs/image.png. Read README.md, docs/image.png and docs/onboarding.md first. Change wiring only: paths, calls, launch and Fuzzfiles. Do not change how the frontend looks.

1. Frontend (frontend/)
   - vite.config.ts proxies /tools, /events (WebSocket), /agent, /datasets, /files, /out and /thumb to LAB_API, default http://127.0.0.1:8790. Point LAB_API at the app server, as a service on the cluster or through the endpoint while developing.
   - It calls these routes, which must keep working:
     GET /tools                                   every tool, with its resource and verb
     POST /tools/{name}                           one tool call: JSON arguments, header X-Actor: person
     WebSocket /events                            one message per store write, run progress and job progress
     POST /agent/sessions                         a new chat: {text, mode: discuss or through, project_id?}
     GET /agent/sessions?project_id=              chats, optionally one project's
     GET /agent/sessions/{sid}                    one chat's turns, replies and tool calls
     POST /agent/sessions/{sid}/message           the person's next message: {text, mode}
     POST /agent/sessions/{sid}/stop
     POST /datasets/upload?name=&dataset_id=      a file a person adds in a chat, raw body
     GET /files/{path}, /out/{path}, /thumb/{path}  stimuli, clips, renders and thumbnails

2. App server (services/app-server/app_server/; it was the packages vcl and vcl.lab in the research repo)
   - home.py: SIMULAXON_HOME, default /data, holds backend/data and feasibility/. Lay them out under /data, or point each use of HOME at its own /data folder:
     backend/data/files      stimuli, trial clips, example clips, papers' text, uploads (served at /files)
     backend/data/fetched    datasets the agent fetches; datasets.py keeps 60 GB of disk free (FLOOR_GB)
     backend/data/sessions   chats with the agent, one JSON file each
     feasibility/tribev2-src TRIBE's source, read by regions.py for the HCP and Destrieux atlases
     feasibility/indexes     the asset and scene search indexes (search.py, records.py)
     feasibility/out         finished runs and scenes (served at /out)
     feasibility/data/had    the person fit's result, read by examples.py
   - lab/serve.py --db: the DuckDB store. Put it at /data/log/lab.duckdb. Start it as `PYTHONPATH=services/app-server python -m app_server.lab.serve --port 8790 --db /data/log/lab.duckdb`. It serves frontend/dist at / once the frontend is built.
   - lab/preview.py: the queue starts the warm workers itself, from HOME/backend/workers with each worker's own Python (Isaac, TRIBE, Cosmos). Send each job to render-score's HTTP front instead (section 3), with the same inputs and outputs, and keep the queue's lanes: fast for previews, batch for runs, ahead for renders made in advance.
   - lab/runner.py and lab/experiment.py run a project's clips as threads in the app server, each clip one job on that queue; they need no change once the queue reaches render-score.
   - lab/sessions.py, lab/agent.py and lab/demo_writer.py run `claude -p` with an MCP config that starts `python -m app_server.lab.mcp_proxy <base url>`, which exposes every /tools tool. Replace that with a tool-calling loop against the planner's OpenAI-compatible API at http://planner/v1. Use the same tools, the same SYSTEM prompts, and the same session record (turns with reply and tool_calls), so the app shows chats unchanged.
   - lab/papers.py and lab/datasets.py reach OpenAlex, Europe PMC, arXiv, OpenNeuro, OSF, Zenodo, Figshare, GitHub and Hugging Face: the service needs outbound HTTPS.
   - Run it as the service app-server in fuzzball/simulaxon.fz: uvicorn, /data mounted, a persistent endpoint named simulaxon.

3. render-score (services/render-score/)
   - One container: Isaac Sim 6.2, the Cosmos framework at c3a2e37, TRIBE v2 at af58661, and the warm workers (isaac/ body and scene, cosmos/, tribe/). Each worker reads JSON lines on stdin and answers one JSON line per job; jobs.py is their queue, the same file as app_server/jobs.py.
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
   - The app has no route yet that starts it; that is open for the owner. Start it with `fuzzball workflow start fuzzball/observer.fz`.

6. Placement
   - render-score on Node A; planner and app-server on Node B, through node annotations requested in resource.annotations.

Done when:
- every check in docs/onboarding.md passes, steps 3 to 7;
- the app opens on the agent's chat, and New project shows the examples playing;
- the agent box answers through the planner;
- `fuzzball workflow list --parent <app-server workflow id>` lists the study run.
Report each check with its output.
```
