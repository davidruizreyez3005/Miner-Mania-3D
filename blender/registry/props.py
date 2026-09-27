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
    P(id="prop_pallet_01", generator="props.misc", seed=2121, budget="tiny_prop", params={"kind": "pallet"},
      tags=("logistics",), description="EUR pallet (1200 x 800 mm)"),
    P(id="prop_gas_cylinder_01", generator="props.misc", seed=2122, budget="tiny_prop",
      params={"kind": "gas_cylinder", "color": "machine_blue"}, tags=("container", "carryable"), description="Gas cylinder, blue"),
    P(id="prop_gas_cylinder_02", generator="props.misc", seed=2123, budget="tiny_prop",
      params={"kind": "gas_cylinder", "color": "signal_red"}, tags=("container", "carryable"), description="Gas cylinder, red"),
    P(id="prop_ore_sack_01", generator="props.misc", seed=2124, budget="tiny_prop", params={"kind": "ore_sack"},
      tags=("container", "carryable"), description="Filled jute ore sack"),
    P(id="prop_cone_01", generator="props.misc", seed=2125, budget="tiny_prop", params={"kind": "cone"},
      tags=("safety",), description="Traffic cone"),
    P(id="prop_workbench_01", generator="props.misc", seed=2126, budget="tiny_prop", params={"kind": "workbench"},
      tags=("furniture", "interactive"), description="Steel workbench at the contract bench height"),
    P(id="prop_bench_01", generator="props.misc", seed=2127, budget="tiny_prop", params={"kind": "bench_seat"},
      tags=("furniture", "interactive"), description="Bench seat at the contract seat height (Sit clip)"),
]
