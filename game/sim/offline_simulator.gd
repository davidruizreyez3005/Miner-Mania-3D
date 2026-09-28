class_name OfflineSimulator
extends RefCounted
## Real offline progression: the time the player was away is validated and
## then simulated with the same Simulation.tick() as live play, in coarse
## steps (mining handles vein depletion inside a step, flows are rate-based,
## so coarse steps stay close to live results). Only automated stages keep
## running: manual lift calls and truck dispatches do not persist, so an
## unautomated mine earns little while you are away - by design.
##
## Guards: negative elapsed time (clock moved back), timestamps in the far
## future, corrupted values, and very long absences (capped by the offline
## cap). A clock rollback never grants time and a rewarded period is never
## rewarded twice (the high-water mark max_seen_unix only moves forward).


## Validates wall-clock timestamps and returns {elapsed, status, credited}.
static func evaluate(sim: Simulation, now_unix: int) -> Dictionary:
	var meta := sim.state.meta
	var last := int(meta.get("last_save_unix", 0))
	var high := maxi(int(meta.get("max_seen_unix", 0)), last)
	var tol := int(sim.content.bal("offline", "future_tolerance_s", 120))
	var min_away := float(sim.content.bal("offline", "min_away_s", 60))
	if last <= 0 or now_unix <= 0:
		return {"elapsed": 0.0, "credited": 0.0, "status": "no_timestamp"}
	if now_unix + tol < high:
		return {"elapsed": 0.0, "credited": 0.0, "status": "clock_rollback"}
	var elapsed := float(now_unix - high)
	if elapsed < min_away:
		return {"elapsed": maxf(0.0, elapsed), "credited": 0.0, "status": "too_short"}
	var cap := Economy.offline_cap_s(sim)
	var eff := Economy.offline_efficiency(sim)
	var credited := minf(elapsed, cap) * eff
	return {"elapsed": elapsed, "credited": credited, "capped": elapsed > cap, "cap_s": cap,
		"efficiency": eff, "status": "ok"}


## Simulates `seconds` of offline time and reports what happened.
static func simulate(sim: Simulation, seconds: float) -> Dictionary:
	var s := sim.state
	var before_run := s.run_stats.duplicate()
	var before_money := s.money
	var before_disc := s.discoveries.keys()
	var t0 := Time.get_ticks_usec()
	var target_steps := float(sim.content.bal("offline", "target_steps", 2400))
	var step := clampf(seconds / target_steps, float(sim.content.bal("offline", "min_step_s", 1.0)),
		float(sim.content.bal("offline", "max_step_s", 30.0)))
	sim.offline_mode = true
	s.lift["manual_s"] = 0.0
	s.sales["manual_s"] = 0.0
	var steps := 0
	var left := maxf(0.0, seconds)
	while left > 1e-9:
		var dt := minf(step, left)
		sim.tick(dt)
		left -= dt
		steps += 1
	sim.offline_mode = false
	var mined := {}
	for k in s.run_stats:
		if String(k).begins_with("mined.") and String(k) != "mined_units":
			var diff := float(s.run_stats[k]) - float(before_run.get(k, 0.0))
			if diff > 1e-6:
				mined[String(k).substr(6)] = diff
	var new_disc := []
	for k in s.discoveries:
		if not k in before_disc:
			new_disc.append(k)
	var report := {
		"seconds": seconds, "steps": steps, "step_s": step,
		"mined": mined,
		"mined_units": float(s.run_stats.get("mined_units", 0.0)) - float(before_run.get("mined_units", 0.0)),
		"processed_units": float(s.run_stats.get("processed_units", 0.0)) - float(before_run.get("processed_units", 0.0)),
		"sold_units": float(s.run_stats.get("sold_units", 0.0)) - float(before_run.get("sold_units", 0.0)),
		"earned": float(s.run_stats.get("earned", 0.0)) - float(before_run.get("earned", 0.0)),
		"money_delta": s.money - before_money,
		"discoveries": new_disc,
		"compute_ms": float(Time.get_ticks_usec() - t0) / 1000.0,
	}
	s.stat_max("offline_best_s", seconds)
	return report
