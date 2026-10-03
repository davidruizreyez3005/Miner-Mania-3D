class_name SalesSystem
extends RefCounted
## Trucks haul finished goods from the warehouse to the railhead market.
## Sale rate = trucks * truck capacity / round trip. Runs automatically with a
## sales manager (supervisor at the office) or the Automated Dispatch
## technology; otherwise each "Sell" dispatches one round trip. Trucks load
## the most valuable goods first. Revenue uses
## the item's value, the deterministic market cycle and all income modifiers.


static func truck_stats(sim: Simulation) -> Dictionary:
	var lvl := sim.facility_level("depot")
	var trucks := maxf(1.0, floorf(sim.content.facility_stat("depot", "trucks", lvl)))
	var cap := sim.content.facility_stat("depot", "truck_capacity", lvl) * sim.mods.m("truck_capacity")
	var trip := maxf(1.0, sim.content.facility_stat("depot", "trip_s", lvl) / sim.mods.m("sales_rate"))
	return {"trucks": int(trucks), "capacity": cap, "trip_s": trip, "rate": trucks * cap / trip}


## Sales run by themselves with the dispatch research or a sales manager
## hired at the office (also while the manager is on a break).
static func automatic(sim: Simulation) -> bool:
	if sim.mods.has_flag("auto_sales"):
		return true
	for w in sim.state.workers:
		if w["post"] == "office" and w["role"] == "supervisor":
			return true
	return false


static func tick(sim: Simulation, dt: float) -> void:
	var s := sim.state
	var ts := truck_stats(sim)
	var auto := automatic(sim)
	var manual := float(s.sales.get("manual_s", 0.0))
	var active := auto or manual > 0.0
	var earned := 0.0
	var sold := 0.0
	var by_item := {}
	if active:
		var total := Simulation.inv_total(s.warehouse)
		var amount := minf(float(ts["rate"]) * dt, total)
		if amount > 0.0:
			var taken := Simulation.inv_take_priority(s.warehouse, amount, sim.unit_value)
			for item in taken:
				var units: float = taken[item]
				var value := units * Economy.item_price(sim, item)
				earned += value
				sold += units
				s.stat_add("sold." + item, units)
				by_item[item] = units
				ProgressionSystem.on_sold(sim, item, units)
			s.money += earned
			s.stat_add("earned", earned)
			s.stat_add("sold_units", sold)
			s.stat_add("truck_trips", sold / maxf(1.0, float(ts["capacity"])))
			s.sales["sold"] = float(s.sales.get("sold", 0.0)) + sold
	if manual > 0.0:
		s.sales["manual_s"] = maxf(0.0, manual - dt)
	ProgressionSystem.update_sold_ema(sim, by_item, dt)
	_track_income(sim, earned, dt)
	ts["auto"] = auto
	ts["active"] = active
	ts["sold_rate"] = sold / dt
	ts["earn_rate"] = earned / dt
	sim.rt["sales"] = ts


static func _track_income(sim: Simulation, earned: float, dt: float) -> void:
	var s := sim.state
	var window := int(sim.content.bal("sim", "income_window_s", 60))
	if s.income_buckets.is_empty():
		s.income_buckets.append(0.0)
	s.income_buckets[s.income_buckets.size() - 1] = float(s.income_buckets[s.income_buckets.size() - 1]) + earned
	s.income_bucket_t += dt
	while s.income_bucket_t >= 1.0:
		s.income_bucket_t -= 1.0
		s.income_buckets.append(0.0)
		while s.income_buckets.size() > window + 1:
			s.income_buckets.remove_at(0)
	var sum := 0.0
	for b in s.income_buckets:
		sum += float(b)
	var span := maxf(1.0, float(s.income_buckets.size() - 1) + s.income_bucket_t)
	sim.rt["income_per_min"] = sum * 60.0 / span
	sim.rt["income_per_s"] = sum / span


## Goods to sell: in the warehouse, or on their way to it (at the headframe
## bin or in the cage while it winds). A truck sent early sells them as they
## arrive during its trip.
static func goods_coming(sim: Simulation) -> bool:
	var s := sim.state
	if Simulation.inv_total(s.warehouse) > 0.01 or Simulation.inv_total(s.surface_bin) > 0.01:
		return true
	var lift_running := TransportSystem.lift_automatic(sim) or float(s.lift.get("manual_s", 0.0)) > 0.0
	return lift_running and TransportSystem.stations_total(sim) > 0.01


static func dispatch(sim: Simulation) -> Dictionary:
	if automatic(sim):
		return {"ok": true, "auto": true}
	var ts := truck_stats(sim)
	var max_s := float(ts["trip_s"]) * float(sim.content.bal("sales", "manual_trips_max", 3))
	var cur := float(sim.state.sales.get("manual_s", 0.0))
	if cur >= max_s - 0.01:
		return {"ok": false, "error": "trucks_busy"}
	if not goods_coming(sim):
		return {"ok": false, "error": "warehouse_empty"}
	sim.state.sales["manual_s"] = minf(max_s, cur + float(ts["trip_s"]))
	sim.emit("sales_dispatched", {"trip_s": ts["trip_s"]})
	return {"ok": true, "trip_s": ts["trip_s"]}
