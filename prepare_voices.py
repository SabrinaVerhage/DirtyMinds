"""Cache the fixed appointment script before a live session; does not play audio."""
from dirtyminds.app import ROOT, load_config
from dirtyminds.core import LINES, ROUND_STAGES, SEQUENCE, VOICE_CUES
from dirtyminds.voice import ElevenVoice, VoiceError


def main():
    try:
        config = load_config()
        voice = ElevenVoice(config['api_key'], config['professor_voice'], config['model_id'], ROOT / '.cache' / 'voice',
                            whisper=config['whisper'], whisper_model_id=config['whisper_model_id'],
                            whisper_pause_ms=config['whisper_pause_ms'])
        print(f'Preparing {len(LINES)} lines. Uncached phrases use ElevenLabs credit; cached audio is reused.', flush=True)
        for stage in SEQUENCE:
            if stage not in LINES:
                continue
            voice.steady = stage not in ROUND_STAGES
            voice.whisper = config['whisper'] and not voice.steady
            voice.voice_id = (config['professor_voice'] if voice.steady
                              else config['round_voices'][ROUND_STAGES.index(stage)])
            print(f'Preparing: {stage.value}', flush=True)
            voice.synthesize(LINES[stage], cue=VOICE_CUES.get(stage) if config['voice_effects'] else None)
            print('  Cached.', flush=True)
        print('Ready. This cast and script can now play from the local cache.')
    except (ValueError, VoiceError) as exc:
        print(str(exc))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print('Stopped. Completed phrases remain cached.')
        raise SystemExit(130) from None
    except Exception:
        print('Preparation failed. Check the local cache folder and connection. No automatic retry.')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
