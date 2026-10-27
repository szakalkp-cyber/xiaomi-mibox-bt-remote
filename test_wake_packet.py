import unittest
from wake_captured import build_payload


class WakePacketTests(unittest.TestCase):
    def test_target_suffix_and_legacy_packet_budget(self):
        packet = build_payload('AA:BB:CC:11:22:33')
        self.assertEqual(len(packet), 31)
        fields = {}
        offset = 0
        while offset < len(packet):
            length = packet[offset]
            self.assertGreater(length, 0)
            self.assertLessEqual(offset + length + 1, len(packet))
            fields[packet[offset + 1]] = packet[offset + 2:offset + length + 1]
            offset += length + 1
        self.assertEqual(offset, len(packet))
        self.assertEqual(fields[0xfe], bytes.fromhex('332211'))
        self.assertEqual(fields[8], b'MI RC')
        self.assertEqual(fields[2], bytes.fromhex('1218'))

    def test_only_suffix_controls_observed_target_field(self):
        self.assertEqual(build_payload('aa:bb:cc:11:22:33'), build_payload('DD:EE:FF:11:22:33'))
        self.assertNotEqual(build_payload('AA:BB:CC:11:22:34'), build_payload('AA:BB:CC:11:22:33'))

    def test_reject_non_bluetooth_addresses(self):
        for target in ('10.0.0.1', '', 'AA:BB:CC:11:22', 'AA:BB:CC:11:22:GG', 'AA:BB:CC:11:22:33\n'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                build_payload(target)


if __name__ == '__main__':
    unittest.main()
