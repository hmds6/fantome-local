from pathlib import Path
import tempfile
import threading
import struct
import unittest
from wad_builder import Wad, ENTRY, build_one, validate, xxhash

class WadWriterTests(unittest.TestCase):
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
