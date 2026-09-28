class_name DetRng
extends RefCounted
## Deterministic, platform-independent PRNG (xoshiro128**) implemented with
## 32-bit arithmetic that never overflows GDScript's signed 64-bit ints.
## Streams are derived from string keys (FNV-1a), so a value such as "the
## resource of vein 3 at depth 2 after its 5th respawn" is reproducible
## regardless of tick size or evaluation order.

const MASK := 0xFFFFFFFF

var _s: PackedInt64Array = PackedInt64Array([0, 0, 0, 0])


func _init(seed_value: int = 1) -> void:
	set_seed(seed_value)


static func from_key(seed_value: int, key: String) -> DetRng:
	return DetRng.new(hash32(key, seed_value & MASK) ^ ((seed_value >> 32) & MASK))


func set_seed(seed_value: int) -> void:
	var x := seed_value & MASK
	var y := (seed_value >> 32) & MASK
	for i in 4:
		x = mix32((x + 0x9E3779B9 * (i + 1)) & MASK ^ y)
		_s[i] = x if x != 0 else 0x6D2B79F5
	for i in 4:
		next_u32()


func get_state() -> Array:
	return [_s[0], _s[1], _s[2], _s[3]]


func set_state(st: Array) -> void:
	if st.size() != 4:
		return
	for i in 4:
		_s[i] = int(st[i]) & MASK
	if _s[0] == 0 and _s[1] == 0 and _s[2] == 0 and _s[3] == 0:
		_s[0] = 1


static func rotl(x: int, k: int) -> int:
	return ((x << k) | (x >> (32 - k))) & MASK


## (a * b) mod 2^32 without 64-bit overflow.
static func mul32(a: int, b: int) -> int:
	a &= MASK
	b &= MASK
	var lo := (a & 0xFFFF) * b
	var hi := (((a >> 16) * b) & 0xFFFF) << 16
	return (lo + hi) & MASK


## lowbias32 integer hash.
static func mix32(x: int) -> int:
	x &= MASK
	x ^= x >> 16
	x = mul32(x, 0x7FEB352D)
	x ^= x >> 15
	x = mul32(x, 0x846CA68B)
	x ^= x >> 16
	return x & MASK


## FNV-1a over the UTF-8 bytes of `key`, finalised with mix32.
static func hash32(key: String, salt: int = 0) -> int:
	var h := (0x811C9DC5 ^ (salt & MASK)) & MASK
	for b in key.to_utf8_buffer():
		h ^= b
		h = mul32(h, 0x01000193)
	return mix32(h)


func next_u32() -> int:
	var s0 := _s[0]
	var s1 := _s[1]
	var s2 := _s[2]
	var s3 := _s[3]
	var result := mul32(rotl(mul32(s1, 5), 7), 9)
	var t := (s1 << 9) & MASK
	s2 ^= s0
	s3 ^= s1
	s1 ^= s2
	s0 ^= s3
	s2 ^= t
	s3 = rotl(s3, 11)
	_s[0] = s0 & MASK
	_s[1] = s1 & MASK
	_s[2] = s2 & MASK
	_s[3] = s3 & MASK
	return result


## Uniform float in [0, 1).
func next_float() -> float:
	return float(next_u32()) / 4294967296.0


func range_f(lo: float, hi: float) -> float:
	return lo + (hi - lo) * next_float()


## Uniform int in [lo, hi] inclusive.
func range_i(lo: int, hi: int) -> int:
	if hi <= lo:
		return lo
	return lo + int(next_u32() % (hi - lo + 1))


## Picks a key from {key: weight} deterministically (keys sorted first).
func weighted_key(weights: Dictionary) -> String:
	var keys := weights.keys()
	keys.sort()
	var total := 0.0
	for k in keys:
		total += maxf(0.0, float(weights[k]))
	if total <= 0.0:
		return String(keys[0]) if not keys.is_empty() else ""
	var r := next_float() * total
	for k in keys:
		r -= maxf(0.0, float(weights[k]))
		if r < 0.0:
			return String(k)
	return String(keys[keys.size() - 1])
