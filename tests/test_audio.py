from array import array
import math
import sys
import unittest

from dirtyminds.audio import SAMPLE_RATE, prepare_playback_pcm


def encode(values):
    data = array("h", values)
    if sys.byteorder != "little":
        data.byteswap()
    return data.tobytes()


def decode(pcm):
    data = array("h")
    data.frombytes(pcm)
    if sys.byteorder != "little":
        data.byteswap()
    return data


def tone(frequency, amplitude=8000):
    return encode(round(amplitude * math.sin(2*math.pi*frequency*i/SAMPLE_RATE))
                  for i in range(SAMPLE_RATE))


def middle_rms(pcm):
    samples = decode(pcm)[SAMPLE_RATE//4:SAMPLE_RATE*3//4]
    return math.sqrt(sum(x*x for x in samples)/len(samples))


class AudioTests(unittest.TestCase):
    def test_fades_remove_edge_steps_without_trimming_or_changing_middle(self):
        samples = [8000] * SAMPLE_RATE
        samples[-1] = 30000  # A generated end spike like the reported artifact.
        result = decode(prepare_playback_pcm(encode(samples)))
        self.assertEqual(len(result), len(samples))
        self.assertEqual((result[0], result[-1]), (0, 0))
        self.assertEqual(result[SAMPLE_RATE//2], 8000)
        self.assertLess(max(abs(result[i+1]-result[i]) for i in range(len(result)-1)), 30)

    def test_rumble_filter_reduces_35_50_and_60_hz_but_preserves_voice_band(self):
        for frequency in (35, 50, 60):
            with self.subTest(frequency=frequency):
                pcm = tone(frequency)
                cleaned = prepare_playback_pcm(pcm, reduce_rumble=True)
                self.assertLess(middle_rms(cleaned)/middle_rms(pcm), 0.20)
        for frequency in (200, 1000, 4000):
            with self.subTest(frequency=frequency):
                pcm = tone(frequency, amplitude=50)  # Keep even quiet voice detail.
                cleaned = prepare_playback_pcm(pcm, reduce_rumble=True)
                self.assertAlmostEqual(middle_rms(cleaned)/middle_rms(pcm), 1, delta=0.03)

    def test_silence_stays_silent_and_short_clips_remain_valid(self):
        for count in (1, 2, 3, 10, SAMPLE_RATE):
            for cleanup in (False, True):
                with self.subTest(count=count, cleanup=cleanup):
                    silence = b"\0\0" * count
                    self.assertEqual(prepare_playback_pcm(silence, reduce_rumble=cleanup), silence)
                    result = decode(prepare_playback_pcm(encode([32000]*count), reduce_rumble=cleanup))
                    self.assertEqual(len(result), count)
                    self.assertEqual((result[0], result[-1]), (0, 0))
        for invalid in (b"", b"\x00"):
            with self.assertRaises(ValueError):
                prepare_playback_pcm(invalid)

    def test_filter_does_not_clip_even_when_input_is_full_scale(self):
        source = encode(32767 if (i//240)%2 else -32768 for i in range(SAMPLE_RATE))
        result = decode(prepare_playback_pcm(source, reduce_rumble=True))
        self.assertLessEqual(max(abs(x) for x in result), 32760)
