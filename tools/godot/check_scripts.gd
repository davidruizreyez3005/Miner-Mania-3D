extends SceneTree
## Static check: parses and compiles every GDScript file in the project and
## fails on any parse/compile error or warning treated as error.
##
##   godot --headless --path . --script res://tools/godot/check_scripts.gd -- [--report <path>]

const ROOTS := ["res://game", "res://tests", "res://tools/godot"]
const SKIP := ["res://tools/godot/check_scripts.gd"]


class Capture extends Logger:
	var errors: Array = []

	func _log_error(function: String, file: String, line: int, code: String, rationale: String, _editor_notify: bool,
			_error_type: int, _script_backtraces: Array) -> void:
		errors.append("%s:%d %s %s" % [file, line, function, rationale if rationale != "" else code])

	func _log_message(_message: String, _error: bool) -> void:
		pass


func _initialize() -> void:
	var cap := Capture.new()
	OS.add_logger(cap)
	var files := []
	for r in ROOTS:
		_collect(r, files)
	files.sort()
	var failed := []
	for f in files:
		if f in SKIP:
			continue
		cap.errors.clear()
		# An uncached load parses, analyses and compiles the script; any error is logged.
		var s: Script = ResourceLoader.load(f, "", ResourceLoader.CACHE_MODE_IGNORE)
		var ok := s != null and cap.errors.is_empty()
		if ok and s is GDScript:
			ok = (s as GDScript).can_instantiate()
		if not ok:
			failed.append({"file": f, "errors": cap.errors.duplicate()})
			print("FAIL ", f)
			for e in cap.errors:
				print("   ", e)
	print("check_scripts: %d files, %d failed" % [files.size() - SKIP.size(), failed.size()])
	var args := OS.get_cmdline_user_args()
	var idx := args.find("--report")
	if idx >= 0 and idx + 1 < args.size():
		var fh := FileAccess.open(args[idx + 1], FileAccess.WRITE)
		if fh:
			fh.store_string(JSON.stringify({"files": files.size(), "failed": failed}, "  "))
	OS.remove_logger(cap)
	quit(1 if not failed.is_empty() else 0)


func _collect(dir: String, out: Array) -> void:
	for f in DirAccess.get_files_at(dir):
		if f.ends_with(".gd"):
			out.append(dir.path_join(f))
	for d in DirAccess.get_directories_at(dir):
		_collect(dir.path_join(d), out)
