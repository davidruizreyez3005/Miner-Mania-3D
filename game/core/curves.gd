class_name Curves
extends RefCounted
## Stat and cost curves shared by every levelled thing (see data/facilities.json).
##   stat:  {"mode": "mult"|"add"|"exp", "base", "per_level", "growth" (compounding, mult/exp modes), "step" (add mode),
##           "milestones": [[lvl, mult]...] | "default",
##           "steps": [[lvl, add]...], "max"}
##   cost:  {"base", "growth"} -> cost of going from level L to L+1 = base * growth^(L-1)


static func stat(spec: Dictionary, level: int, default_milestones: Array = []) -> float:
	var lv := maxi(level, 1)
	var base := float(spec.get("base", 0.0))
	var value: float
	var mode := String(spec.get("mode", "mult"))
	if mode == "add":
		value = base + float(spec.get("step", 0.0)) * float(lv - 1)
	elif mode == "exp":
		value = base * pow(float(spec.get("growth", 1.0)), float(lv - 1))
	else:
		value = base * (1.0 + float(spec.get("per_level", 0.0)) * float(lv - 1))
		if spec.has("growth"):
			value *= pow(float(spec["growth"]), float(lv - 1))
	var ms = spec.get("milestones", [])
	if ms is String and ms == "default":
		ms = default_milestones
	if ms is Array:
		for m in ms:
			if lv >= int(m[0]):
				value *= float(m[1])
	var steps = spec.get("steps", [])
	if steps is Array:
		for s in steps:
			if lv >= int(s[0]):
				value += float(s[1])
	if spec.has("max"):
		value = minf(value, float(spec["max"]))
	return value


static func cost(spec: Dictionary, level: int, scale: float = 1.0) -> float:
	var lv := maxi(level, 1)
	return float(spec.get("base", 0.0)) * pow(float(spec.get("growth", 1.0)), float(lv - 1)) * scale


## Total cost of buying `count` levels starting at `level`.
static func cost_n(spec: Dictionary, level: int, count: int, scale: float = 1.0) -> float:
	var g := float(spec.get("growth", 1.0))
	var first := cost(spec, level, scale)
	if count <= 1:
		return first
	if absf(g - 1.0) < 1e-9:
		return first * count
	return first * (pow(g, count) - 1.0) / (g - 1.0)


## Largest number of levels affordable with `money` (bounded by max_count).
static func affordable(spec: Dictionary, level: int, money: float, max_count: int, scale: float = 1.0) -> int:
	var g := float(spec.get("growth", 1.0))
	var first := cost(spec, level, scale)
	if first <= 0.0:
		return max_count
	if money < first:
		return 0
	var n: int
	if absf(g - 1.0) < 1e-9:
		n = int(floorf(money / first))
	else:
		n = int(floorf(log(money * (g - 1.0) / first + 1.0) / log(g)))
	n = clampi(n, 0, max_count)
	while n > 0 and cost_n(spec, level, n, scale) > money * (1.0 + 1e-9):
		n -= 1
	return n
