"""The neutral scene format. Every generation method produces one of these; one composer turns it into USD.

Units are metres and degrees, Z is up. An object's position is the centre of its bottom face, and
rotation_deg turns it about its own axes. An asset is either a USD file (referenced as-is) or a mesh
file that an importer converts to USD first.

Hierarchy: Scene > Room > Wall, and Scene > SceneObject > Asset. Lights and cameras sit on the scene.
Each object keeps where it came from (source) and how it was placed, so the interface can show provenance
and the agent can say which method produced which object.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json


@dataclass
class Asset:
    path: str                      # USD or mesh file on disk
    format: str                    # usd, usda, usdz, glb, gltf, obj, ply, stl
    texture_path: str | None = None
    facing_yaw_deg: float = 0.0    # turn that makes the asset face -Y (towards a default camera)


@dataclass
class Source:
    method: str                    # sage_layout, file_upload, library, procedural_script, cosmos, scan
    collection: str | None = None  # SAGE-10k, Palatial, SimReady, user upload ...
    record_id: str | None = None   # id inside that collection
    licence: str | None = None


@dataclass
class SceneObject:
    id: str
    label: str
    asset: Asset
    source: Source
    position_m: list[float]                     # bottom centre, world frame
    rotation_deg: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    size_m: list[float] | None = None           # target width, length, height; None keeps the asset's own size
    description: str = ''
    placed_on: str | None = None                # floor, wall, or another object's id
    role: str = 'context'                       # context, manipulated, control


@dataclass
class Wall:
    id: str
    start_m: list[float]
    end_m: list[float]
    height_m: float
    thickness_m: float
    colour_rgb: list[float] = field(default_factory=lambda: [0.8, 0.8, 0.8])


@dataclass
class Room:
    id: str
    room_type: str
    origin_m: list[float]
    size_m: list[float]                         # width, length, height
    walls: list[Wall] = field(default_factory=list)
    floor_colour_rgb: list[float] = field(default_factory=lambda: [0.5, 0.5, 0.5])


@dataclass
class Scene:
    id: str
    name: str
    source: Source
    rooms: list[Room] = field(default_factory=list)
    objects: list[SceneObject] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)   # what an importer could not bring in, and why

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)

    @staticmethod
    def from_json(text: str) -> 'Scene':
        d = json.loads(text)
        rooms = [Room(**{**r, 'walls': [Wall(**w) for w in r['walls']]}) for r in d['rooms']]
        objs = [SceneObject(**{**o, 'asset': Asset(**o['asset']), 'source': Source(**o['source'])}) for o in d['objects']]
        return Scene(id=d['id'], name=d['name'], source=Source(**d['source']), rooms=rooms, objects=objs, skipped=d.get('skipped', []))
