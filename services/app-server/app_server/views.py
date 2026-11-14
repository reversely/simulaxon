"""Views: a dataset plus a list of stages, as in FiftyOne (fiftyone/core/stages.py). A stage is plain data:

  {"stage": "match",        "path": "held_end", "op": "==", "value": false}      ops: == != < <= > >= in between
  {"stage": "exists",       "path": "drop_t", "present": true}
  {"stage": "sort_by",      "path": "grip_nm", "reverse": false}
  {"stage": "take",         "n": 20, "seed": 0}
  {"stage": "select_slices","slices": ["A"]}
  {"stage": "pair_nearest", "left": {"path": "held_end", "op": "==", "value": false},
                            "right": {"path": "held_end", "op": "==", "value": true}, "on": ["size_m", "grip_nm"]}

pair_nearest pairs each left sample with the nearest unused right sample, by distance over the `on` fields, each scaled
by its standard deviation across both sides. It keeps only paired samples and writes, on each, `pair.id`, `pair.role`,
`pair.distance` and `pair.diff.<field>` (left minus right), so what was matched to what, and how closely, is data.
"""
from __future__ import annotations
import math, random
from .store import flatten, value_type


def get(s: dict, path: str):
    return flatten(s['fields']).get(path)


def test(v, op: str, x) -> bool:
    if v is None: return False
    try:
        if op == '==': return v == x
        if op == '!=': return v != x
        if op == '<': return v < x
        if op == '<=': return v <= x
        if op == '>': return v > x
        if op == '>=': return v >= x
        if op == 'in': return v in x
        if op == 'between': return x[0] <= v <= x[1]
    except TypeError:
        return False
    raise ValueError(f'unknown op {op}')


def text(v) -> str:
    """Values as the interface writes them: booleans as true and false, everything else as is."""
    return ('true' if v else 'false') if isinstance(v, bool) else str(v)


def describe(st: dict) -> str:
    """A stage in words, for the view bar."""
    k = st['stage']
    if k == 'match':
        v = st['value']; v = f'{text(v[0])} to {text(v[1])}' if st['op'] == 'between' else ', '.join(map(text, v)) if st['op'] == 'in' else text(v)
        return f"{st['path']} {'is' if st['op'] == '==' else st['op']} {v}"
    if k == 'exists': return f"{st['path']} {'present' if st.get('present', True) else 'missing'}"
    if k == 'sort_by': return f"sorted by {st['path']}{', largest first' if st.get('reverse') else ''}"
    if k == 'take': return f"{st['n']} at random, seed {st.get('seed', 0)}"
    if k == 'select_slices': return f"slices {', '.join(st['slices'])}"
    if k == 'pair_nearest':
        return f"pair {describe({'stage': 'match', **st['left']})} with nearest {describe({'stage': 'match', **st['right']})}, on {', '.join(st['on'])}"
    return k


def _pair(rows, st):
    L = [s for s in rows if test(get(s, st['left']['path']), st['left']['op'], st['left']['value'])]
    R = [s for s in rows if test(get(s, st['right']['path']), st['right']['op'], st['right']['value'])]
    on = st['on']; sd = {}
    for p in on:
        xs = [get(s, p) for s in L + R if isinstance(get(s, p), (int, float))]
        m = sum(xs) / len(xs) if xs else 0; sd[p] = math.sqrt(sum((x - m) ** 2 for x in xs) / max(len(xs) - 1, 1)) or 1.0
    free, out = list(R), []
    for i, a in enumerate(L):
        if not free: break
        def dist(b): return math.sqrt(sum(((get(a, p) - get(b, p)) / sd[p]) ** 2 for p in on))
        b = min(free, key=dist); free.remove(b); d = dist(b); pid = f'pair {i + 1:03d}'
        diff = {p: get(a, p) - get(b, p) for p in on}
        for s, role in ((a, 'left'), (b, 'right')):
            f = {**s['fields'], 'pair': {'id': pid, 'role': role, 'distance': round(d, 4), 'diff': {p: round(v, 6) for p, v in diff.items()}}}
            src = {**s['sources'], 'pair.id': 'pair_nearest stage', 'pair.role': 'pair_nearest stage', 'pair.distance': f"pair_nearest stage: distance over {', '.join(on)}, each divided by its SD ({', '.join(f'{p} {sd[p]:.4g}' for p in on)})",
                   **{f'pair.diff.{p}': f'pair_nearest stage: left minus right {p}' for p in on}}
            out.append({**s, 'fields': f, 'sources': src})
    return out


def apply(rows: list[dict], stages: list[dict]) -> tuple[list[dict], list[dict]]:
    """The samples after every stage, and the count after each stage."""
    trail = [{'stage': 'dataset', 'text': 'all samples', 'count': len(rows)}]
    for st in stages:
        k = st['stage']
        if k == 'match': rows = [s for s in rows if test(get(s, st['path']), st['op'], st['value'])]
        elif k == 'exists': rows = [s for s in rows if (get(s, st['path']) is not None) == st.get('present', True)]
        elif k == 'sort_by':
            have = [s for s in rows if get(s, st['path']) is not None]; miss = [s for s in rows if get(s, st['path']) is None]
            rows = sorted(have, key=lambda s: get(s, st['path']), reverse=st.get('reverse', False)) + miss
        elif k == 'take': rows = random.Random(st.get('seed', 0)).sample(rows, min(st['n'], len(rows)))
        elif k == 'select_slices': rows = [s for s in rows if s['slice'] in st['slices']]
        elif k == 'pair_nearest':
            nl = sum(test(get(s, st['left']['path']), st['left']['op'], st['left']['value']) for s in rows)
            nr = sum(test(get(s, st['right']['path']), st['right']['op'], st['right']['value']) for s in rows)
            rows = _pair(rows, st)
            trail.append({'stage': k, 'text': describe(st), 'count': len(rows), 'note': f'{nl} on the left, {nr} on the right, {len(rows) // 2} pairs'}); continue
        else: raise ValueError(f'unknown stage {k}')
        trail.append({'stage': k, 'text': describe(st), 'count': len(rows)})
    return rows, trail


def facets(rows: list[dict], schema: list[dict], bins: int = 24) -> dict:
    """Per field, over the samples in the view: numbers get a histogram with its bin edges, the rest value counts."""
    out = {}
    for e in schema:
        p, t = e['path'], e['type']
        vals = [get(s, p) for s in rows]; present = [v for v in vals if v is not None]
        f = {'count': len(present), 'missing': len(vals) - len(present)}
        if t in ('int', 'float') and present:
            lo, hi = min(present), max(present); w = (hi - lo) / bins or 1
            h = [0] * bins
            for v in present: h[min(int((v - lo) / w), bins - 1)] += 1
            f.update(kind='numeric', min=lo, max=hi, edges=[lo + i * w for i in range(bins + 1)], hist=h)
        elif t in ('str', 'bool'):
            c: dict = {}
            for v in present: c[text(v)] = c.get(text(v), 0) + 1
            f.update(kind='values', values=sorted(c.items(), key=lambda kv: -kv[1])[:40], distinct=len(c))
        else:
            f.update(kind=t)
        out[p] = f
    return out
