"""Worlds and their scene scripts. A template names a world kind; the world kind writes the scene script whose declared
parameters become the room's controls, and turns the current values into one renderer job.

Kinds: counter (an asset on a counter), stage (a composed USD stage such as a SAGE room), fall (an asset dropped onto
the counter), body (a real moment of social interaction from EgoBody, in the scan of its room, acted out by a human
body or the Unitree G1 with recorded or robotic motion, filmed from the partner's eye). The agent can write any other script; the parser (vcl/script.py) turns its declarations into controls.
"""
from __future__ import annotations


def _opts(xs):
    return '[' + ', '.join(repr(x) for x in xs) + ']'


def script(kind: str, assets: dict, defaults: dict) -> str:
    ids = list(assets)
    if kind == 'counter':
        return f'''# Scene script: one asset on the counter, framed by its size.
item      = asset({defaults.get('item', ids[0])!r}, options={_opts(ids)}, role="manipulated", target="/World/Item", label="Item")
framing   = number({defaults.get('framing', 2.6)}, unit="x size", range=(1.2, 6.0), role="fixed", target="camera.distance_to(item)", label="Camera distance")
yaw_deg   = angle({defaults.get('yaw_deg', 8)}, unit="deg", range=(-60, 60), role="fixed", target="camera.yaw", label="Camera angle")
light_deg = angle({defaults.get('light_deg', 35)}, unit="deg", range=(5, 80), role="fixed", target="/World/WindowLight.elevation", label="Window light height")
colour    = choice({defaults.get('colour', 'full')!r}, options=["full", "greyscale"], role="fixed", target="render.colour", label="Colour")
focus     = choice({defaults.get('focus', 'whole_frame')!r}, options=["whole_frame", "item_only", "background_only", "zoom_to_item"], role="fixed", target="render.focus", label="Focus")

def build(stage, p):
    place_on_counter(stage, p.item); frame(stage.camera, p.item, p.framing, p.yaw_deg); set_light(stage, p.light_deg)
'''
    if kind == 'stage':
        return f'''# Scene script: a whole room, with any object hidden, from a named camera.
hidden = asset({defaults.get('hidden', 'none')!r}, options={_opts(['none'] + ids)}, role="manipulated", target="/World/Objects/*.visibility", label="Hidden object")
camera = choice({defaults.get('camera', 'corner_a')!r}, options=["corner_a", "corner_b", "overview"], role="fixed", target="camera", label="Camera")

def build(stage, p):
    hide(stage, p.hidden); use_camera(stage, p.camera)
'''
    if kind == 'fall':
        return f'''# Scene script: an asset dropped onto the counter; the outcome is the manipulation.
item        = asset({defaults.get('item', ids[0])!r}, options={_opts(ids)}, role="randomized", sampler="choice", target="/World/Item", label="Item")
outcome     = choice({defaults.get('outcome', 'lands')!r}, options=["lands", "hovers", "hovers_bouncing"], role="manipulated", target="motion.after_contact", label="Outcome")
drop_m      = number({defaults.get('drop_m', 0.4)}, unit="m", range=(0.1, 1.0), role="fixed", target="motion.drop", label="Drop height")
gap_m       = number({defaults.get('gap_m', 0.08)}, unit="m", range=(0.0, 0.3), role="fixed", target="motion.hover_gap", label="Hover gap")
restitution = number({defaults.get('restitution', 0.35)}, range=(0.0, 0.9), role="fixed", target="motion.restitution", label="Bounciness")

def build(stage, p):
    place_above_counter(stage, p.item, p.drop_m); animate_fall(stage, p.outcome, p.gap_m, p.restitution)
'''
    if kind == 'body':
        return f'''# Scene script: a real moment of social interaction (EgoBody), in the scan of its room, seen from the partner's eye.
moment     = asset({defaults.get('moment', ids[0])!r}, options={_opts(ids)}, role="randomized", sampler="choice", target="/World/Room", label="Moment")
body       = choice({defaults.get('body', 'human')!r}, options=["human", "g1"], role="manipulated", target="/World/Body", label="Body")
motion     = choice({defaults.get('motion', 'recorded')!r}, options=["recorded", "robotic"], role="manipulated", target="motion.timing", label="Motion")
keyframe_s = number({defaults.get('keyframe_s', 0.5)}, unit="s", range=(0.1, 3.0), role="fixed", target="motion.keyframe_spacing", label="Keyframes, robotic motion")

def build(stage, p):
    load_room(stage, p.moment); camera_at_partner_eye(stage, p.moment); place_body(stage, p.body, p.moment); play_motion(stage, p.motion, p.keyframe_s)
'''
    raise ValueError(kind)


def body_world(n: int = 6, keyframe_s: float = 0.5) -> dict:
    """The body world from data: the moments the EgoBody search keeps (lab/records.search_egobody_moments), as the
    world's assets, with the search that found them."""
    from . import records
    srch = records.search_egobody_moments(n)
    assets = {m['id']: {'label': m['label'], 'recording': m['rec'], 'episode': m['k'], 'source': m.get('source'), 'image': None} for m in srch['picked']}
    return {'world': {'kind': 'body', 'name': 'EgoBody rooms in Isaac Sim'}, 'assets': assets, 'search': srch,
            'units': list(assets), 'factors': {'body': ['human', 'g1'], 'motion': ['recorded', 'robotic']},
            'script': script('body', assets, {'keyframe_s': keyframe_s})}


def job(kind: str, values: dict, assets: dict, world: dict) -> dict:
    """The renderer inputs for one set of parameter values."""
    if kind == 'counter':
        return {'kind': 'counter', 'usd': assets[values['item']]['usd'], 'framing': values['framing'], 'yaw_deg': values['yaw_deg'], 'light_deg': values['light_deg'], 'colour': values.get('colour', 'full'),
                **({'focus': values['focus']} if values.get('focus', 'whole_frame') != 'whole_frame' else {})}   # default stays out of the cache key
    if kind == 'stage':
        return {'kind': 'stage', 'usda': world['usda'], 'hidden': [] if values['hidden'] == 'none' else [values['hidden']], 'camera': values['camera']}
    if kind == 'fall':
        return {'kind': 'fall', 'usd': assets[values['item']]['usd'], 'outcome': values['outcome'], 'drop_m': values['drop_m'], 'gap_m': values['gap_m'],
                'restitution': values['restitution'], 'motion': 'scripted, kinematic, own light'}   # fall renders before this did not hold the item kinematic
    if kind == 'body':
        a = assets[values['moment']]
        return {'kind': 'body', 'rec': a['recording'], 'k': int(a['episode']), 'body': values['body'], 'motion': values['motion'],
                'keyframe_s': round(float(values['keyframe_s']), 3),
                'renderer': 'body-scene 4' if values['body'] == 'g1' else 'body-scene 1'}   # = feasibility/observer/body_scene.REVISION: a renderer change never reuses an old clip
    raise ValueError(kind)
