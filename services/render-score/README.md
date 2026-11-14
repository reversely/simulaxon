# render-score

Node A in [docs/image.png](../../docs/image.png): one container that runs a scene through Isaac Sim 6.2 (render), Cosmos3 Nano (restyle) and TRIBE v2 (predicted cortical response).

| File | Does |
|---|---|
| `isaac/isaac_scene_worker.py` | Warm Isaac Sim worker: renders a scene, with masks |
| `isaac/isaac_body_worker.py` | Warm Isaac Sim worker for the body world (uses `studies/observer/body_scene.py`) |
| `isaac/render_fit.py` | The stage settings the scene worker matches |
| `cosmos/cosmos_worker.py` | Warm Cosmos3-Nano-Sim-Transfer worker: the rendered clip conditions the restyle |
| `tribe/tribe_worker.py`, `tribe/fast_tribe.py` | Warm TRIBE v2 worker: one prediction per clip, video only, bfloat16 |
| `server.py` imports the queue | `app_server/jobs.py` from the app server, the one queue for both: lanes, caching and warm workers over JSON lines |

Memory, from the picture: Isaac 15 GB (estimate), Cosmos 48 GB (measured), TRIBE 15 GB (estimate; 10.8 GB peak measured); 78 of 128 GB on Node A.

Wiring: [docs/wiring-prompt.md](../../docs/wiring-prompt.md), section 3.
