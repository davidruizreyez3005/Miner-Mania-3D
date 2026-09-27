"""Mining vehicles: wheels/tracks, steering, suspension, lights, operator
position and entry points; clips are in place with speeds in the metadata."""

from core.definitions import VehicleDefinition as V

ASSETS = [
    V(id="veh_mining_truck_01", generator="vehicles.truck", seed=5101, budget="hero_machinery", smoke=True,
      tags=("truck", "haulage"), description="Rigid-frame haul truck with tipping dump body"),
    V(id="veh_excavator_01", generator="vehicles.excavator", seed=5102, budget="hero_machinery",
      tags=("excavator", "digging", "tracked"), description="Tracked hydraulic excavator with moving track pads"),
    V(id="veh_loader_01", generator="vehicles.loader", seed=5103, budget="hero_machinery",
      tags=("loader", "digging"), description="Articulated wheel loader with lift arms and bucket"),
    # Origin at rail-head level; wheel flanges drop 25 mm below it (inside the rails).
    V(id="veh_mine_cart_01", generator="vehicles.mine_cart", seed=5104, budget="prop",
      params={"origin": "embedded"}, tags=("rail", "haulage"), description="Side-tipping 600 mm gauge rail mine cart"),
    V(id="veh_utility_01", generator="vehicles.utility", seed=5105, budget="important_prop",
      tags=("utility", "transport"), description="Site 4x4 service pickup with light bar and ladder rack"),
]
