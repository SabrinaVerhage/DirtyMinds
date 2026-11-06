import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from dirtyminds.core import INGREDIENTS, PROFESSOR_PROTOCOL
from dirtyminds.scripts import DEFAULT_MODEL, WritingRequest, choose_tactics, generate_intro, generate_lines, generate_name


class ScriptTests(unittest.TestCase):
    def test_tactics_change_for_every_character(self):
        first = choose_tactics()
        second = choose_tactics(first)
        self.assertEqual(len(set(second)), 3)
        self.assertTrue(all(a != b for a, b in zip(first, second)))

    def request(self, result, write, argument):
        reply = {"status": "completed", "output": [
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]},
        ]}
        with patch("dirtyminds.scripts.urllib.request.build_opener") as opener:
            open_response = opener.return_value.open
            open_response.return_value = io.BytesIO(json.dumps(reply).encode())
            value = write("test-key", DEFAULT_MODEL, *argument)
        request = open_response.call_args.args[0]
        return value, json.loads(request.data)

    def test_rest_payload_contains_three_separate_character_briefs(self):
        lines = {item.key: item.pitch for item in INGREDIENTS}
        result, payload = self.request(lines, generate_lines, (choose_tactics(),))
        self.assertFalse(payload["store"])
        cast = json.loads(payload["input"])
        self.assertEqual(list(cast), [item.key for item in INGREDIENTS])
        self.assertEqual(len({value["character"] for value in cast.values()}), 3)
        self.assertEqual(result, lines)

    def test_professor_opening_keeps_the_fixed_three_voice_protocol(self):
        opening = "I am the professor on duty. The findings were independently chilled."
        result, payload = self.request({"opening": opening}, generate_intro, ())
        self.assertEqual(result, f"{opening} {PROFESSOR_PROTOCOL}")
        self.assertIn("scientific lecturer", payload["instructions"])

    def test_pitch_rejects_spoken_character_name(self):
        lines = {item.key: item.pitch for item in INGREDIENTS}
        lines["onion"] = "I am the onion. My juice is sharp and brings a little sweetness. Let it run slowly through the tubing into your glass."
        with self.assertRaisesRegex(ValueError, "introduced"):
            self.request(lines, generate_lines, (choose_tactics(),))

    def test_name_uses_strongest_whisper_and_prescribed_brines(self):
        pitch = "A squeeze of my juice makes the glass silky and impossibly bright."
        result, payload = self.request({"name": "A Second Onion Opinion"}, generate_name,
                                       ((8.6, 6.4, 0), pitch, ("The Control Group",)))
        self.assertEqual(result, "A Second Onion Opinion")
        self.assertEqual(json.loads(payload["input"]),
                         {"strongest_voice_pitch": pitch, "recent_titles": ["The Control Group"],
                          "prescribed_brine_ml": {"Pickled Onion": 8.6, "Olive": 6.4}})

    def test_invalid_response_falls_back_without_logging_provider_body(self):
        with patch("dirtyminds.scripts._write", side_effect=ValueError("secret")):
            job = WritingRequest(generate_name, "test-key", DEFAULT_MODEL, (0, 15, 0), "Juice", ())
            value, outcome = job.result.get(timeout=1)
        self.assertIsNone(value)
        self.assertIn("invalid response", outcome)
        self.assertNotIn("secret", outcome)

    def test_http_status_survives_without_response_body(self):
        with patch("dirtyminds.scripts._write", side_effect=HTTPError("", 401, "secret", {}, None)):
            job = WritingRequest(generate_intro, "test-key", DEFAULT_MODEL)
            value, outcome = job.result.get(timeout=1)
        self.assertIsNone(value)
        self.assertIn("HTTP 401", outcome)
        self.assertNotIn("secret", outcome)
