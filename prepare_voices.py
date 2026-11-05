"""Cache the eight fixed voice lines before a live session; does not play audio."""
from dirtyminds.app import ROOT, load_config
from dirtyminds.core import INGREDIENTS, LINES, ROUND_STAGES, SEQUENCE
from dirtyminds.voice import ElevenVoice, VoiceError


def main():
    try:
        config = load_config()
        voice = ElevenVoice(config['api_key'], config['voice_id'], config['model_id'], ROOT / '.cache' / 'voice',
                            whisper=config['whisper'], whisper_model_id=config['whisper_model_id'],
                            whisper_pause_ms=config['whisper_pause_ms'])
        print('Preparing eight lines. Uncached phrases use ElevenLabs credit; cached audio is reused.', flush=True)
        for stage in SEQUENCE:
            if stage not in LINES:
                continue
            voice.voice_id = config['round_voices'][ROUND_STAGES.index(stage)] if stage in ROUND_STAGES else config['voice_id']
            print(f'Preparing: {stage.value}', flush=True)
            voice.synthesize(LINES[stage])
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
