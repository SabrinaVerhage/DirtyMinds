"""Optional writing for the fictional clinic. The recipe is calculated locally."""
from itertools import permutations
import json
import queue
import random
import re
import threading
import time
import urllib.error
import urllib.request

from .core import INGREDIENTS, PROFESSOR_PROTOCOL
from .voice import NoRedirect

DEFAULT_MODEL = "gpt-5.4-mini"
TACTICS = (
    "confide a ridiculous little secret",
    "issue a playful cocktail dare",
    "offer a very official-sounding promise",
    "paint a sensory picture of the first sip",
    "tell a tiny joke with a briny punchline",
)


def choose_tactics(previous=()):
    choices = [order for order in permutations(TACTICS, len(INGREDIENTS))
               if all(new != old for new, old in zip(order, previous))]
    return random.choice(choices)


CLINIC = (
    "Write for Dirty Minds, the Department of Inappropriate Responses, a fictional "
    "cocktail clinic. The patient is ready for the experiment. Three talking "
    "brines are diagnostic stimuli. The institution takes itself very seriously. "
    "Keep the humour suggestive, playful and non-explicit. Avoid real medical advice "
    "or claims about what the patient thinks, desires, or feels."
)


def _write(api_key, model, instructions, context, fields, timeout):
    payload = {
        "model": model, "store": False, "max_output_tokens": 350,
        "instructions": f"{CLINIC} {instructions}",
        "input": json.dumps(context, ensure_ascii=False),
        "text": {"format": {
            "type": "json_schema", "name": "clinic_copy", "strict": True,
            "schema": {
                "type": "object", "additionalProperties": False, "required": list(fields),
                "properties": {key: {"type": "string"} for key in fields},
            },
        }},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
        data = json.loads(response.read(65_536))
    if data.get("status") != "completed":
        raise ValueError("Incomplete response")
    output = "".join(part["text"] for item in data["output"] if item["type"] == "message"
                     for part in item["content"] if part["type"] == "output_text")
    result = json.loads(output)
    for field, (min_words, max_words, max_length) in fields.items():
        value = result[field]
        if not isinstance(value, str) or any(ch in value for ch in "[]<>"):
            raise ValueError("Invalid clinic copy")
        result[field] = value = " ".join(value.split())
        if not min_words <= len(value.split()) <= max_words or len(value) > max_length:
            raise ValueError("Invalid clinic copy length")
    return result


def generate_intro(api_key, model):
    result = _write(api_key, model,
                    "Write a short English opening spoken by the professor on duty. "
                    "They are a very dry, quietly pedantic scientific lecturer. "
                    "Introduce the fictional department and make one original deadpan "
                    "lab-protocol or cocktail pun. Use 12–26 words in plain dialogue. "
                    "Keep a straight face. Do not give the procedure instructions, "
                    "which are appended separately. Skip all equipment, seating and headphone instructions.",
                    {"department": "Department of Inappropriate Responses",
                     "comic_angle": random.choice(TACTICS)}, {"opening": (8, 30, 210)}, timeout=4)
    opening = result["opening"].rstrip(".!?")
    if re.search(r"\b(?:headphones?|contacts?|gloves?|seated|sit down|take a seat|fingers?)\b", opening, re.I):
        raise ValueError("Unexpected setup instructions")
    return f"{opening}. {PROFESSOR_PROTOCOL}"


def generate_lines(api_key, model, tactics):
    cast = {item.key: {"name": item.name, "character": item.character,
                       "example": item.pitch, "approach": tactic}
            for item, tactic in zip(INGREDIENTS, tactics)}
    lines = _write(api_key, model,
                  "Write one distinct first-person whisper for each character in English, "
                  "with 26–42 words in short, unhurried phrases. Each character is trying to seduce the listener "
                  "into choosing their own juice for the automated martini. Coax them with intimate, "
                  "suggestive cocktail double meanings. Make the machine part of the temptation: "
                  "liquid winding through tubing, the motor humming beside the wiring, a slow pump pulse, "
                  "or drops gathering in the cold glass. Describe what the juice adds to the drink. "
                  "Give each character a distinct sensory selling angle. "
                  "They remain anonymous. Never name a character, vegetable or ingredient, or use an introduction. "
                  "Use their sense of humour without phonetic accent spellings. "
                  "Use each suggested approach in that character’s own voice. Use plain dialogue.",
                  cast, {item.key: (20, 48, 320) for item in INGREDIENTS}, timeout=8)
    if any(re.search(r"\b(?:onions?|olives?|jalape[nñ]os?)\b|\bi(?:'|’)?m (?:the|a)\b", line, re.I)
           for line in lines.values()):
        raise ValueError("A character introduced themselves")
    return lines


def generate_name(api_key, model, amounts, lead_pitch, recent_names):
    brines = {item.name: round(ml, 3) for item, ml in zip(INGREDIENTS, amounts) if ml}
    result = _write(api_key, model,
                    "Invent one original dirty martini menu name in 2–7 words. "
                    "Anchor the name in the exact selling pitch the patient responded to most. "
                    "Turn a memorable image, phrase, flavour or adjective from that pitch into a cheeky "
                    "cocktail pun. Use the actual blend as secondary context. Return a new menu title "
                    "without quotes, directions, measurements or extra ingredients. Avoid all recent titles.",
                    {"strongest_voice_pitch": lead_pitch, "prescribed_brine_ml": brines,
                     "recent_titles": list(recent_names)}, {"name": (2, 7, 56)}, timeout=4)
    return result["name"]


class WritingRequest:
    """A disposable result queue keeps cancelled appointments isolated from later ones."""

    def __init__(self, write, *args):
        self.result = queue.Queue(maxsize=1)
        self.thread = threading.Thread(target=self._run, args=(write, args), daemon=True)
        self.thread.start()

    def _run(self, write, args):
        started = time.monotonic()
        value = None
        try:
            value = write(*args)
            status = "succeeded"
        except urllib.error.HTTPError as exc:
            status = f"failed (HTTP {exc.code})"
        except (TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            status = "timed out" if isinstance(reason, TimeoutError) else "failed (network)"
        except OSError:
            status = "failed (network)"
        except (ValueError, KeyError, TypeError, AttributeError):
            status = "failed (incomplete or invalid response)"
        self.result.put_nowait((value, f"{status} in {time.monotonic() - started:.2f} s"))
