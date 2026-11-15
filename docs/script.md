# Demo script

The film's one script (#29). The spoken lines are the owner's pitch (`docs/pitch.md`), word for word and in order; the
line "How does the brain make sense of an event as it unfolds?" is cut. Each beat gives the spoken line, then what is on
screen and the sound under it. Everything on screen is a real capture from the app, Grafana or the cluster.

## 1. Opening

**Spoken:** Prototype neuroscience experiments in hours. Simulaxon's AI agents turn a hypothesis into scenes they can
generate, predict how the brain would respond, and use those predictions to decide what to test next.

**On screen:** The predicted brain from a real trial turns slowly while a hypothesis is typed into the agent's chat and
sent. Sound: `transition5`, then `mouse_click`.

## 2. Problem

**Spoken:** To find out what drives a response, researchers need to vary what people see, hear, or know going into a
scene. Testing those comparisons with people gets expensive fast, at tens of thousands of dollars per study.

**On screen:** In the Room of the busts against vases project, the scene script switches a bust to a vase and the Isaac
Sim render swaps. Sound: `click_bubble2`.

## 3. Approach

**Spoken:** Simulaxon gives researchers a way to develop the experiment before they bring in participants. The agent
decides what to vary and what to hold fixed, generates the clips, and compares the predicted brain responses. It can then
run a follow-up to see whether a pattern persists when another detail changes.

**On screen:** Nemotron's plan streams into the chat, the project is set up and its trial count climbs as clips render.
Sound: `multiply_click3`, then the melodic success.

## 4. Predictions

**Spoken:** The predictions come from Meta's TRIBE v2, which trained on fMRI recordings of people watching films,
television, and short videos of everyday events. In separate evaluations, it recovered known patterns of brain activity
for seeing faces versus places and hearing descriptions of emotional versus physical pain.

**On screen:** The brain view goes from pial to inflated, then the face and house rivalry experiment shows its map.
Sound: `ES_User Interface, Motion, Scan, Zoom`.

## 5. Two workstations

**Spoken:** The app and the video pipeline together need an estimated 150 GB of memory, so Fuzzball starts them on
separate 128 GB workstations and gives both access to the same VAST storage.

**On screen:** The architecture diagram from the demo page: two GB10 nodes, each service with its image, cores, memory
and GPU, the VAST volume underneath. Sound: `Low Subby Whoosh`.

## 6. Planning

**Spoken:** When you submit a hypothesis, Nemotron Super 120B plans the experiment on the first workstation.

**On screen:** The planner box on CIQ-CHI-SPARK26 lights up, then the recording of the plan streaming into the chat.
Sound: `Low Subby Whoosh`.

## 7. Render, restyle, predict

**Spoken:** The app sends the scene specifications to the second, where Isaac Sim renders a reference video, NVIDIA
Cosmos 3 Nano uses it to generate realistic footage, and TRIBE v2 predicts the fMRI response to each clip.

**On screen:** The vase clip made on the cluster: Isaac Sim's render, then Cosmos 3 Nano's restyle beside it, then its
predicted brain. Sound: `Low Subby Whoosh`.

## 8. Follow-up

**Spoken:** The app sends the predictions back to Nemotron to compare conditions. If the agent chooses a follow-up, the
app submits it to Fuzzball.

**On screen:** The diagram's dot travels back to the planner, then the Fuzzball jobs table from Grafana.
Sound: `Low Subby Whoosh`.

## 9. One volume

**Spoken:** Each round adds its clips, predictions, and log to the same VAST volume, so you can trace each result back to
what the agent changed.

**On screen:** History: one change, then Undo. Sound: `mouse_click`.

## 10. Monitoring

**Spoken:** Prometheus and Grafana run beside them as their own Fuzzball workflow: every node's state, every study step,
each GPU job's utilisation, power and memory, and the planner's tokens per second.

**On screen:** One Grafana panel per phrase, from the live dashboard: busy GPUs by service, utilisation while held,
memory in use on each node, planner tokens per second. Sound: `click_digital1`.

## 11. Demo

**Spoken:**

1. Ask the agent to design an experiment around your hypothesis.
2. Upload footage or describe the scenes you want to test.
3. Review the generated scenes and predicted responses alongside the agent's follow-up experiments.
4. If you have access to some fMRI recordings that you want to extrapolate on, these can be fine-tuned to customize
   simulation results.
5. Run robotics experiments that use predicted human brain responses to test whether a robot can better anticipate what
   someone is about to do from the way they move.

**On screen:** One card per step. Step 1 is the agent's chat. Step 2 is an upload into a dataset from the chat. Step 3 is
Results for the busts against vases project. Step 4 is the Human Action Dataset's adapter card, labelled as a benchmark on
held-out categories, with no r shown beside any live result. Step 5 is a simulated SO-101 grasp from Experimental.
Sound: `click_digital1` per card.

## 12. Close

**Spoken:** Prototype neuroscience experiments in hours.

**On screen:** Every card from the film in one collage, then the end mark. Sound: `ES_Swooshes, Whoosh, Short`.

## Rules for the cut

- The spoken lines stay as the owner wrote them.
- The agent is Nemotron Super 120B everywhere.
- Motion and sound come from the reference recording (`docs/resources/Screen Recording 2026-11-15 at 12.47.21 AM.mov`)
  and the sound files in `docs/resources/Ramp Video sfx/`; type and colour come from the app.
- Isaac Sim and Cosmos material leads; fetched-dataset projects appear only as examples.
