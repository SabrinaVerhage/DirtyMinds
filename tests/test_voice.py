import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import wave

from dirtyminds.voice import ElevenVoice, VoiceError, VoiceWorker, NoRedirect, whisper_phrases
from dirtyminds.audio import prepare_playback_pcm


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

    def test_whisper_uses_v3_direction_and_separate_cached_audio(self):
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = [FakeResponse(b"\0\0" * 100), FakeResponse(b"\0\0" * 100)]
            spoken_path = self.voice.synthesize("Hello")
            spoken = json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(spoken["text"], "Hello")
            self.voice.whisper = True
            whispered_path = self.voice.synthesize("Hello")
            whispered = json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(whispered["text"], "[whispering] Hello")
            self.assertEqual(whispered["model_id"], "eleven_v3")
            self.assertEqual(whispered["voice_settings"]["stability"], 0.5)
            self.assertNotEqual(spoken_path, whispered_path)
            self.voice.whisper = False
            self.assertEqual(self.voice.synthesize("Hello"), spoken_path)
            self.assertEqual(opener.return_value.open.call_count, 2)

    def test_http_errors_do_not_expose_key_or_response(self):
        error = urllib.error.HTTPError("https://example.invalid", 401, "test-secret-do-not-log", {}, None)
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(VoiceError) as caught:
                self.voice.synthesize("Hello")
        self.assertNotIn("test-secret", str(caught.exception))
        self.assertIn("rejected the key", str(caught.exception))

    def test_v4_places_one_reaction_beside_whispered_dialogue(self):
        self.voice.whisper = True
        self.voice.whisper_model_id = "eleven_v4"
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            send = opener.return_value.open
            send.side_effect = [FakeResponse(b"\0\0" * 100) for _ in range(2)]
            self.voice.synthesize("My name is Pearl. I have a secret.", cue="[sighs]")
        requests = [json.loads(call.args[0].data) for call in send.call_args_list]
        self.assertEqual([item["text"] for item in requests],
                         ["[whispering] My name is Pearl.", "[whispering] [sighs] I have a secret."])

    def test_whisper_restarts_per_phrase_and_adds_exact_silence(self):
        self.voice.whisper = True
        first = b"\x01\x00" * 2400
        second = b"\x02\x00" * 4800
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = [FakeResponse(first), FakeResponse(second)]
            path = self.voice.synthesize("Welcome. Take your time.")
            requests = [json.loads(c.args[0].data) for c in opener.return_value.open.call_args_list]
            self.assertEqual([p["text"] for p in requests], ["[whispering] Welcome.", "[whispering] Take your time."])
            self.assertTrue(all(p["voice_settings"]["speed"] == 0.85 for p in requests))
            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getnframes(), 2400 + 21600 + 4800)
                self.assertEqual(wav.readframes(wav.getnframes()),
                                 prepare_playback_pcm(first, reduce_rumble=True)
                                 + b"\0\0" * 21600
                                 + prepare_playback_pcm(second, reduce_rumble=True))
            self.assertEqual(self.voice.synthesize("Welcome. Take your time."), path)
            self.voice.whisper_pause_ms = 1500
            longer = self.voice.synthesize("Welcome. Take your time.")
            self.assertNotEqual(longer, path)
            self.assertEqual(opener.return_value.open.call_count, 2)

    def test_existing_raw_cache_is_smoothed_without_network_or_overwrite(self):
        pcm = b"\x00\x20" * 24000
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = FakeResponse(pcm)
            raw = self.voice._synthesize_phrase("A cached phrase.")
        original = raw.read_bytes()
        self.voice.api_key = ""
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            playback = self.voice.synthesize("A cached phrase.")
            opener.assert_not_called()
        self.assertNotEqual(raw, playback)
        self.assertEqual(raw.read_bytes(), original)
        with wave.open(str(playback), "rb") as wav:
            processed = wav.readframes(wav.getnframes())
        self.assertEqual(len(processed), len(pcm))
        self.assertEqual(processed[:2], b"\0\0")
        self.assertEqual(processed[-2:], b"\0\0")
        self.assertEqual(processed[12000:12002], pcm[12000:12002])

    def test_character_reactions_are_spaced_across_the_whisper(self):
        self.voice.whisper = True
        self.voice.whisper_model_id = "eleven_v4"
        self.voice.whisper_pause_ms = 900
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            send = opener.return_value.open
            send.side_effect = [FakeResponse(b"\0\0" * 100) for _ in range(3)]
            path = self.voice.synthesize("Come closer. Follow the tubing. Taste the finish.",
                                         cue=("[inhales softly]", "[sighs]"))
        texts = [json.loads(call.args[0].data)["text"] for call in send.call_args_list]
        self.assertEqual(texts, ["[whispering] [slowly] [inhales softly] Come closer.",
                                 "[whispering] [sighs] Follow the tubing.",
                                 "[whispering] Taste the finish."])
        with wave.open(str(path), "rb") as wav:
            self.assertEqual(wav.getnframes(), 300 + 2 * 27_600)

    def test_every_phrase_boundary_is_zero_even_without_a_pause(self):
        self.voice.whisper = True
        self.voice.whisper_pause_ms = 0
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = [
                FakeResponse(b"\x00\x20" * 24000),
                FakeResponse(b"\x00\xe0" * 24000),
            ]
            path = self.voice.synthesize("First phrase. Second phrase.")
        with wave.open(str(path), "rb") as wav:
            self.assertEqual(wav.getnframes(), 48000)
            pcm = wav.readframes(wav.getnframes())
        self.assertEqual(pcm[47998:48002], b"\0\0\0\0")

    def test_whisper_phrase_split_preserves_words_and_limits_length(self):
        text = "Close your eyes, if you like. Imagine a secret you would only tell over a very good martini. Take your time."
        parts = whisper_phrases(text)
        self.assertEqual(" ".join(parts), text)
        self.assertTrue(all(len(p.split()) <= 10 for p in parts))

    def test_stop_prevents_later_phrase_requests(self):
        self.voice.whisper = True
        cancelled = threading.Event()
        def first_response(*args, **kwargs):
            cancelled.set()
            return FakeResponse(b"\0\0" * 100)
        with patch("dirtyminds.voice.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = first_response
            with self.assertRaisesRegex(VoiceError, "cancelled"):
                self.voice.synthesize("First. Second.", cancelled=cancelled)
            self.assertEqual(opener.return_value.open.call_count, 1)

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

    def test_each_job_snapshots_voice_and_reports_actual_playback(self):
        entered, release = threading.Event(), threading.Event()
        observed = []

        class Backend:
            voice_id = 'host'
            def synthesize(self, text, *, cancelled=None):
                entered.set()
                release.wait(2)
                observed.append(self.voice_id)
                return Path('fake.wav')

        class Player:
            def play(self, path):
                return 0
            def stop(self):
                pass

        worker = VoiceWorker(Backend(), Player())
        self.addCleanup(worker.close)
        worker.speak('round one', voice_id='nora')
        self.assertTrue(entered.wait(1))
        self.assertNotIn('playing', [event[1] for event in list(worker.events.queue)])
        worker.backend.voice_id = 'changed'
        release.set()
        deadline = time.monotonic() + 2
        while worker.busy and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(observed, ['nora'])
        kinds = [event[1] for event in list(worker.events.queue)]
        self.assertLess(kinds.index('playing'), kinds.index('done'))

    def test_cue_finishes_before_speech_starts(self):
        played = []
        options = []

        class Backend:
            whisper = True
            def synthesize(self, text, *, cancelled=None):
                options.append((self.whisper, self.steady))
                return Path("speech.wav")

        class Player:
            def play(self, path):
                played.append(path.name)
                return 0
            def stop(self):
                pass

        worker = VoiceWorker(Backend(), Player())
        self.addCleanup(worker.close)
        worker.speak("Welcome", steady=True, lead_in=Path("jingle.wav"))
        deadline = time.monotonic() + 2
        while worker.busy and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(played, ["jingle.wav", "speech.wav"])
        self.assertEqual(options, [(False, True)])
        self.assertEqual([event[1] for event in list(worker.events.queue)].count("playing"), 1)
        self.assertTrue(worker.backend.whisper)

    def test_stop_during_api_request_prevents_late_playback(self):
        entered = threading.Event()
        release = threading.Event()
        played = []

        class Backend:
            def synthesize(self, text, *, cancelled=None):
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

