"""Optional one-request writing pass for the four fictional characters."""
from itertools import permutations
import json
import queue
import random
import threading
import urllib.error
import urllib.request

from .core import INGREDIENTS
from .voice import NoRedirect

DEFAULT_MODEL = "gpt-5.4-mini"
TACTICS = (
    "confide a ridiculous little secret",
    "issue a playful cocktail dare",
    "make a grand promise in the style of a tiny speakeasy",
    "paint a sensory picture of the first sip",
    "tell a tiny joke with a briny punchline",
)
CAST = ("sweet, layered, and sharp", "velvety, salty, and classic",
        "green, bright, and hot", "crisp, sour, and Dutch")


def choose_tactics(previous=()):
    choices = [order for order in permutations(TACTICS, len(INGREDIENTS))
               if all(new != old for new, old in zip(order, previous))]
    return random.choice(choices)


def generate_pitches(api_key, model, tactics):
    cast = [{"ingredient": item.name, "character": item.character, "traits": traits, "approach": tactic}
            for item, traits, tactic in zip(INGREDIENTS, CAST, tactics)]
    payload = {
        "model": model,
        "store": False,
        "max_output_tokens": 600,
        "reasoning": {"effort": "none"},
        "instructions": (
            "Write four short first-person spoken cocktail pitches for a cheeky cabaret about talking brines. "
            "Use the approaches and cast in order. Keep the flirtation light and the imagery about taste, "
            "ice, and brine. Write 18 to 34 words per pitch in short sentences. Skip character introductions, "
            "stage directions, and claims about what the listener thinks or feels."
        ),
        "input": json.dumps(cast, ensure_ascii=False),
        "text": {"format": {
            "type": "json_schema", "name": "brine_pitches", "strict": True,
            "schema": {
                "type": "object", "additionalProperties": False, "required": ["pitches"],
                "properties": {"pitches": {"type": "array", "minItems": 4, "maxItems": 4,
                                            "items": {"type": "string"}}},
            },
        }},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
        data = json.loads(response.read(65_537))
    if data.get("status") != "completed":
        raise ValueError("Incomplete script")
    output = "".join(part["text"] for item in data["output"] if item["type"] == "message"
                     for part in item["content"] if part["type"] == "output_text")
    pitches = json.loads(output)["pitches"]
    if not isinstance(pitches, list) or len(pitches) != len(INGREDIENTS):
        raise ValueError("Missing pitches")
    if any(not isinstance(pitch, str) or not 8 <= len(pitch.split()) <= 45
           or len(pitch) > 300 or any(ch in pitch for ch in "[]<>") for pitch in pitches):
        raise ValueError("Invalid pitch")
    return tuple(f"{item.introduction} {' '.join(pitch.split())}" for item, pitch in zip(INGREDIENTS, pitches))


class ScriptRequest:
    """One background request per session. The UI takes its result at round one."""

    def __init__(self, api_key, model, tactics):
        self.tactics = tactics
        self.results = queue.Queue(maxsize=1)
        self.thread = threading.Thread(target=self._run, args=(api_key, model), daemon=True)
        self.thread.start()

    def _run(self, api_key, model):
        try:
            result = generate_pitches(api_key, model, self.tactics), "Fresh pitches ready."
        except urllib.error.HTTPError as exc:
            result = None, f"OpenAI returned HTTP {exc.code}. Using house scripts."
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            result = None, "OpenAI pitches unavailable. Using house scripts."
        self.results.put_nowait(result)
