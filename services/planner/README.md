# planner

Node B in [docs/image.png](../../docs/image.png): Nemotron Super 120B in NVFP4, about 70 GB.
- Served by vLLM with an OpenAI-compatible API at `http://planner`.
- The app server's agent plans studies through it, calling tools.

No code lives here; the service is defined in `fuzzball/simulaxon.fz`. Settings: [docs/onboarding.md](../../docs/onboarding.md), step 4.
