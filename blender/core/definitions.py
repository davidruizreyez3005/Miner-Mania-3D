"""Typed asset definitions.

Adding content to the game means registering one of these in
``blender/registry``; the build pipeline itself never changes. Each definition
carries an explicit seed, a generator reference and intentional parameters::

    WorkerDefinition(id="chr_worker_miner_01", role="miner", body_type="standard",
                     helmet="hardhat_lamp", tool="pickaxe", seed=1001)
"""

import re
from dataclasses import dataclass, field, fields
from typing import ClassVar, Optional, Tuple

ID_PATTERN = re.compile(r"^(chr|mach|veh|bld|env|res|prop|tool|eqp)_[a-z0-9]+(_[a-z0-9]+)*_\d{2}$")
ANIM_ID_PATTERN = re.compile(r"^anim_[a-z0-9]+(_[a-z0-9]+)*$")
STATE_PATTERN = re.compile(r"^[a-z][a-z0-9]*$")


@dataclass(frozen=True)
class AssetDefinition:
    id: str
    generator: str = ""
    params: dict = field(default_factory=dict)
    seed: int = 1
    budget: str = "prop"
    texture_size: Optional[int] = None
    lods: Optional[Tuple[float, ...]] = None
    collision: str = "convex"
    animations: Tuple[str, ...] = ()
    states: Tuple[str, ...] = ("default",)
    smoke: bool = False
    tags: Tuple[str, ...] = ()
    description: str = ""

    category: ClassVar[str] = "prop"
    default_generator: ClassVar[str] = ""

    @property
    def generator_name(self):
        return self.generator or self.default_generator

    def output_name(self, state):
        """File stem for a state; the default/first state uses the bare id."""
        if state in ("default", self.states[0]):
            return self.id
        return f"{self.id}_{state}"

    def describe(self):
        out = {"id": self.id, "category": self.category, "generator": self.generator_name}
        for f in fields(self):
            if f.name in ("id", "generator"):
                continue
            value = getattr(self, f.name)
            out[f.name] = list(value) if isinstance(value, tuple) else value
        return out


@dataclass(frozen=True)
class WorkerDefinition(AssetDefinition):
    role: str = "miner"
    body_type: str = "standard"          # slim | standard | stocky | heavy
    presentation: str = "masculine"      # masculine | feminine
    skin_tone: str = "skin_3"
    hair_style: str = "short"            # none | buzz | short | side_part | curly | ponytail | bun | long
    hair_color: str = "hair_brown"
    beard: str = "none"                  # none | stubble | full | mustache | goatee
    eye_color: str = "iris_brown"
    brows: str = "normal"
    glasses: bool = False
    outfit: str = "work_shirt"           # work_shirt | hivis_vest | hivis_jacket | coveralls | field_vest | supervisor
    outfit_colors: dict = field(default_factory=dict)
    sleeves: str = "long"                # long | rolled | short
    helmet: str = "hardhat"              # none | hardhat | hardhat_lamp | cap | beanie | bush_hat
    helmet_color: str = "industrial_yellow"
    ear_protection: bool = False
    gloves: str = "work"                 # none | work | rubber
    boots: str = "work"
    equipment: Tuple[str, ...] = ()      # tool_belt | backpack | radio | pouch
    tool: Optional[str] = None           # asset id of the right-hand tool
    off_hand_tool: Optional[str] = None  # asset id of the left-hand tool

    category: ClassVar[str] = "character"
    default_generator: ClassVar[str] = "characters.worker"


@dataclass(frozen=True)
class MannequinDefinition(AssetDefinition):
    category: ClassVar[str] = "character"
    default_generator: ClassVar[str] = "characters.mannequin"


@dataclass(frozen=True)
class AnimationLibraryDefinition(AssetDefinition):
    category: ClassVar[str] = "animation"
    default_generator: ClassVar[str] = "characters.animation_library"


@dataclass(frozen=True)
class MachineDefinition(AssetDefinition):
    category: ClassVar[str] = "machinery"


@dataclass(frozen=True)
class VehicleDefinition(AssetDefinition):
    category: ClassVar[str] = "vehicle"


@dataclass(frozen=True)
class BuildingDefinition(AssetDefinition):
    category: ClassVar[str] = "building"


@dataclass(frozen=True)
class EnvironmentDefinition(AssetDefinition):
    category: ClassVar[str] = "environment"


@dataclass(frozen=True)
class ResourceDefinition(AssetDefinition):
    resource: str = "iron"
    states: Tuple[str, ...] = ("full", "damaged", "depleted")

    category: ClassVar[str] = "resource"
    default_generator: ClassVar[str] = "resources.ore_node"


@dataclass(frozen=True)
class PropDefinition(AssetDefinition):
    category: ClassVar[str] = "prop"


@dataclass(frozen=True)
class ToolDefinition(AssetDefinition):
    collision: str = "convex"
    category: ClassVar[str] = "tool"


@dataclass(frozen=True)
class EquipmentDefinition(AssetDefinition):
    category: ClassVar[str] = "equipment"
