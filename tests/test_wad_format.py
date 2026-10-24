from pathlib import Path
import tempfile
import threading
import struct
import unittest
from wad_builder import Wad, ENTRY, LEGACY_ENTRY, build_one, validate, xxhash

class WadWriterTests(unittest.TestCase):
    def test_legacy_v33_unordered_table_and_duplicate_layout_are_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b'legacy-payload'
            checksum = xxhash.xxh3_64_intdigest(payload)
            source = root / 'legacy.wad.client'
            source.write_bytes(b'RW\x03\x03' + bytes(264) + struct.pack('<I', 2)
                               + LEGACY_ENTRY.pack(20, 336, len(payload), len(payload), 0, 0, 0, checksum)
                               + LEGACY_ENTRY.pack(10, 336, len(payload), len(payload), 0, 1, 257, checksum)
                               + payload)
            legacy = Wad(source)
            self.assertEqual(list(legacy.entries), [10, 20])
            self.assertEqual(legacy.entries[10][5], bytes((0, 1, 1)))
            self.assertEqual(legacy.decode(legacy.entries[10]), payload)
            self.assertEqual(legacy.decode(legacy.entries[20]), payload)
            bad = bytearray(source.read_bytes())
            bad[-1] ^= 1
            source.write_bytes(bad)
            with self.assertRaises(ValueError):
                legacy.decode(legacy.entries[10])

    def test_new_entry_preservation_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = b'original'
            source = root / 'source.wad.client'
            header = b'RW\x03\x04' + bytes(264)
            source.write_bytes(header + struct.pack('<I', 1) + ENTRY.pack(10, 304, 8, 8, 0, bytes(3), xxhash.xxh3_64_intdigest(data)) + data)
            clone = root / 'clone.wad.client'
            build_one(Wad(source), clone, {}, threading.Event())
            self.assertEqual(source.read_bytes(), clone.read_bytes())
            target = root / 'target.wad.client'
            build_one(Wad(source), target, {5: (b'inserted', 8, 0), 10: (b'replaced', 8, 0)}, threading.Event())
            result = Wad(target)
            self.assertEqual(list(result.entries), [5, 10])
            self.assertEqual(result.header, header)
            self.assertEqual(result.decode(result.entries[5]), b'inserted')
            self.assertEqual(result.decode(result.entries[10]), b'replaced')
            corrupt = bytearray(target.read_bytes())
            corrupt[-1] ^= 1
            target.write_bytes(corrupt)
            with self.assertRaises(ValueError):
                validate(target)

if __name__ == '__main__':
    unittest.main()
