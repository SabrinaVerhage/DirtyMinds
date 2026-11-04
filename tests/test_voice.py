import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import wave

from dirtyminds.voice import ElevenVoice, VoiceError, VoiceWorker, NoRedirect


class FakeResponse(io.BytesIO):
    pass


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.voice = ElevenVoice("test-secret-do-not-log", "voice-id", "model-id", self.directory.name)

    def test_request_pcm_conversion_and_cache_without_key(self):
        pcm = b"\x00\x00" * 2400
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = FakeResponse(pcm)
            path = self.voice.synthesize("Hello")
            request = opener.return_value.open.call_args.args[0]
            self.assertTrue(request.full_url.endswith("voice-id?output_format=pcm_24000"))
            self.assertEqual(request.get_header("Xi-api-key"), "test-secret-do-not-log")
            self.assertNotIn(b"test-secret", request.data)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), (24000, 1, 2))
                self.assertEqual(wav.readframes(2400), pcm)
            self.voice.api_key = ""
            self.assertEqual(self.voice.synthesize("Hello"), path)
            self.assertEqual(opener.return_value.open.call_count, 1)
        self.assertNotIn(b"test-secret", path.read_bytes())
        self.assertNotIn("test-secret", path.name)

    def test_cache_changes_when_voice_changes(self):
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = [FakeResponse(b"\0\0" * 100), FakeResponse(b"\0\0" * 100)]
            first = self.voice.synthesize("Hello")
            self.voice.voice_id = "another-voice"
            second = self.voice.synthesize("Hello")
            self.assertNotEqual(first, second)

    def test_http_errors_do_not_expose_key_or_response(self):
        error = urllib.error.HTTPError("https://example.invalid", 401, "test-secret-do-not-log", {}, None)
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(VoiceError) as caught:
                self.voice.synthesize("Hello")
        self.assertNotIn("test-secret", str(caught.exception))
        self.assertIn("rejected the key", str(caught.exception))

    def test_empty_audio_and_missing_key_are_actionable(self):
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = FakeResponse(b"")
            with self.assertRaisesRegex(VoiceError, "invalid"):
                self.voice.synthesize("Hello")
        self.voice.api_key = ""
        with self.assertRaisesRegex(VoiceError, ".env"):
            self.voice.synthesize("Hello")

    def test_redirects_cannot_forward_credentials(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    def test_stop_during_api_request_prevents_late_playback(self):
        entered = threading.Event()
        release = threading.Event()
        played = []

        class Backend:
            def synthesize(self, text):
                entered.set()
                release.wait(2)
                return Path("fake.wav")

        class Player:
            def play(self, path):
                played.append(path)
                return 0

            def stop(self):
                pass

        worker = VoiceWorker(Backend(), Player())
        self.addCleanup(worker.close)
        self.assertTrue(worker.speak("first"))
        self.assertFalse(worker.speak("overlapping"))
        self.assertTrue(entered.wait(1))
        worker.stop()
        release.set()
        worker.speak("second")
        deadline = time.monotonic() + 2
        while worker.busy and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(worker.busy)
        self.assertEqual(len(played), 1)


if __name__ == "__main__":
    unittest.main()

