"""Prop asset definitions."""

from core.definitions import PropDefinition as P

ASSETS = [
    P(id="prop_barrel_oil_01", generator="props.barrel", seed=2101, budget="prop", smoke=True,
      params={"color": "signal_red"}, tags=("container",), description="Steel oil drum, red"),
    P(id="prop_barrel_oil_02", generator="props.barrel", seed=2102, budget="prop",
      params={"color": "machine_blue"}, tags=("container",), description="Steel oil drum, blue"),
    P(id="prop_barrel_wood_01", generator="props.barrel", seed=2103, budget="prop",
      params={"style": "wood"}, tags=("container",), description="Banded wooden barrel"),
    P(id="prop_crate_wood_01", generator="props.crate", seed=2111, budget="prop",
      params={"size": (0.9, 0.7, 0.7)}, tags=("container",), description="Large wooden crate"),
    P(id="prop_crate_wood_02", generator="props.crate", seed=2112, budget="prop",
      params={"size": (0.6, 0.5, 0.45), "wood": "wood_weathered:wood_weathered"}, tags=("container",),
      description="Small weathered crate"),
    P(id="prop_crate_carry_01", generator="props.crate", seed=2113, budget="prop",
      params={"size": (0.46, 0.36, 0.36), "carry": True, "frame": 0.05}, tags=("container", "carryable"),
      description="Standard carry crate matching the worker carry animations (grip width 0.51 m)"),
]
