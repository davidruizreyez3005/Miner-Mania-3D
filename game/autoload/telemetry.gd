extends Node
## Analytics/telemetry hook. The game never sends data anywhere: events go to
## a local ring buffer (and, when enabled in settings, to user://telemetry.log)
## so a backend can be plugged in later by replacing `sink`.

const MAX_EVENTS := 256

var events: Array = []
var counters: Dictionary = {}
var sink: Callable = Callable()


func track(event: String, props: Dictionary = {}) -> void:
	var e := {"event": event, "t": Time.get_ticks_msec(), "props": props}
	events.append(e)
	if events.size() > MAX_EVENTS:
		events.remove_at(0)
	counters[event] = int(counters.get(event, 0)) + 1
	if sink.is_valid():
		sink.call(e)
	elif Settings.get_value("telemetry_log", false):
		var fh := FileAccess.open("user://telemetry.log", FileAccess.READ_WRITE if FileAccess.file_exists("user://telemetry.log") else FileAccess.WRITE)
		if fh:
			fh.seek_end()
			fh.store_line(JSON.stringify(e))
