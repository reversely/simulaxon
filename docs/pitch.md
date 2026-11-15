# Simulaxon pitch

The owner's pitch, 15 Nov 2026, as written.

**Elevator pitch**

Prototype neuroscience experiments in hours. Simulaxon’s AI agents turn a hypothesis into scenes they can generate, predict how the brain would respond, and use those predictions to decide what to test next.

**Slightly longer**

How does the brain make sense of an event as it unfolds? To find out what drives a response, researchers need to vary what people see, hear, or know going into a scene. Testing those comparisons with people gets expensive fast. A 20-person fMRI study with one hour per participant can cost nearly $14,000 in scan time alone.

Simulaxon gives researchers a way to develop the experiment before they bring in participants. The agent decides what to vary and what to hold fixed, generates the clips, and compares the predicted brain responses. It can then run a follow-up to see whether a pattern persists when another detail changes.

The predictions come from Meta’s TRIBE v2, which trained on fMRI recordings of people watching films, television, and short videos of everyday events. In separate evaluations, it recovered known patterns of brain activity for seeing faces versus places and hearing descriptions of emotional versus physical pain.

**How it runs on CIQ**

The app and the video pipeline together need an estimated 150 GB of memory, so Fuzzball starts them on separate 128 GB workstations and gives both access to the same VAST storage. When you submit a hypothesis, Nemotron Super 120B plans the experiment on the first workstation. The app sends the scene specifications to the second, where Isaac Sim renders a reference video, NVIDIA Cosmos 3 Nano uses it to generate realistic footage, and TRIBE v2 predicts the fMRI response to each clip.

The app sends the predictions back to Nemotron to compare conditions. If the agent chooses a follow-up, the app submits it to Fuzzball. Each round adds its clips, predictions, and log to the same VAST volume, so you can trace each result back to what the agent changed.

**Workflow**

1. Ask the agent to design an experiment around your hypothesis.
2. Upload footage or describe the scenes you want to test.
3. Review the generated scenes and predicted responses alongside the agent’s follow-up experiments.
4. Provide a participant’s fMRI recordings and the videos they watched. Fine-tune the model in one click to predict how that person would respond to new footage.
5. Run robotics experiments that use predicted human brain responses to test whether a robot can better anticipate what someone is about to do from the way they move.
