# The observer study

What a humanoid's appearance and motion do to the person watching it. Six recorded moments, each acted out four ways, in the scan of the real room, seen from where the partner stood:

| | Recorded human motion | Robotic motion |
|---|---|---|
| SMPL-X human body | human | android |
| Unitree G1 | robot look, human motion | robot |

TRIBE reads each clip as the observer's cortex. The anchor is Saygin et al. 2012 (SCAN 7:413–422): bilateral anterior intraparietal sulcus responded to the mismatch between look and motion.

| Stage | Files |
|---|---|
| Moments and motions | `motions.py`, `motion_lib.py`, `scan_mesh.py` |
| Render | `render.py`, `body_scene.py`, `g1_execute.py`, `g1_retarget.py`, `g1_fk.py` |
| Predict | `tribe_clips.py` |
| Contrasts and baselines | `analyse.py`, `donoso_signals.py` (region labels and the V-JEPA 2 index) |
| Region maps | `maps.py` |
| Into the app | `app_dataset.py`, `contact_sheet.py` |
| Local runner | `run_demo.sh` |

Wiring: [docs/wiring-prompt.md](../../docs/wiring-prompt.md), section 5.
