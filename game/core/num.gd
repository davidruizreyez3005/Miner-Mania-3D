class_name Num
extends RefCounted
## Number, money and time formatting for the UI (idle-game suffixes).

const SUFFIXES := ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc", "Ud", "Dd", "Td"]


static func short(value: float, decimals: int = 2) -> String:
	if is_nan(value):
		return "0"
	if is_inf(value):
		return "inf"
	var neg := value < 0.0
	var v := absf(value)
	var out: String
	if v < 1000.0:
		if v < 10.0 and v != floorf(v):
			out = "%.1f" % v if v >= 1.0 else ("%.2f" % v if v > 0.0 else "0")
			out = out.trim_suffix("0").trim_suffix(".") if out.contains(".") else out
		else:
			out = str(int(floorf(v)))
	else:
		var tier := int(floorf(log(v) / log(1000.0)))
		tier = clampi(tier, 0, SUFFIXES.size() - 1)
		var scaled := v / pow(1000.0, tier)
		if scaled >= 999.995 and tier < SUFFIXES.size() - 1:
			tier += 1
			scaled = v / pow(1000.0, tier)
		var d := decimals if scaled < 100.0 else (1 if scaled < 1000.0 and decimals > 0 else 0)
		if scaled >= 100.0:
			d = 0
		out = ("%." + str(d) + "f") % scaled
		if out.contains("."):
			out = out.rstrip("0").trim_suffix(".")
		out += SUFFIXES[tier]
	return ("-" if neg else "") + out


static func money(value: float) -> String:
	return "$" + short(value)


static func rate(value_per_s: float, unit: String = "/s") -> String:
	return short(value_per_s) + unit


static func percent(fraction: float, decimals: int = 0) -> String:
	return ("%." + str(decimals) + "f%%") % (fraction * 100.0)


static func duration(seconds: float) -> String:
	var s := int(maxf(0.0, seconds))
	var d := s / 86400
	var h := (s % 86400) / 3600
	var m := (s % 3600) / 60
	var sec := s % 60
	if d > 0:
		return "%dd %dh" % [d, h]
	if h > 0:
		return "%dh %02dm" % [h, m]
	if m > 0:
		return "%dm %02ds" % [m, sec]
	return "%ds" % sec


static func mult(value: float) -> String:
	return "x" + short(value)
