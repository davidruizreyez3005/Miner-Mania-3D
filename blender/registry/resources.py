"""Resource nodes: every node has full / damaged / depleted states exported as
separate GLBs (res_<id>.glb, res_<id>_damaged.glb, res_<id>_depleted.glb)."""

from core.definitions import ResourceDefinition as R

ASSETS = [
    R(id="res_ore_iron_01", seed=6101, budget="prop", texture_size=512, resource="iron", smoke=True,
      tags=("ore", "metal"), description="Iron ore node: rust-red veins and iron chunks"),
    R(id="res_ore_coal_01", seed=6102, budget="prop", texture_size=512, resource="coal",
      tags=("ore", "fuel"), description="Coal seam boulder with coal lumps"),
    R(id="res_ore_copper_01", seed=6103, budget="prop", texture_size=512, resource="copper",
      tags=("ore", "metal"), description="Copper ore node with green-blue veins and copper chunks"),
    R(id="res_ore_silver_01", seed=6104, budget="prop", texture_size=512, resource="silver",
      tags=("ore", "precious"), description="Silver ore node"),
    R(id="res_ore_gold_01", seed=6105, budget="prop", texture_size=512, resource="gold",
      tags=("ore", "precious"), description="Gold-bearing quartz with nuggets"),
    R(id="res_crystal_amethyst_01", seed=6106, budget="prop", texture_size=512, resource="amethyst",
      tags=("crystal", "rare"), description="Amethyst crystal cluster node (faint glow)"),
    R(id="res_gem_diamond_01", seed=6107, budget="prop", texture_size=512, resource="diamond",
      tags=("gem", "rare"), description="Diamond-bearing kimberlite with clear crystals"),
    R(id="res_ore_uranium_01", seed=6108, budget="prop", texture_size=512, resource="uranium",
      tags=("ore", "advanced"), description="Uranium ore with glowing green crystals"),
]
