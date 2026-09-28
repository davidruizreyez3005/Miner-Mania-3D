extends SceneTree
## Headless test runner.
##
##   godot --headless --path . --script res://tests/run_tests.gd -- [--filter <substr>] \
##         [--junit <path>] [--json <path>]
##
## Runs every test_* method of every tests/unit/test_*.gd script. Engine and
## script errors raised while a test runs are captured by a Logger and fail
## that test, so a runtime error can never pass silently. Exit code 0 = all
## passed, 1 = failures.

const TEST_DIR := "res://tests/unit"


class ErrorCapture extends Logger:
	var errors: Array = []
	var mutex := Mutex.new()

	func _log_error(function: String, file: String, line: int, code: String, rationale: String, _editor_notify: bool,
			error_type: int, _script_backtraces: Array) -> void:
		mutex.lock()
		errors.append("%s %s:%d %s %s" % ["SCRIPT ERROR" if error_type == ERROR_TYPE_SCRIPT else "ERROR", file, line, function, rationale if rationale != "" else code])
		mutex.unlock()

	func _log_message(_message: String, _error: bool) -> void:
		pass

	func take() -> Array:
		mutex.lock()
		var out := errors
		errors = []
		mutex.unlock()
		return out


func _initialize() -> void:
	# World tests add nodes to the tree; the root is only inside the tree
	# once the first frame starts.
	await process_frame
	var args := _args()
	var capture := ErrorCapture.new()
	OS.add_logger(capture)
	var files := []
	for f in DirAccess.get_files_at(TEST_DIR):
		if f.begins_with("test_") and f.ends_with(".gd"):
			files.append(f)
	files.sort()
	var results := []
	var n_fail := 0
	var t_start := Time.get_ticks_msec()
	for f in files:
		var script: GDScript = load(TEST_DIR.path_join(f))
		if script == null or not script.can_instantiate():
			results.append({"suite": f, "name": "<load>", "ok": false, "messages": ["could not load " + f] + capture.take(), "ms": 0})
			n_fail += 1
			continue
		var methods := []
		for m in script.get_script_method_list():
			var mname := String(m["name"])
			if mname.begins_with("test_") and not mname in methods:
				methods.append(mname)
		methods.sort()
		for mname in methods:
			if args.has("filter") and not (f + "::" + mname).contains(args["filter"]):
				continue
			var inst: TestCase = script.new()
			inst.current_test = mname
			capture.take()
			var t0 := Time.get_ticks_usec()
			inst.before_each()
			inst.call(mname)
			inst.after_each()
			var ms := float(Time.get_ticks_usec() - t0) / 1000.0
			var msgs: Array = inst.failures.duplicate()
			msgs.append_array(capture.take())
			var ok := msgs.is_empty()
			if not ok:
				n_fail += 1
			results.append({"suite": f.get_basename(), "name": mname, "ok": ok, "messages": msgs, "ms": ms})
			print("%s %s::%s (%.1f ms)" % ["PASS" if ok else "FAIL", f.get_basename(), mname, ms])
			for msg in msgs:
				print("     - " + str(msg))
	var total := results.size()
	var elapsed := float(Time.get_ticks_msec() - t_start) / 1000.0
	print("\n%d tests, %d passed, %d failed in %.1fs" % [total, total - n_fail, n_fail, elapsed])
	if args.has("json"):
		_write(args["json"], JSON.stringify({"total": total, "failed": n_fail, "seconds": elapsed, "results": results}, "  "))
	if args.has("junit"):
		_write(args["junit"], _junit(results, elapsed))
	OS.remove_logger(capture)
	quit(1 if n_fail > 0 or total == 0 else 0)


func _args() -> Dictionary:
	var out := {}
	var a := OS.get_cmdline_user_args()
	var i := 0
	while i < a.size():
		if a[i].begins_with("--") and i + 1 < a.size():
			out[a[i].substr(2)] = a[i + 1]
			i += 2
		else:
			i += 1
	return out


func _write(path: String, text: String) -> void:
	var p := path if path.is_absolute_path() or path.begins_with("res://") or path.begins_with("user://") else ProjectSettings.globalize_path("res://").path_join(path)
	DirAccess.make_dir_recursive_absolute(p.get_base_dir())
	var fh := FileAccess.open(p, FileAccess.WRITE)
	if fh:
		fh.store_string(text)
		fh.close()


func _junit(results: Array, elapsed: float) -> String:
	var suites := {}
	for r in results:
		if not suites.has(r["suite"]):
			suites[r["suite"]] = []
		suites[r["suite"]].append(r)
	var x := "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<testsuites time=\"%.3f\">\n" % elapsed
	for s in suites:
		var fails := 0
		for r in suites[s]:
			if not r["ok"]:
				fails += 1
		x += "  <testsuite name=\"%s\" tests=\"%d\" failures=\"%d\">\n" % [s, suites[s].size(), fails]
		for r in suites[s]:
			x += "    <testcase classname=\"%s\" name=\"%s\" time=\"%.4f\">" % [s, r["name"], float(r["ms"]) / 1000.0]
			if not r["ok"]:
				var msg := "\n".join(PackedStringArray(r["messages"])).xml_escape()
				x += "<failure message=\"%s\">%s</failure>" % [msg.substr(0, 200), msg]
			x += "</testcase>\n"
		x += "  </testsuite>\n"
	return x + "</testsuites>\n"
