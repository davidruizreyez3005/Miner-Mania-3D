extends SceneTree
## Balance/pacing report: an AutoplayBot plays N hours of game time and the
## milestone timeline, stage rates and bottlenecks are printed.
##
##   godot --headless --path . --script res://tools/godot/balance_report.gd -- [--hours 6] [--seed 1] [--prestige] [--json out.json]


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var hours := 6.0
	var seed_value := 1
	var json_out := ""
	var i := 0
	while i < args.size():
		match args[i]:
			"--hours":
				hours = float(args[i + 1])
				i += 1
			"--seed":
				seed_value = int(args[i + 1])
				i += 1
			"--json":
				json_out = args[i + 1]
				i += 1
		i += 1
	var sim := Simulation.new(ContentDB.load_default())
	sim.new_game(seed_value)
	var bot := AutoplayBot.new(sim)
	bot.allow_prestige = "--prestige" in args
	var t0 := Time.get_ticks_msec()
	var report_every := 1800.0
	var played := 0.0
	var snapshots := []
	while played < hours * 3600.0:
		bot.play(report_every, 0.5)
		played += report_every
		var r := bot.stage_rates()
		var snap := {
			"t_min": snappedf(sim.state.total_time / 60.0, 0.1), "money": sim.state.money,
			"earned": float(sim.state.run_stats.get("earned", 0.0)), "income_min": float(sim.rt.get("income_per_min", 0.0)),
			"depth": sim.state.deepest_unlocked(), "workers": sim.state.workers.size(), "techs": sim.state.techs.size(),
			"stage": sim.automation_stage(), "rates": r, "rp": sim.state.research_points,
			"prestige": sim.state.prestige.duplicate(),
		}
		snapshots.append(snap)
		print("t=%6.1f min  money=%-8s earned=%-8s income=%-8s/min depth=%d workers=%d techs=%d stage=%d | mine=%.2f lift=%.2f plant=%.2f sales=%.2f bn=%s stall=%s" % [
			snap["t_min"], Num.short(sim.state.money), Num.short(snap["earned"]), Num.short(snap["income_min"]),
			snap["depth"], snap["workers"], snap["techs"], snap["stage"], r["mining"], r["lift"], r["plant"], r["sales"], r["bottleneck"], r["stalled"]])
	print("\nMilestones (minutes):")
	var keys: Array = bot.milestones.keys()
	keys.sort_custom(func(a, b): return float(bot.milestones[a]) < float(bot.milestones[b]))
	for k in keys:
		print("  %-18s %7.1f" % [k, float(bot.milestones[k]) / 60.0])
	print("\nDepth levels:")
	for dep in sim.state.depths:
		if dep["unlocked"]:
			print("  depth %d: %s tool %d workers %d" % [dep["index"], str(dep["levels"]), dep["tool_tier"], sim.workers_at("depth:%d" % dep["index"]).size()])
	for fid in sim.state.facilities:
		if sim.facility_built(fid):
			print("  %-10s L%d cond %.2f" % [fid, sim.facility_level(fid), float(sim.state.facilities[fid]["condition"])])
	print("\nquests claimed: %d, achievements: %d, discoveries: %d" % [
		ProgressionSystem.objective_progress(sim, {"type": "quests", "target": 1})[0], sim.state.achievements.size(), sim.state.discoveries.size()])
	print("simulated %.1f h in %.1f s" % [hours, float(Time.get_ticks_msec() - t0) / 1000.0])
	if json_out != "":
		var fh := FileAccess.open(json_out, FileAccess.WRITE)
		fh.store_string(JSON.stringify({"milestones": bot.milestones, "snapshots": snapshots}, "  "))
	quit(0)
