extends Node
## Save files on disk. Writes are atomic (temp file + rename) and the previous
## save is kept as a backup; loading falls back to the backup when the main
## file is corrupt, and reports what happened. Encoding, integrity and
## migrations live in SaveCodec.

const DIR := "user://saves"
const MAIN := "user://saves/slot0.save"
const BACKUP := "user://saves/slot0.bak"
const TEMP := "user://saves/slot0.tmp"

var last_error: String = ""


func has_save() -> bool:
	return FileAccess.file_exists(MAIN) or FileAccess.file_exists(BACKUP)


func write(state: SimState, now_unix: int) -> bool:
	DirAccess.make_dir_recursive_absolute(DIR)
	var text := SaveCodec.encode(state, now_unix)
	var fh := FileAccess.open(TEMP, FileAccess.WRITE)
	if fh == null:
		last_error = "cannot open %s (%s)" % [TEMP, error_string(FileAccess.get_open_error())]
		EventBus.save_completed.emit(false, last_error)
		return false
	fh.store_string(text)
	fh.flush()
	fh.close()
	# Verify what landed on disk before replacing the good save.
	var check := SaveCodec.decode(FileAccess.get_file_as_string(TEMP))
	if not check.get("ok", false):
		last_error = "verification failed: %s" % check.get("error", "?")
		EventBus.save_completed.emit(false, last_error)
		return false
	var dir := DirAccess.open(DIR)
	if FileAccess.file_exists(MAIN):
		if FileAccess.file_exists(BACKUP):
			dir.remove(BACKUP.get_file())
		dir.rename(MAIN.get_file(), BACKUP.get_file())
	var err := dir.rename(TEMP.get_file(), MAIN.get_file())
	if err != OK:
		last_error = "rename failed: %s" % error_string(err)
		EventBus.save_completed.emit(false, last_error)
		return false
	last_error = ""
	EventBus.save_completed.emit(true, "")
	return true


## Returns {"ok", "state", "source": "main"|"backup", "error", "migrated_from"}.
func read() -> Dictionary:
	var errors := []
	for pair in [[MAIN, "main"], [BACKUP, "backup"]]:
		if not FileAccess.file_exists(pair[0]):
			continue
		var r := SaveCodec.decode(FileAccess.get_file_as_string(pair[0]))
		if r.get("ok", false):
			r["source"] = pair[1]
			if not errors.is_empty():
				r["recovered_from"] = errors
			return r
		errors.append("%s: %s" % [pair[1], r.get("error", "?")])
	if errors.is_empty():
		return {"ok": false, "error": "no_save"}
	last_error = ", ".join(PackedStringArray(errors))
	return {"ok": false, "error": "corrupt", "detail": last_error}


func delete_all() -> void:
	var dir := DirAccess.open(DIR)
	if dir == null:
		return
	for f in [MAIN, BACKUP, TEMP]:
		if FileAccess.file_exists(f):
			dir.remove(f.get_file())


## Moves unreadable saves aside so a new game does not overwrite evidence.
func quarantine() -> void:
	var dir := DirAccess.open(DIR)
	if dir == null:
		return
	var stamp := str(int(Time.get_unix_time_from_system()))
	for f in [MAIN, BACKUP]:
		if FileAccess.file_exists(f):
			dir.rename(f.get_file(), f.get_file() + ".corrupt-" + stamp)
