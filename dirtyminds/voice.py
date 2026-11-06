"""ElevenLabs PCM -> cached WAV -> Windows default audio output.

One worker, bounded requests, and cancellation prevent overlapping/stale speech.
No shell audio player, FFmpeg, API SDK, or key-bearing logs are needed.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import queue
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave

from .audio import PLAYBACK_VERSION, prepare_playback_pcm


class VoiceError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward the API key to an unexpected host.
        return None


def whisper_phrases(text, max_words=10):
    """Keep each whispered request short; preserve all words and punctuation."""
    phrases = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text.strip()):
        words = sentence.split()
        for start in range(0, len(words), max_words):
            phrases.append(" ".join(words[start:start + max_words]))
    return phrases


class ElevenVoice:
    def __init__(self, api_key, voice_id, model_id, cache_dir, *, whisper=False, whisper_model_id="eleven_v3", whisper_pause_ms=900):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.cache_dir = Path(cache_dir)
        self.whisper = whisper
        self.steady = False
        self.whisper_model_id = whisper_model_id
        if not isinstance(whisper_pause_ms, int) or not 0 <= whisper_pause_ms <= 3000:
            raise ValueError("Whisper pause must be between 0 and 3000 milliseconds.")
        self.whisper_pause_ms = whisper_pause_ms

    def synthesize(self, text, *, cancelled=None, cue=None):
        phrases = whisper_phrases(text) if self.whisper else [text]
        if not phrases or not text.strip():
            raise VoiceError("There is no text to speak.")
        model = self.whisper_model_id if self.whisper else self.model_id
        pause_ms = self.whisper_pause_ms if self.whisper else 0
        if cue and model in ("eleven_v3", "eleven_v4"):
            if isinstance(cue, tuple):
                # Reactions share existing phrase requests and stay beside the dialogue.
                for index, reaction in zip((0, len(phrases) // 2), cue):
                    phrases[index] = f"{reaction} {phrases[index]}"
                if self.whisper:
                    phrases[0] = f"[slowly] {phrases[0]}"
                    pause_ms = min(3000, pause_ms + 250)
            else:
                index = min(1, len(phrases) - 1)
                phrases[index] = f"{cue} {phrases[index]}"
        paths = []
        for phrase in phrases:
            if cancelled is not None and cancelled.is_set():
                raise VoiceError("Voice generation cancelled.")
            paths.append(self._synthesize_phrase(phrase))
        if cancelled is not None and cancelled.is_set():
            raise VoiceError("Voice generation cancelled.")
        # Retain the original phrase files. Derive new playback audio locally so
        # an audio fix also repairs existing caches without another paid request.
        digest = hashlib.sha256(json.dumps([
            PLAYBACK_VERSION, [p.name for p in paths], self.whisper,
            pause_ms,
        ]).encode()).hexdigest()
        path = self.cache_dir / "playback" / f"{digest}.wav"
        if self._valid_cached_audio(path):
            return path
        silence = b"\x00\x00" * (24000 * pause_ms // 1000)
        frames = []
        for index, clip in enumerate(paths):
            if cancelled is not None and cancelled.is_set():
                raise VoiceError("Voice generation cancelled.")
            with wave.open(str(clip), "rb") as wav:
                if index:
                    frames.append(silence)
                frames.append(prepare_playback_pcm(
                    wav.readframes(wav.getnframes()), reduce_rumble=self.whisper,
                ))
        if cancelled is not None and cancelled.is_set():
            raise VoiceError("Voice generation cancelled.")
        self._write_wav(path, b"".join(frames))
        return path

    @staticmethod
    def _valid_cached_audio(path):
        try:
            with wave.open(str(path), "rb") as wav:
                return (wav.getnframes() > 0 and wav.getframerate() == 24000
                        and wav.getnchannels() == 1 and wav.getsampwidth() == 2)
        except (wave.Error, EOFError, OSError):
            return False

    @staticmethod
    def _write_wav(path, pcm):
        wav_bytes = io.BytesIO()
        with wave.open(wav_bytes, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(wav_bytes.getvalue())
        temporary.replace(path)

    def _synthesize_phrase(self, text):
        # Whisper uses a tag-capable model, even when the ordinary voice is v2.
        voice_id, whisper = self.voice_id, self.whisper
        model = self.whisper_model_id if whisper else self.model_id
        settings = {"stability": 0.5 if model in ("eleven_v3", "eleven_v4") else 0.45, "similarity_boost": 0.75}
        if self.steady:
            settings["stability"] = 1.0 if model in ("eleven_v3", "eleven_v4") else 0.85
            settings["speed"] = 0.95
        if whisper and model == "eleven_v3":
            settings["speed"] = 0.85
        payload = {
            "text": "[whispering] " + text if whisper else text,
            "model_id": model,
            "voice_settings": settings,
        }
        digest = hashlib.sha256(json.dumps(
            [voice_id, payload, "pcm_24000"], sort_keys=True
        ).encode()).hexdigest()
        path = self.cache_dir / f"{digest}.wav"
        if self._valid_cached_audio(path):
            return path
        if not self.api_key or self.api_key == "your_api_key_here":
            raise VoiceError("Add your ElevenLabs key to .env, restart, or select Silent rehearsal.")
        voice = urllib.parse.quote(voice_id, safe="")
        request = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_24000",
            data=json.dumps(payload).encode(),
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=25) as response:
                pcm = response.read(12_000_001)
        except urllib.error.HTTPError as exc:
            messages = {
                401: "ElevenLabs rejected the key. Check .env and restart.",
                403: "ElevenLabs denied access. Check key permissions and voice access.",
                404: "Voice or model not found. Check the IDs in .env.",
                422: "ElevenLabs rejected the settings. Check voice and model IDs.",
                429: "ElevenLabs rate or credit limit reached. Try later or rehearse silently.",
            }
            raise VoiceError(messages.get(exc.code, f"ElevenLabs request failed (HTTP {exc.code}).")) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise VoiceError("Could not reach ElevenLabs. Check the internet or use Silent rehearsal.") from None
        if not pcm or len(pcm) % 2 or len(pcm) > 12_000_000:
            raise VoiceError("ElevenLabs returned invalid or oversized audio.")
        self._write_wav(path, pcm)
        return path


class WindowsPlayer:
    def play(self, path, *, loop=False):
        import winsound
        with wave.open(str(path), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        if loop:
            flags |= winsound.SND_LOOP
        winsound.PlaySound(str(path), flags)
        return duration

    def stop(self):
        import winsound
        winsound.PlaySound(None, 0)


class VoiceWorker:
    def __init__(self, backend, player=None):
        self.backend = backend
        self.player = player or WindowsPlayer()
        self.events = queue.Queue()
        self.jobs = queue.Queue()
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.generation = 0
        self.busy = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def speak(self, text, *, voice_id=None, cue=None, steady=False, lead_in=None):
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            backend = copy.copy(self.backend)
            if voice_id is not None:
                backend.voice_id = voice_id
            if steady:
                backend.whisper = False
                backend.steady = True
            self.jobs.put((self.generation, self.cancelled, text, backend, cue, lead_in))
            return True

    def play_loop(self, path):
        with self.lock:
            if self.busy:
                return False
            try:
                self.player.play(path, loop=True)
            except (OSError, wave.Error, RuntimeError):
                return False
            return True

    def stop(self):
        with self.lock:
            self.cancelled.set()
            self.generation += 1
            self.cancelled = threading.Event()
            self.busy = False
            self.player.stop()

    def close(self):
        self.stop()
        self.jobs.put(None)

    def _run(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            generation, cancelled, text, backend, cue, lead_in = job
            if cancelled.is_set():
                continue
            error = None
            try:
                self.events.put((generation, "status", "Preparing voice…"))
                options = {"cue": cue} if cue else {}
                path = backend.synthesize(text, cancelled=cancelled, **options)
                if lead_in:
                    try:
                        with self.lock:
                            if cancelled.is_set():
                                continue
                            lead_duration = self.player.play(lead_in)
                        if cancelled.wait(lead_duration + 0.08):
                            continue
                    except (OSError, wave.Error, RuntimeError):
                        self.events.put((generation, "status", "Sound cue unavailable. Continuing with speech."))
                with self.lock:
                    if cancelled.is_set():
                        continue
                    duration = self.player.play(path)
                    self.events.put((generation, "playing", "Voice playing · measuring this round"))
                    self.events.put((generation, "status", "Speaking through Windows audio output…"))
                cancelled.wait(duration + 0.1)
            except VoiceError as exc:
                error = str(exc)
            except Exception:
                # Never log raw exceptions: they may contain request/config details.
                error = "Voice playback failed. Check Windows audio output and the local cache folder."
            finally:
                with self.lock:
                    if generation == self.generation:
                        self.busy = False
                        self.events.put((generation, "error" if error else "done", error or "Voice ready"))

