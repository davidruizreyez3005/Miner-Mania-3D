"""Mining machinery. Moving parts are rigid-skinned to mechanical bones and
animated with functional clips (see generators/machinery/*)."""

from core.definitions import MachineDefinition as M

ASSETS = [
    M(id="mach_drill_01", generator="machinery.drill", seed=4101, budget="hero_machinery", smoke=True,
      tags=("drill", "extraction"), description="Skid-mounted rotary drill rig with feeding rotary head"),
    M(id="mach_crusher_01", generator="machinery.crusher", seed=4102, budget="hero_machinery",
      tags=("crusher", "processing"), description="Jaw crusher with flywheels, swing jaw, hopper and walkway"),
    M(id="mach_conveyor_01", generator="machinery.conveyor", seed=4103, budget="important_prop",
      params={"length": 6.0}, tags=("conveyor", "transport", "modular"),
      description="6 m troughed belt conveyor segment with moving cleats; chains via input/output sockets"),
    M(id="mach_pump_01", generator="machinery.pump", seed=4104, budget="important_prop",
      tags=("pump", "water"), description="Triplex plunger dewatering pump with belt drive and pressure gauge"),
    M(id="mach_generator_01", generator="machinery.generator", seed=4105, budget="important_prop",
      tags=("generator", "power"), description="Containerised diesel generator set"),
    M(id="mach_smelter_01", generator="machinery.smelter", seed=4106, budget="hero_machinery",
      tags=("smelter", "processing"), description="Tilting crucible smelter with fume hood and casting table"),
    M(id="mach_washer_01", generator="machinery.washer", seed=4107, budget="hero_machinery",
      tags=("washer", "processing"), description="Trommel drum washer with girth-gear drive and spray bar"),
    M(id="mach_sorter_01", generator="machinery.sorter", seed=4108, budget="important_prop",
      tags=("sorter", "processing"), description="Double-deck vibrating screen on coil springs"),
    M(id="mach_silo_01", generator="machinery.silo", seed=4109, budget="important_prop",
      tags=("storage",), description="Ore silo with slide gate, caged ladder and level gauge"),
    M(id="mach_processor_01", generator="machinery.processor", seed=4110, budget="hero_machinery",
      tags=("processing", "tank"), description="Agitated leach tank with launder, control valve and gauge"),
]
