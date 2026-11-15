"""Regions of interest on fsaverage5 (20,484 vertices): anatomical regions from the Destrieux atlas, as in feasibility
tests 4 to 11, and areas from the HCP multimodal parcellation (Glasser 2016) that TRIBE v2 itself reports, where a
published finding names one. Every UI label says which through the region's definition.
"""
from functools import lru_cache
import numpy as np

REGIONS = {
    'Fusiform gyrus': (['G_oc-temp_lat-fusifor'], 'Faces, bodies, objects'),
    'Lateral occipitotemporal sulcus': (['S_oc-temp_lat'], 'Objects and bodies'),
    'Lateral occipital': (['G_occipital_middle', 'S_occipital_ant'], 'Object shape'),
    'Superior temporal sulcus': (['S_temporal_sup'], 'Faces, motion of people'),
    'Inferior temporal gyrus': (['G_temporal_inf'], 'Object identity'),
    'Parahippocampal gyrus': (['G_oc-temp_med-Parahip'], 'Places and scenes'),
    'Lingual gyrus': (['G_oc-temp_med-Lingual'], 'Scenes and early vision'),
    'Early visual': (['S_calcarine', 'Pole_occipital'], 'Edges, colour, contrast'),
    'Intraparietal sulcus': (['S_intrapariet_and_P_trans'], 'Space, motion, physical events'),
    'Superior parietal': (['G_parietal_sup'], 'Spatial attention'),
}
ALIASES = {   # the field's names for areas, resolved to the HCP-MMP1 areas this lab uses for them (FFC for the face area in
              # gates 1 and 2, PHA1 to PHA3 for the place area). Only names with a clear HCP counterpart are listed.
    'FFA': (['FFC'], 'Fusiform face area: HCP area FFC, the fusiform face complex'),
    'PPA': (['PHA1', 'PHA2', 'PHA3'], 'Parahippocampal place area: HCP areas PHA1, PHA2 and PHA3'),
    'V5': (['MT'], 'Motion area V5: HCP area MT'),
}
ALIAS_NAMES = {'fusiform face area': 'FFA', 'parahippocampal place area': 'PPA', 'place area': 'PPA', 'face area': 'FFA', 'motion area': 'V5'}


def alias(name: str) -> str | None:
    """The alias a name stands for, such as PPA for "ppa" or "parahippocampal place area", or None."""
    n = name.strip()
    return n.upper() if n.upper() in ALIASES else ALIAS_NAMES.get(n.lower())


HCP = {   # HCP-MMP1 areas, both hemispheres, as TRIBE v2 reports them (tribev2.utils.get_hcp_labels)
    'Anterior intraparietal area': (['AIP'], 'Grasping and watching actions'),
}


@lru_cache(None)
def masks() -> dict[str, np.ndarray]:
    from nilearn import datasets
    a = datasets.fetch_atlas_surf_destrieux(); lab = np.concatenate([a['map_left'], a['map_right']]); names = [str(x) for x in a['labels']]
    out = {r: np.isin(lab, [names.index(n) for n in parts]) for r, (parts, _) in REGIONS.items()}
    import sys
    from pathlib import Path
    from ..home import HOME; sys.path.insert(0, str(HOME / 'feasibility' / 'tribev2-src'))
    from tribev2.utils import get_hcp_labels
    hcp = {**{f'L_{k}': np.asarray(v) for k, v in get_hcp_labels(mesh='fsaverage5', hemi='left').items()},
           **{f'R_{k}': np.asarray(v) for k, v in get_hcp_labels(mesh='fsaverage5', hemi='right').items()}}
    for r, (parts, _) in HCP.items():
        m = np.zeros(20484, bool)
        for part in parts:
            for h in ('L', 'R'): m[hcp[f'{h}_{part}']] = True
        out[r] = m
    return out


def readout(values: np.ndarray) -> dict[str, float]:
    """Mean per region of a vertex map."""
    return {r: float(values[m].mean()) for r, m in masks().items()}


def table() -> list[dict]:
    m = masks()
    return ([{'region': r, 'atlas_labels': parts, 'known_for': known, 'vertices': int(m[r].sum()), 'definition': 'Destrieux atlas, anatomical'}
             for r, (parts, known) in REGIONS.items()]
            + [{'region': r, 'atlas_labels': parts, 'known_for': known, 'vertices': int(m[r].sum()), 'definition': 'HCP-MMP1 (Glasser 2016), both hemispheres, as TRIBE v2 reports it'}
               for r, (parts, known) in HCP.items()])


@lru_cache(None)
def hcp_areas() -> list[np.ndarray]:
    """The 360 HCP-MMP1 areas TRIBE v2 reports, as vertex masks: the cortex any region is ranked against."""
    import sys
    from pathlib import Path
    from ..home import HOME; sys.path.insert(0, str(HOME / 'feasibility' / 'tribev2-src'))
    from tribev2.utils import get_hcp_labels
    out = []
    for h in ('left', 'right'):   # indices are already over both hemispheres, as regions.masks uses them
        for k, v in get_hcp_labels(mesh='fsaverage5', hemi=h).items():
            if k != '?': m = np.zeros(20484, bool); m[np.asarray(v)] = True; out.append(m)
    return out


@lru_cache(None)
def atlas() -> dict[str, tuple[np.ndarray, str]]:
    """Every region an experiment can name, as vertex masks with where each comes from: the named groups above; each of
    TRIBE's HCP-MMP1 areas by its code (both hemispheres, or L_ and R_ for one); each Destrieux label (both, or L_ and R_)."""
    import sys
    from pathlib import Path
    from nilearn import datasets
    out = {r: (m, 'named group') for r, m in masks().items()}
    from ..home import HOME; sys.path.insert(0, str(HOME / 'feasibility' / 'tribev2-src'))
    from tribev2.utils import get_hcp_labels
    for h, hemi in (('L', 'left'), ('R', 'right')):   # indices already run over both hemispheres
        for k, v in get_hcp_labels(mesh='fsaverage5', hemi=hemi).items():
            if k == '?': continue
            m = np.zeros(20484, bool); m[np.asarray(v)] = True; out[f'{h}_{k}'] = (m, 'HCP-MMP1 area, one hemisphere')
            both = out.get(k, (np.zeros(20484, bool), ''))[0] | m; out[k] = (both, 'HCP-MMP1 area, both hemispheres')
    a = datasets.fetch_atlas_surf_destrieux(); names = [str(x) for x in a['labels']]
    lab = {'L': np.concatenate([a['map_left'], np.full(len(a['map_right']), -1)]), 'R': np.concatenate([np.full(len(a['map_left']), -1), a['map_right']])}
    for i, n in enumerate(names):
        if n in ('Unknown', 'Medial_wall'): continue
        l, r = lab['L'] == i, lab['R'] == i
        out[f'L_{n}'] = (l, 'Destrieux label, one hemisphere'); out[f'R_{n}'] = (r, 'Destrieux label, one hemisphere'); out[n] = (l | r, 'Destrieux label, both hemispheres')
    return out


def mask_for(name: str | list[str]) -> np.ndarray:
    """One region by name, or the union of several. Raises with near names when one is unknown."""
    A = atlas(); names = [name] if isinstance(name, str) else list(name); m = np.zeros(20484, bool)
    for n in names:
        if n not in A and alias(n):   # FFA, PPA, V5 and their spelled-out names
            for a in ALIASES[alias(n)][0]: m |= A[a][0]
            continue
        if n not in A:
            near = [k for k in A if n.lower() in k.lower()][:12]
            raise ValueError(f'no region named {n!r}' + (f'; near: {near}' if near else '; use region_search'))
        m |= A[n][0]
    return m


def search(query: str = '', limit: int = 60) -> dict:
    """Regions whose name contains the words, with what each is and its size. Empty: the named groups and every HCP code."""
    A = atlas(); q = query.lower().split()
    if not q:
        return {'named_groups': [{'region': r, 'known_for': k} for r, (_, k) in {**REGIONS, **HCP}.items()],
                'hcp_codes': sorted(k for k, (_, d) in A.items() if d == 'HCP-MMP1 area, both hemispheres'),
                'note': 'HCP-MMP1 (Glasser 2016) codes as TRIBE v2 reports them; Destrieux labels by search. L_ or R_ for one hemisphere.'}
    hits = [k for k in A if all(w in k.lower() for w in q)]
    named = [k for k, (_, what) in ALIASES.items() if all(w in (k + ' ' + what).lower() for w in q)]
    out = [{'region': k, 'what': ALIASES[k][1], 'areas': ALIASES[k][0], 'vertices': int(mask_for(k).sum()), 'use_as': k} for k in named]
    out += [{'region': k, 'what': A[k][1], 'vertices': int(A[k][0].sum())} for k in hits[:limit]]
    return {'query': query, 'matching': len(out), 'regions': out,
            **({} if out else {'note': 'Areas are named by HCP-MMP1 code or anatomy. The field names FFA, PPA and V5 work too; for other functional areas, '
                                       'such as the extrastriate body area, choose HCP areas from a paper and pass them as a group: {name, areas: [...]}.'})}
