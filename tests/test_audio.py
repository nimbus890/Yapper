import unittest

import numpy as np

from aura_flow.audio import BoundedAudioBuffer


class AudioBufferTests(unittest.TestCase):
    def test_buffer_is_bounded(self):
        buffer = BoundedAudioBuffer(sample_rate=100, block_size=10, max_seconds=1)
        for value in range(20):
            buffer.append(np.full(10, value, dtype=np.float32))
        snapshot = buffer.snapshot()
        self.assertLessEqual(snapshot.duration_seconds, 1.1)
        self.assertGreater(snapshot.dropped_blocks, 0)
        self.assertEqual(snapshot.samples[-1], 19)

    def test_clear_resets_dropped_count(self):
        buffer = BoundedAudioBuffer(100, 10, 1)
        for _ in range(20):
            buffer.append(np.ones(10, dtype=np.float32))
        buffer.clear()
        self.assertEqual(buffer.snapshot().dropped_blocks, 0)


if __name__ == "__main__":
    unittest.main()

