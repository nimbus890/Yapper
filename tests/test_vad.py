import unittest

import numpy as np

from aura_flow.vad import EnergyVad


class VadTests(unittest.TestCase):
    def setUp(self):
        self.vad = EnergyVad(16_000, 0.006, 0.25)

    def test_silence_is_rejected(self):
        decision = self.vad.analyze(np.zeros(16_000, dtype=np.float32))
        self.assertFalse(decision.accepted)

    def test_speech_like_signal_is_accepted(self):
        time = np.arange(16_000, dtype=np.float32) / 16_000
        audio = 0.05 * np.sin(2 * np.pi * 220 * time)
        decision = self.vad.analyze(audio.astype(np.float32))
        self.assertTrue(decision.accepted)
        self.assertGreater(decision.speech_seconds, 0.9)


if __name__ == "__main__":
    unittest.main()

