"""Hand tools and handheld equipment (grip-space origin, attach to hand_tool.R/L)."""

from core.definitions import ToolDefinition as T

ASSETS = [
    T(id="tool_pickaxe_01", generator="props.tools", seed=3101, budget="tiny_prop", texture_size=512,
      params={"kind": "pickaxe", "grip": "pickaxe", "origin": "grip"}, tags=("two_handed", "mining"),
      description="Pickaxe; left-hand grip 0.30 m down the handle"),
    T(id="tool_sledgehammer_01", generator="props.tools", seed=3102, budget="tiny_prop", texture_size=512,
      params={"kind": "sledgehammer", "grip": "pickaxe", "origin": "grip"}, tags=("two_handed",)),
    T(id="tool_shovel_01", generator="props.tools", seed=3103, budget="tiny_prop", texture_size=512,
      params={"kind": "shovel", "grip": "shovel", "origin": "grip"}, tags=("two_handed", "digging")),
    T(id="tool_jackhammer_01", generator="props.tools", seed=3104, budget="prop", texture_size=512,
      params={"kind": "jackhammer", "grip": "jackhammer", "origin": "grip"}, tags=("two_handed", "mining")),
    T(id="tool_hammer_01", generator="props.tools", seed=3105, budget="tiny_prop", texture_size=256,
      params={"kind": "hammer", "origin": "grip"}, tags=("one_handed",)),
    T(id="tool_wrench_01", generator="props.tools", seed=3106, budget="tiny_prop", texture_size=256,
      params={"kind": "wrench", "origin": "grip"}, tags=("one_handed", "repair")),
    T(id="tool_rock_hammer_01", generator="props.tools", seed=3107, budget="tiny_prop", texture_size=256,
      params={"kind": "rock_hammer", "origin": "grip"}, tags=("one_handed", "survey")),
    T(id="tool_tablet_01", generator="props.tools", seed=3108, budget="tiny_prop", texture_size=256,
      params={"kind": "tablet", "origin": "grip"}, tags=("one_handed",)),
    T(id="tool_clipboard_01", generator="props.tools", seed=3109, budget="tiny_prop", texture_size=256,
      params={"kind": "clipboard", "origin": "grip"}, tags=("one_handed",)),
    T(id="tool_radio_01", generator="props.tools", seed=3110, budget="tiny_prop", texture_size=256,
      params={"kind": "radio", "origin": "grip"}, tags=("one_handed",)),
    T(id="tool_remote_control_01", generator="props.tools", seed=3111, budget="tiny_prop", texture_size=256,
      params={"kind": "remote_control", "origin": "grip"}, tags=("one_handed", "operator")),
    T(id="tool_toolbox_01", generator="props.tools", seed=3112, budget="tiny_prop", texture_size=256,
      params={"kind": "toolbox", "origin": "grip"}, tags=("one_handed", "engineer")),
    T(id="tool_scanner_01", generator="props.tools", seed=3113, budget="tiny_prop", texture_size=256,
      params={"kind": "scanner", "origin": "grip"}, tags=("one_handed", "survey")),
    T(id="tool_lantern_01", generator="props.tools", seed=3114, budget="tiny_prop", texture_size=256,
      params={"kind": "lantern", "origin": "grip"}, tags=("one_handed",)),
]


def by_id(asset_id):
    for a in ASSETS:
        if a.id == asset_id:
            return a
    raise KeyError(asset_id)
