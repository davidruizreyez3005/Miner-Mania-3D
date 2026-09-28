extends Node
## Global signal hub. Systems publish facts here; nothing listens by reaching
## into another system's internals. Simulation events arrive through
## sim_event (one Dictionary per event, see Simulation.emit).

signal sim_event(ev: Dictionary)
signal command_result(cmd: Dictionary, result: Dictionary)
signal state_changed(from_state: int, to_state: int)
signal toast(text: String, kind: String)
signal panel_requested(panel: String, args: Dictionary)
signal panel_closed(panel: String)
signal focus_requested(target: String)
signal selection_changed(target: String)
signal tutorial_event(name: String)
signal settings_changed(key: String, value: Variant)
signal loading_progress(fraction: float, label: String)
signal offline_report(report: Dictionary)
signal world_ready()
signal save_completed(ok: bool, error: String)
signal quality_changed(level: int)


func tutorial(name: String) -> void:
	tutorial_event.emit(name)


func notify(text: String, kind: String = "info") -> void:
	toast.emit(text, kind)
