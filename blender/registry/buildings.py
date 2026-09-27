"""Building asset definitions (animated doors, gates and hoist gear)."""

from core.definitions import BuildingDefinition as B

ASSETS = [
    B(id="bld_mine_entrance_01", generator="buildings.mine_entrance", seed=4001, budget="large_structure",
      tags=("mine", "entrance"), description="Mine portal in a rock hillside with gates, track and a tunnel section"),
    B(id="bld_headframe_01", generator="buildings.headframe", seed=4002, budget="large_structure",
      tags=("mine", "shaft", "animated"), description="Shaft headframe with animated sheave, cage and rope, plus winder house"),
    B(id="bld_warehouse_01", generator="buildings.warehouse", seed=4003, budget="large_structure",
      tags=("storage",), description="Portal-frame warehouse with roll-up and personnel doors"),
    B(id="bld_office_01", generator="buildings.office", seed=4004, budget="large_structure",
      tags=("office",), description="Portable site office with steps and hinged door"),
    B(id="bld_workshop_01", generator="buildings.workshop", seed=4005, budget="large_structure",
      tags=("maintenance",), description="Open-front workshop with workbench and travelling hoist"),
]
