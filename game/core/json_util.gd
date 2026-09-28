class_name JsonUtil
extends RefCounted
## JSON helpers: strict file loading with error reporting, canonical
## (key-sorted) serialisation for checksums, and deep copies.


static func load_file(path: String, errors: Array = []) -> Variant:
	if not FileAccess.file_exists(path):
		errors.append("%s: file not found" % path)
		return null
	var text := FileAccess.get_file_as_string(path)
	var parser := JSON.new()
	var err := parser.parse(text)
	if err != OK:
		errors.append("%s:%d: %s" % [path, parser.get_error_line(), parser.get_error_message()])
		return null
	return parser.data


static func parse(text: String) -> Variant:
	var parser := JSON.new()
	if parser.parse(text) != OK:
		return null
	return parser.data


## Canonical JSON: dictionaries with sorted keys; ints and floats share one
## number format (JSON has a single number type, so 3 and 3.0 must hash alike).
static func canonical(value: Variant) -> String:
	match typeof(value):
		TYPE_DICTIONARY:
			var keys: Array = value.keys()
			keys.sort_custom(func(a, b): return str(a) < str(b))
			var parts := PackedStringArray()
			for k in keys:
				parts.append(JSON.stringify(str(k)) + ":" + canonical(value[k]))
			return "{" + ",".join(parts) + "}"
		TYPE_ARRAY, TYPE_PACKED_INT64_ARRAY, TYPE_PACKED_FLOAT64_ARRAY, TYPE_PACKED_STRING_ARRAY, TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_FLOAT32_ARRAY:
			var parts2 := PackedStringArray()
			for v in value:
				parts2.append(canonical(v))
			return "[" + ",".join(parts2) + "]"
		TYPE_FLOAT, TYPE_INT:
			var f := float(value)
			if is_nan(f) or is_inf(f):
				return "null"
			if f == floorf(f) and absf(f) < 1e15:
				return str(int(f))
			return String.num_scientific(f)
		TYPE_BOOL:
			return "true" if value else "false"
		TYPE_NIL:
			return "null"
		_:
			return JSON.stringify(str(value))


static func sha256(text: String) -> String:
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(text.to_utf8_buffer())
	return ctx.finish().hex_encode()


static func deep_copy(value: Variant) -> Variant:
	if value is Dictionary or value is Array:
		return value.duplicate(true)
	return value
