class_name TestCase
extends RefCounted
## Base class for headless unit tests (see tests/run_tests.gd). Test methods
## are named test_*; assertions record failures instead of aborting so one
## run reports everything.

static var _content: ContentDB

var failures: Array = []
var current_test: String = ""


static func content() -> ContentDB:
	if _content == null:
		_content = ContentDB.load_default()
	return _content


func before_each() -> void:
	pass


func after_each() -> void:
	pass


## A fresh simulation on the shipped content (optionally a fixed seed).
func make_sim(seed_value: int = 1234) -> Simulation:
	var sim := Simulation.new(content())
	sim.new_game(seed_value)
	return sim


func fail(msg: String) -> void:
	failures.append("%s: %s" % [current_test, msg])


func assert_true(cond: bool, msg: String = "expected true") -> bool:
	if not cond:
		fail(msg)
	return cond


func assert_false(cond: bool, msg: String = "expected false") -> bool:
	return assert_true(not cond, msg)


func assert_eq(actual: Variant, expected: Variant, msg: String = "") -> bool:
	var same: bool = typeof(actual) == typeof(expected) and actual == expected
	if not same and (actual is float or actual is int) and (expected is float or expected is int):
		same = float(actual) == float(expected)
	if not same:
		fail("%s expected <%s> got <%s>" % [msg, str(expected), str(actual)])
	return same


func assert_near(actual: float, expected: float, tol: float, msg: String = "") -> bool:
	var ok := absf(actual - expected) <= tol
	if not ok:
		fail("%s expected %s +- %s got %s" % [msg, str(expected), str(tol), str(actual)])
	return ok


func assert_rel(actual: float, expected: float, rel: float, msg: String = "") -> bool:
	var tol := absf(expected) * rel
	return assert_near(actual, expected, maxf(tol, 1e-9), msg)


func assert_gt(a: float, b: float, msg: String = "") -> bool:
	if not a > b:
		fail("%s expected %s > %s" % [msg, str(a), str(b)])
		return false
	return true


func assert_ge(a: float, b: float, msg: String = "") -> bool:
	if not a >= b:
		fail("%s expected %s >= %s" % [msg, str(a), str(b)])
		return false
	return true


func assert_lt(a: float, b: float, msg: String = "") -> bool:
	if not a < b:
		fail("%s expected %s < %s" % [msg, str(a), str(b)])
		return false
	return true


func assert_ok(result: Dictionary, msg: String = "") -> bool:
	if not result.get("ok", false):
		fail("%s command failed: %s" % [msg, str(result)])
		return false
	return true


func assert_err(result: Dictionary, code: String, msg: String = "") -> bool:
	if result.get("ok", false) or String(result.get("error", "")) != code:
		fail("%s expected error '%s' got %s" % [msg, code, str(result)])
		return false
	return true


func assert_finite_state(sim: Simulation, msg: String = "") -> bool:
	var s := sim.state
	var bad := []
	if is_nan(s.money) or is_inf(s.money) or s.money < 0.0:
		bad.append("money=%s" % s.money)
	if is_nan(s.research_points) or s.research_points < 0.0:
		bad.append("rp")
	for dep in s.depths:
		for inv in [dep["face"], dep["station"]]:
			for k in inv:
				if is_nan(float(inv[k])) or float(inv[k]) < -1e-6:
					bad.append("depth %d %s=%s" % [dep["index"], k, inv[k]])
	for inv2 in [s.surface_bin, s.warehouse]:
		for k in inv2:
			if is_nan(float(inv2[k])) or float(inv2[k]) < -1e-6:
				bad.append("%s=%s" % [k, inv2[k]])
	if not bad.is_empty():
		fail("%s non-finite/negative state: %s" % [msg, ", ".join(PackedStringArray(bad))])
		return false
	return true
