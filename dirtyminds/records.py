"""Anonymous local aggregate results, saved after each round and delivery."""
from datetime import datetime, timezone
import json


def new_record_path(directory):
    return directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + ".json")


def save_record(path, session, *, source, mode, durations, voices, scripts=()):
    record = session.record()
    record.update(updated_utc=datetime.now(timezone.utc).isoformat(), input=source,
                  delivery_mode=mode, durations_ms=durations, round_voices=voices,
                  round_scripts=list(scripts)[:len(session.results)])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)
