# Seeded examples

The classic experiments listed in New project (`services/app-server/app_server/lab/examples.py`), and what their cards show.

| File | Does |
|---|---|
| `stimuli.py` | Makes the rivalry stimuli (face and house taking turns, blended, alone, and turns of 1.5 to 12 s) from fLoc photos, and the flash train, as the dataset `generated_examples`. Fetches fLoc from `github:VPNL/fLoc` the first time |
| `media.py` | Cuts each card's looping clip: from the example's run when the store has one, from its stimuli otherwise. Names any example it skips and why |

Both read the data root from `SIMULAXON_HOME` or `SIMULAXON_DATA` and run with the app server's Python: `PYTHONPATH=services/app-server python studies/examples/<file>`. Onboarding step 6 has the commands.
