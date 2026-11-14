"""MCP server for the agent: the same data API the panels use, nothing else.

usage (by the agent runtime): python -m vcl.data.agent_tools BASE_URL SHOW_FILE

Reading tools call the running server over HTTP. view_show is the agent's only way to change the screen: it writes the
dataset and stages it wants shown to SHOW_FILE, and the server hands them to the interface, where each stage is marked
as added by the agent and can be removed like any other.
"""
from __future__ import annotations
import json, sys, urllib.parse, urllib.request

BASE, SHOW = sys.argv[1], sys.argv[2]


def _http(method: str, path: str, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=300) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'detail': json.loads(e.read() or b'{}').get('detail')}


def _ds(name: str) -> str:
    return '/api/datasets/' + urllib.parse.quote(name, safe='')


def datasets_list() -> str:
    """Every dataset: name, how it was loaded (source description) and sample count."""
    return json.dumps([{'name': d['name'], 'samples': d['samples'], 'about': d['source'].get('about')} for d in _http('GET', '/api/datasets')])


def dataset_schema(dataset: str) -> str:
    """A dataset's fields: path, type, how many samples have it, unit and description when the source gives them."""
    d = _http('GET', _ds(dataset))
    return json.dumps(d.get('schema', d))


def view_run(dataset: str, stages: list[dict], limit: int = 20) -> str:
    """Runs stages on a dataset without changing the screen. Returns the count after each stage, per-field summaries of
    the samples in the view, and the first `limit` samples (track fields left out). Stage forms:
      {"stage": "match", "path": P, "op": "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "between", "value": V}
      {"stage": "exists", "path": P, "present": true}
      {"stage": "sort_by", "path": P, "reverse": false}
      {"stage": "take", "n": N, "seed": 0}
      {"stage": "select_slices", "slices": [S]}
      {"stage": "pair_nearest", "left": {"path", "op", "value"}, "right": {"path", "op", "value"}, "on": [P, ...]}"""
    r = _http('POST', _ds(dataset) + '/view', {'stages': stages, 'limit': limit})
    if 'error' in r: return json.dumps(r)
    facets = {p: {k: v for k, v in f.items() if k not in ('edges', 'hist')} for p, f in r['facets'].items()}
    samples = [{'id': s['id'], 'group': s['group'], 'slice': s['slice'], 'fields': {k: v for k, v in s['fields'].items() if not (isinstance(v, dict) and v.get('_kind') == 'track')}} for s in r['samples']]
    return json.dumps({'count': r['count'], 'trail': r['trail'], 'facets': facets, 'samples': samples}, default=str)[:60000]


def sample_get(dataset: str, id: str) -> str:
    """One sample: every field with the file and key it came from, its media file and the members of its group."""
    return json.dumps(_http('GET', _ds(dataset) + '/samples/' + urllib.parse.quote(id, safe='')), default=str)[:60000]


def track_summary(dataset: str, id: str, path: str) -> str:
    """A time track summarised per column: time range, number of readings, first, last, min, max and mean. Wide tracks
    (such as TRIBE's 20,484 vertices) arrive as their mean and spread across columns."""
    t = _http('GET', _ds(dataset) + '/samples/' + urllib.parse.quote(id, safe='') + '/track?path=' + urllib.parse.quote(path))
    if 'error' in t: return json.dumps(t)
    out = {'source': t['source'], 'unit': t.get('unit'), 'summary': t.get('summary'), 'time_s': [t['time_s'][0], t['time_s'][-1]], 'readings': len(t['time_s']), 'columns': {}}
    for c, vs in zip(t['columns'], t['values']):
        xs = [v for v in vs if v is not None]
        out['columns'][c] = {'first': xs[0], 'last': xs[-1], 'min': min(xs), 'max': max(xs), 'mean': sum(xs) / len(xs), 'missing': len(vs) - len(xs)} if xs else {'missing': len(vs)}
    return json.dumps(out)


def view_show(dataset: str, stages: list[dict], why: str, fields_on_tiles: list[str] | None = None) -> str:
    """Puts this dataset and these stages on the person's screen, replacing the current view. Every stage you pass is
    marked on screen as added by you and can be removed. `why` is one plain sentence shown with it. `fields_on_tiles`
    names the fields printed under each sample, such as the ones you sorted or compared by. Run view_run first so you
    know what the view contains."""
    json.dump({'dataset': dataset, 'stages': stages, 'why': why, 'fields_on_tiles': fields_on_tiles or []}, open(SHOW, 'w'))
    return json.dumps({'shown': True, 'dataset': dataset, 'stages': len(stages)})


def main():
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer('vcl-data')
    for f in (datasets_list, dataset_schema, view_run, sample_get, track_summary, view_show): mcp.add_tool(f, name=f.__name__, description=f.__doc__)
    mcp.run()


if __name__ == '__main__':
    main()
