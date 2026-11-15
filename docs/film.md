# Demo film (#29)

The script is the owner's pitch, `docs/pitch.md`, used in its order. This file holds the cut and the cards built on
it. Claims in the script are checked in `docs/research/pitch-claims.md`.

## Rules from the owner

- The script is `docs/pitch.md`. Its lines stay as written.
- Everything is Nemotron Super 120B.
- From the reference recording (`docs/resources/Screen Recording 2026-11-15 at 12.47.21 AM.mov`), take only the
  motion and the sound. Type and colour come from the app.
- Sound: the files in `docs/resources/Ramp Video sfx/`.
- Less time on the sales pitch; cut a line.
- A Grafana section, showing it working; it need not be live.
- The narrative targets Rocky Linux usage, possibly RLC Pro AI, then Fuzzball usage, uptime monitoring, and both clusters used in a way that is not absurd. Plan the Grafana data story first, from real usage screenshots once back online, with the dashboard focused on compute optimization: `docs/grafana-plan.md`.

## Fine-tuning: the demo story

The owner, 15 Nov: fine-tuning is "our best benchmark and is kind of more valid as an idea"; "there's benchmarking, and there's live results. these are two different kinds of results. when you talk about how well the adapter did this doesn't reflect usefulness in prod on new unseen images"; "the demo story of a fine tune needs to be made clear".

What the app has is an adapter: a map from TRIBE v2's prediction for each of 360 brain areas to measured fMRI, fitted in one click (#28). It does not retrain TRIBE v2's own weights, as the TRIBE v2 paper's fine-tuning does, so the demo calls it "fitting TRIBE v2 to measured fMRI" and the app calls the result an adapter.

The story has two halves that are never mixed: a **benchmark**, scored against measured fMRI the fit never saw, and a **live** use on new stimuli, where no measured fMRI exists and no r is shown.

| # | Beat | Screen | What it says | Evidence | Status |
|---|---|---|---|---|---|
| 1 | TRIBE v2 predicts an average viewer it has never met | A trial in the Room: the clip beside its predicted brain | Predictions come from other people watching other films | TRIBE v2 paper, Table 1 | Built |
| 2 | Bring people's measured fMRI | Datasets: the Human Action Dataset, 30 people, 3,600 clips, with an Adapters tab | A dataset with measured responses can be fitted to | OpenNeuro ds004488 | Built |
| 3 | One click | Fit an adapter; the card appears in about 1.5 s | Fitting is one action | #28 page check: 1.2 to 1.6 s | Built |
| 4 | **Benchmark** | The adapter card, labelled "Benchmark: held-out categories of the Human Action Dataset" | On categories it never saw: 0.257 as released, 0.407 fitted, against a ceiling of 0.675 (38% to 60% of what the data allow); shuffled labels −0.011 | #28: 179 of 212 areas improve | Numbers built; the label and a V-JEPA 2 baseline row are not |
| 5 | Known results survive | Faces against objects (Kanwisher 1997) run with and without the adapter, side by side | The fit does not break a finding the field already knows | Not yet run | To build (#37) |
| 6 | **Live** | An experiment run through the adapter: its results name the adapter, show no r, and say when the stimuli lie outside what it was fitted on | Use on new stimuli, stated as a prediction | Not yet built | To build (#28 item 3, #37) |
| 7 | Transfer | Fitted on the Human Action Dataset, scored on a dataset of different stimuli with measured fMRI | The closest test of new, unseen stimuli that can still be scored | Not yet run | To build (#37) |

The film uses beats 1 to 4 today, with the benchmark labelled as one; beats 5 to 7 join it as they are built. It never puts the benchmark's r beside a live result.

Not claimed: a fit to one person. In the lab's run, one person's own fit scored 0.107 on that person's held-out categories, against 0.115 for a fit to everyone else; workflow step 4 in `docs/pitch.md` ("predict how that person would respond") is the owner's line and stays, and the picture under it is the group adapter until a personal fit beats the group's.

## The owner's lines, in order

Cut: "How does the brain make sense of an event as it unfolds?"

1. Prototype neuroscience experiments in hours.
2. Simulaxon's AI agents turn a hypothesis into scenes they can generate, predict how the brain would respond, and use those predictions to decide what to test next.
3. To find out what drives a response, researchers need to vary what people see, hear, or know going into a scene.
4. Testing those comparisons with people gets expensive fast. A 20-person fMRI study with one hour per participant can cost nearly $14,000 in scan time alone.
5. Simulaxon gives researchers a way to develop the experiment before they bring in participants.
6. The agent decides what to vary and what to hold fixed, generates the clips, and compares the predicted brain responses.
7. It can then run a follow-up to see whether a pattern persists when another detail changes.
8. The predictions come from Meta's TRIBE v2, which trained on fMRI recordings of people watching films, television, and short videos of everyday events.
9. In separate evaluations, it recovered known patterns of brain activity for seeing faces versus places and hearing descriptions of emotional versus physical pain.
10. The app and the video pipeline together need an estimated 150 GB of memory, so Fuzzball starts them on separate 128 GB workstations and gives both access to the same VAST storage.
11. When you submit a hypothesis, Nemotron Super 120B plans the experiment on the first workstation.
12. The app sends the scene specifications to the second, where Isaac Sim renders a reference video, NVIDIA Cosmos 3 Nano uses it to generate realistic footage, and TRIBE v2 predicts the fMRI response to each clip.
13. The app sends the predictions back to Nemotron to compare conditions. If the agent chooses a follow-up, the app submits it to Fuzzball.
14. Each round adds its clips, predictions, and log to the same VAST volume, so you can trace each result back to what the agent changed.
15. Workflow steps 1 to 5, as written in `docs/pitch.md`.
16. Prototype neuroscience experiments in hours.

## Claude's draft, for the owner's approval

Grafana line, after line 14:

> Prometheus and Grafana run beside them as their own Fuzzball workflow: every node's state, every study step, each GPU job's utilisation, power and memory, the planner's tokens per second, and every failed step with its error.

## Cards

One card per line: a real control in the app, performed on its real values, with the reference's motion (the card
rises on a stack, one cursor action, values roll, one button press) and one Ramp sound.

| Line | Card | Sound |
|---|---|---|
| 1 | The brain mesh with drifting glyphs round the line | `transition5` |
| 2 | A hypothesis typed into the agent's chat, then Send | `text_crisp5`, `mouse_click` |
| 3 | The scene script control switches bust to vase; the render swaps | `click_bubble2` |
| 4 | 20 people × 1 h × $710 rolls up to $14,200 | `ES_Mechanical, Click, Spin, Clocks 01` |
| 5–6 | Nemotron's plan streams in; Run; the trial count reaches 40 | `multiply_click3`, melodic success |
| 7 | Colour-matched, then shape-matched: same region, two runs | `Pencil Underscoring` |
| 8–9 | Brain view pial to inflated; the faces versus places map | `ES_User Interface, Motion, Scan, Zoom` |
| 10–13 | Two workstations on a VAST bar; each message travels its arrow | `Low Subby Whoosh` per hop |
| 14 | History: one change, then Undo | `mouse_click` |
| Grafana | Nodes, Study steps, GPU jobs, Planner, Failures: one panel each, from real captures | `click_digital1` |
| 15 | Steps 1 to 5, one card each | `click_digital1` |
| 16 | Every card in a collage, then the end mark | `ES_Swooshes, Whoosh, Short` |

## Open

- Grafana captures with real data need the cluster; the owner's go-ahead first.
- Shots of Nemotron planning on the cluster.
- Step 4 on one person: the per-person adapter (#28) is not built.
- Line 7's numbers are from 7 Nov; recheck in the app before they go on screen.
