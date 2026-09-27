"""Per-asset build context handed to generators.

Generators describe *what* to build (geometry parts, bones, sockets,
collision proxies, animation clips, metadata); the stage pipeline decides how
it is baked, optimized, validated and exported.
"""

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from mathutils import Matrix, Vector

from . import paths
from .rng import Rng


@dataclass
class BoneSpec:
    name: str
    head: tuple
    tail: tuple
    parent: Optional[str] = "root"
    z_axis: Optional[tuple] = None   # roll hint: local Z points along this vector
    deform: bool = True


@dataclass
class SocketSpec:
    name: str
    matrix: Matrix
    bone: Optional[str] = None


@dataclass
class CollisionSpec:
    kind: str              # box | cylinder | hull | capsule
    matrix: Matrix
    size: tuple = (1.0, 1.0, 1.0)
    radius: float = 0.5
    height: float = 1.0
    points: list = field(default_factory=list)
    segments: int = 12


@dataclass
class ClipSpec:
    """Procedural clip for rigid rigs: ``fn(t) -> {bone: (loc|None, quat|None)}``."""
    name: str
    duration: float
    loop: bool
    fn: Callable
    description: str = ""


@dataclass
class OutputRecord:
    name: str
    state: str
    model: str = ""
    lods: list = field(default_factory=list)
    collision: Optional[str] = None
    triangles: int = 0
    lod_triangles: list = field(default_factory=list)
    materials: int = 0
    textures: int = 0
    texture_resolution: int = 0
    skeleton: bool = False
    bones: int = 0
    animations: list = field(default_factory=list)
    animation_details: dict = field(default_factory=dict)
    dimensions: list = field(default_factory=list)
    bounds_min: list = field(default_factory=list)
    bounds_max: list = field(default_factory=list)
    file_size: int = 0
    sha256: str = ""
    uv: dict = field(default_factory=dict)
    collision_shapes: int = 0
    sockets: list = field(default_factory=list)
    validated: bool = False
    checks: dict = field(default_factory=dict)


class BuildContext:
    def __init__(self, definition, cfg, library_factory, options):
        self.defn = definition
        self.id = definition.id
        self.cfg = cfg
        self.options = options
        self._library_factory = library_factory
        self.timings = {}
        self.warnings = []
        self.outputs = []
        self.state = None
        self.work_dir = os.path.join(paths.WORK_DIR, definition.id)

    # -- lifecycle ---------------------------------------------------------
    def begin_state(self, state):
        self.state = state
        self.name = self.defn.output_name(state)
        self.rng = Rng(self.defn.seed, self.id)                   # identical for all states
        self.state_rng = Rng(self.defn.seed, f"{self.id}/{state}")
        self.lib = self._library_factory()
        self.geos = []
        self.objects = []
        self.armature = None
        self.bones = []
        self.sockets = []
        self.collision = []
        self.clips = []
        self.character = None
        self.metadata = {}
        self.parts = []
        self.final_objects = []
        self.lod_objects = []
        self.collision_objects = []
        self.record = OutputRecord(self.name, state)
        self.uv_stats = {}
        self.texture_paths = {}

    @property
    def budget(self):
        return self.cfg["budgets"][self.defn.budget]

    @property
    def category_cfg(self):
        return self.cfg["categories"][self.defn.category]

    @property
    def texture_size(self):
        return int(self.defn.texture_size or self.budget["texture"])

    @property
    def lod_ratios(self):
        return tuple(self.defn.lods if self.defn.lods is not None else self.budget["lods"])

    def param(self, key, default=None):
        return self.defn.params.get(key, default)

    # -- geometry ----------------------------------------------------------
    def geo(self, name, bone=None, max_lod=99, attach=None, shade="auto", smooth_angle=32.0, weighted=True):
        from utilities.meshkit import Geo
        g = Geo(f"{self.name}__{name}", mm_part=name, mm_max_lod=int(max_lod))
        if bone:
            g.props["mm_bone"] = bone
        if attach:
            g.props["mm_attach_bone"] = attach
        g.props["_shade"] = shade
        g.props["_smooth_angle"] = smooth_angle
        g.props["_weighted"] = weighted
        self.geos.append(g)
        return g

    def finalize_geos(self):
        for g in self.geos:
            if g.is_empty():
                continue
            shade = g.props.pop("_shade", "auto")
            angle = g.props.pop("_smooth_angle", 32.0)
            weighted = g.props.pop("_weighted", True)
            obj = g.to_object(self.lib, smooth_angle=angle, weighted_normals=weighted, shade=shade)
            self.objects.append(obj)
        self.geos = []

    # -- rig / sockets / collision / clips --------------------------------
    def bone(self, name, head, tail=None, parent="root", z_axis=None, deform=True):
        h = Vector(head)
        t = Vector(tail) if tail is not None else h + Vector((0.0, 0.0, 0.25))
        self.bones.append(BoneSpec(name, tuple(h), tuple(t), parent, tuple(z_axis) if z_axis else None, deform))

    def socket(self, name, loc, rot=None, bone=None):
        from utilities.meshkit import trs
        self.sockets.append(SocketSpec(name, trs(loc, rot), bone))

    def col_box(self, center, size, rot=None):
        from utilities.meshkit import trs
        self.collision.append(CollisionSpec("box", trs(center, rot), size=tuple(size)))

    def col_cylinder(self, center, radius, height, rot=None, segments=12):
        from utilities.meshkit import trs
        self.collision.append(CollisionSpec("cylinder", trs(center, rot), radius=radius, height=height,
                                            segments=segments))

    def col_hull(self, points):
        self.collision.append(CollisionSpec("hull", Matrix.Identity(4), points=[tuple(p) for p in points]))

    def col_capsule(self, radius, height):
        self.collision.append(CollisionSpec("capsule", Matrix.Identity(4), radius=radius, height=height))

    def clip(self, name, duration, loop, fn, description=""):
        self.clips.append(ClipSpec(name, duration, loop, fn, description))

    def warn(self, code, message):
        self.warnings.append({"code": code, "message": message, "state": self.state})
