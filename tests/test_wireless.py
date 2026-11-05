import socket
import time
import unittest
from unittest.mock import patch
from dirtyminds.sensors import WirelessInput

class FakeSocket:
    def __init__(self):
        self.parts = iter([b'GSR:4', b'2\nnoise\n9999\nGSR:123\n', b''])
    def settimeout(self, timeout): pass
    def recv(self, size): return next(self.parts)
    def close(self): pass

class WirelessInputTests(unittest.TestCase):
    def test_fragmented_invalid_and_disconnect(self):
        with patch.object(socket, 'create_connection', return_value=FakeSocket()):
            reader = WirelessInput('192.168.1.10')
            reader.thread.join(timeout=1)
            samples = [v for _, v in reader.poll()]
            reader.close()
        self.assertEqual(samples, [42, 123])
        self.assertIn('connection lost', reader.error)

if __name__ == '__main__': unittest.main()
