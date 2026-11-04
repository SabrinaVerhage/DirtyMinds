"""ElevenLabs PCM -> cached WAV -> Windows default audio output.

One worker, bounded requests, and cancellation prevent overlapping/stale speech.
No shell audio player, FFmpeg, API SDK, or key-bearing logs are needed.
"""
import hashlib
import io
import json
from pathlib import Path
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave


class VoiceError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward the API key to an unexpected host.
        return None


class ElevenVoice:
    def __init__(self, api_key, voice_id, model_id, cache_dir):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.cache_dir = Path(cache_dir)

    def synthesize(self, text):
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
        }
        digest = hashlib.sha256(json.dumps(
            [self.voice_id, payload, "pcm_24000"], sort_keys=True
        ).encode()).hexdigest()
        path = self.cache_dir / f"{digest}.wav"
        if path.exists():
            try:
                with wave.open(str(path), "rb") as wav:
                    if wav.getnframes() > 0 and wav.getframerate() == 24000:
                        return path
            except (wave.Error, EOFError, OSError):
                pass
        if not self.api_key or self.api_key == "your_api_key_here":
            raise VoiceError("Add your ElevenLabs key to .env, restart, or select Silent rehearsal.")
        voice = urllib.parse.quote(self.voice_id, safe="")
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
        wav_bytes = io.BytesIO()
        with wave.open(wav_bytes, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(wav_bytes.getvalue())
        temporary.replace(path)
        return path


class WindowsPlayer:
    def play(self, path):
        import winsound
        with wave.open(str(path), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
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

    def speak(self, text):
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            self.jobs.put((self.generation, self.cancelled, text))
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
            generation, cancelled, text = job
            if cancelled.is_set():
                continue
            error = None
            try:
                self.events.put((generation, "status", "Preparing voice…"))
                path = self.backend.synthesize(text)
                with self.lock:
                    if cancelled.is_set():
                        continue
                    duration = self.player.play(path)
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

