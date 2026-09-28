extends TestCase
## Core utilities: deterministic RNG, stat/cost curves, number formatting.


func test_rng_deterministic() -> void:
	var a := DetRng.new(42)
	var b := DetRng.new(42)
	for i in 1000:
		if a.next_u32() != b.next_u32():
			fail("streams diverged at %d" % i)
			return
	var c := DetRng.new(43)
	var same := 0
	for i in 100:
		if a.next_u32() == c.next_u32():
			same += 1
	assert_lt(same, 3, "different seeds must differ")


func test_rng_known_values() -> void:
	## Pinned outputs: a platform or refactor change in the generator breaks saves' determinism.
	assert_eq(DetRng.mul32(0xFFFFFFFF, 0xFFFFFFFF), 1, "mul32 wraps")
	assert_eq(DetRng.mul32(123456789, 987654321), (123456789 * 987654321) & 0xFFFFFFFF, "mul32 small")
	assert_eq(DetRng.hash32("abc"), DetRng.hash32("abc"))
	assert_true(DetRng.hash32("abc") != DetRng.hash32("abd"))
	var r := DetRng.new(7)
	var first := [r.next_u32(), r.next_u32(), r.next_u32()]
	var r2 := DetRng.new(7)
	assert_eq([r2.next_u32(), r2.next_u32(), r2.next_u32()], first)


func test_rng_distribution() -> void:
	var r := DetRng.new(99)
	var sum := 0.0
	var lo := 1.0
	var hi := 0.0
	for i in 20000:
		var f := r.next_float()
		sum += f
		lo = minf(lo, f)
		hi = maxf(hi, f)
	assert_near(sum / 20000.0, 0.5, 0.01, "mean")
	assert_ge(lo, 0.0)
	assert_lt(hi, 1.0)
	var counts := {"a": 0, "b": 0}
	for i in 10000:
		counts[r.weighted_key({"a": 3.0, "b": 1.0})] += 1
	assert_near(float(counts["a"]) / 10000.0, 0.75, 0.02, "weighted pick")


func test_rng_state_roundtrip() -> void:
	var r := DetRng.new(5)
	r.next_u32()
	var st := r.get_state()
	var v := r.next_u32()
	var r2 := DetRng.new(1)
	r2.set_state(st)
	assert_eq(r2.next_u32(), v)


func test_stat_curves() -> void:
	var spec := {"base": 2.0, "per_level": 0.5, "milestones": [[10, 2.0], [25, 3.0]]}
	assert_near(Curves.stat(spec, 1), 2.0, 1e-9)
	assert_near(Curves.stat(spec, 9), 2.0 * 5.0, 1e-9)
	assert_near(Curves.stat(spec, 10), 2.0 * 5.5 * 2.0, 1e-9)
	assert_near(Curves.stat(spec, 25), 2.0 * 13.0 * 6.0, 1e-9)
	var add := {"mode": "add", "base": 0.0, "step": 0.3}
	assert_near(Curves.stat(add, 1), 0.0, 1e-9)
	assert_near(Curves.stat(add, 11), 3.0, 1e-9)
	var steps := {"base": 2, "per_level": 0.0, "steps": [[5, 1], [10, 1]], "max": 3}
	assert_near(Curves.stat(steps, 4), 2.0, 1e-9)
	assert_near(Curves.stat(steps, 5), 3.0, 1e-9)
	assert_near(Curves.stat(steps, 50), 3.0, 1e-9, "clamped to max")


func test_cost_curves() -> void:
	var spec := {"base": 10.0, "growth": 1.15}
	var sum := 0.0
	for l in range(3, 13):
		sum += Curves.cost(spec, l)
	assert_rel(Curves.cost_n(spec, 3, 10), sum, 1e-9, "geometric sum")
	var n := Curves.affordable(spec, 3, sum, 1000)
	assert_eq(n, 10, "affordable exactly")
	assert_eq(Curves.affordable(spec, 3, sum - 0.01, 1000), 9, "one short")
	assert_eq(Curves.affordable(spec, 3, 1e30, 7), 7, "bounded")


func test_number_format() -> void:
	assert_eq(Num.short(0), "0")
	assert_eq(Num.short(999), "999")
	assert_eq(Num.short(1500), "1.5K")
	assert_eq(Num.short(1234567), "1.23M")
	assert_eq(Num.short(999999), "1M")
	assert_eq(Num.short(2.5e12), "2.5T")
	assert_eq(Num.money(12), "$12")
	assert_eq(Num.duration(3725), "1h 02m")
	assert_eq(Num.duration(59), "59s")
