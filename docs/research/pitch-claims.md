# Pitch claims, checked against sources

The film (#29) puts lines from `docs/pitch.md` on screen. Each factual claim below was checked on 15 Nov 2026 against
a primary source. Local copies of each source are in `sources/` (gitignored); every source is public and cited here by URL.

## "A 20-person fMRI study with one hour per participant can cost nearly $14,000 in scan time alone."

Holds at the hourly rates research MRI facilities publish. Twenty one-hour scans at:

| Facility | Rate per hour | 20 hours | Source |
|---|---|---|---|
| Harvard Center for Brain Science, academic external, weekday peak (FY27) | $710 | $14,200 | cbs.fas.harvard.edu/facilities/neuroimaging/investigators/policies |
| Harvard Center for Brain Science, Harvard affiliate or full internal (FY27) | $660 | $13,200 | same |
| UC Davis Imaging Research Center, MRI scan with live subject, internal | $666 | $13,320 | health.ucdavis.edu/imaging-research/services/rates-and-scheduling |
| UC Davis Imaging Research Center, external | $906 | $18,120 | same |

Quoted from the Harvard page: "Academic External $710 / hour" (weekday peak). From the UC Davis page: "MRI scan,
live subject $666 $906" (internal, external).

## "TRIBE v2, which trained on fMRI recordings of people watching films, television, and short videos of everyday events."

Holds. TRIBE v2 paper (d'Ascoli et al., arXiv:2605.04326, Table 1 and § 5.7): trained on four datasets.
- Courtois NeuroMod: "the first six seasons of the popular TV series Friends as well as four movies".
- BoldMoments: "1,102 3-second video clips … represented a wide selection of possible events a human might witness".
- Wen2017: "three hours of short video clips without sound".
- Lebel2023: podcasts ("listened to 27 complete, natural, narrative stories … from The Moth podcast"). The line
  leaves this one out; it does not contradict it.

## "In separate evaluations, it recovered known patterns of brain activity for seeing faces versus places and hearing descriptions of emotional versus physical pain."

Holds. Same paper:
- § 2.5, visual localizers from the Individual Brain Charting dataset: "well-known responsive areas are recovered:
  the fusiform face area (FFA) for faces, the parahippocampal place area (PPA) for places" (Fig. 4).
- § 2.6, language localizers: "we test the ability of TRIBE v2 to isolate emotional processing regions by
  contrasting sentences relative to emotional versus physical pain. TRIBE v2 correctly recovers two important
  regions: the temporo-parietal junction (TPJ) and the middle temporal gyrus (MTG)" (Fig. 5).
