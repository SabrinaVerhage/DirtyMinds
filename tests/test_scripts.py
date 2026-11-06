import io
import json
import unittest
from unittest.mock import patch

from dirtyminds.core import INGREDIENTS
from dirtyminds.scripts import DEFAULT_MODEL, ScriptRequest, choose_tactics, generate_pitches


class ScriptTests(unittest.TestCase):
    def test_tactics_change_for_every_character(self):
        first = choose_tactics()
        second = choose_tactics(first)
        self.assertEqual(len(set(second)), 4)
        self.assertTrue(all(a != b for a, b in zip(first, second)))

    def test_rest_payload_and_fixed_character_introductions(self):
        pitch = "Take one cool sip and let the salty little secret linger."
        reply = {"status": "completed", "output": [
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"pitches": [pitch] * 4})}]},
        ]}
        with patch("dirtyminds.scripts.urllib.request.build_opener") as opener:
            open_response = opener.return_value.open
            open_response.return_value = io.BytesIO(json.dumps(reply).encode())
            pitches = generate_pitches("test-key", DEFAULT_MODEL, choose_tactics())
        request = open_response.call_args.args[0]
        payload = json.loads(request.data)
        self.assertFalse(payload["store"])
        self.assertEqual([item["character"] for item in json.loads(payload["input"])],
                         [item.character for item in INGREDIENTS])
        self.assertEqual(pitches, tuple(f"{item.introduction} {pitch}" for item in INGREDIENTS))

    def test_invalid_response_falls_back_without_logging_provider_body(self):
        with patch("dirtyminds.scripts.generate_pitches", side_effect=ValueError("secret")):
            job = ScriptRequest("test-key", DEFAULT_MODEL, choose_tactics())
            result, status = job.results.get(timeout=1)
        self.assertIsNone(result)
        self.assertIn("house scripts", status)
        self.assertNotIn("secret", status)
