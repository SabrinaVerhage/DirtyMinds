"""Anonymous local aggregate results, saved after each round and delivery."""
from datetime import datetime, timezone
import json
import math

from .core import DEFAULT_PUMP_ORDER, INGREDIENTS, LEGACY_PUMP_ORDER

CONNECTION_FIELDS = ("feather_ip", "gsr_usb", "pump_usb")


def load_connections(path):
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(values, dict):
        return {}
    return {key: values[key] for key in CONNECTION_FIELDS if isinstance(values.get(key), str)}


def save_connections(path, values):
    _write_json(path, {key: values[key] for key in CONNECTION_FIELDS if key in values})


def load_pump_order(path):
    try:
        order = tuple(json.loads(path.read_text(encoding="utf-8"))["pump_order"])
        if len(order) == len(INGREDIENTS) and set(order) == set(DEFAULT_PUMP_ORDER):
            return order
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return DEFAULT_PUMP_ORDER


def save_pump_order(path, order):
    if len(order) != len(INGREDIENTS) or set(order) != set(DEFAULT_PUMP_ORDER):
        raise ValueError("Assign each brine to one pump.")
    _write_json(path, {"pump_order": list(order)})


def load_pump_calibration(path, pump_order=DEFAULT_PUMP_ORDER):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if tuple(data.get("pump_order", LEGACY_PUMP_ORDER)) != pump_order:
            return ()
        saved = data["ml_per_second"]
        rates = tuple(saved[item.key] for item in INGREDIENTS)
        if all(type(rate) in (int, float) and math.isfinite(rate) and rate > 0 for rate in rates):
            return rates
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        pass
    return ()


def save_pump_calibration(path, rates, pump_order=DEFAULT_PUMP_ORDER):
    _write_json(path, {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "pump_order": list(pump_order),
        "ml_per_second": {item.key: rate for item, rate in zip(INGREDIENTS, rates)},
    })


def recent_recipe_names(directory, limit=24):
    names = []
    for path in sorted(directory.glob("*.json"), reverse=True)[:limit]:
        try:
            name = json.loads(path.read_text(encoding="utf-8"))["recipe"]["name"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(name, str) and 0 < len(name) <= 80:
            names.append(name)
    return names


def new_record_path(directory):
    return directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + ".json")


def save_record(path, session, *, source, mode, durations, voices, scripts=(), pump_rates=(),
                pump_order=DEFAULT_PUMP_ORDER):
    record = session.record()
    record.update(updated_utc=datetime.now(timezone.utc).isoformat(), input=source,
                  delivery_mode=mode, durations_ms=durations, round_voices=voices,
                  pump_channels=dict(enumerate(pump_order, 1)),
                  round_scripts=list(scripts)[:len(session.results)])
    if session.recipe:
        record["recipe"]["brines_ml"] = {
            item.key: ml for item, ml in zip(INGREDIENTS, session.recipe.amounts) if ml
        }
        record["recipe"]["brine_percentages"] = {
            item.key: round(ml / session.recipe.brine_ml * 100, 3)
            for item, ml in zip(INGREDIENTS, session.recipe.amounts)
        }
        if durations and pump_rates:
            record["recipe"]["estimated_brines_ml"] = {
                item.key: round(durations[pump_order.index(item.key)] * rate / 1000, 4)
                for item, rate in zip(INGREDIENTS, pump_rates)
            }
    _write_json(path, record)


def _write_json(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)
