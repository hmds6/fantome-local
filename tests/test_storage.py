from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from storage import cleanup_finished_sessions, session_root

class StorageTests(unittest.TestCase):
    def make_session(self, root, name, state, pid=None):
        folder = root / name
        folder.mkdir()
        (folder / 'status.json').write_text(json.dumps({'state': state}), encoding='utf-8')
        (folder / 'host.log').write_text(f'dll 1 {pid} 1 INFO attached\n' if pid else 'logs\n', encoding='utf-8')
        (folder / 'overlay').mkdir()
        (folder / 'overlay' / 'generated.wad.client').write_bytes(b'generated-data')
        (folder / 'original.fantome').write_bytes(b'keep-user-package')
        return folder

    def test_finished_payload_removed_but_logs_packages_and_active_session_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ended = self.make_session(root, '20261024T100000Z-abcdef', 'stopped')
            active = self.make_session(root, '20261024T110000Z-123456', 'waiting_game')
            report = cleanup_finished_sessions(root)
            self.assertEqual(report['freed_bytes'], len(b'generated-data'))
            self.assertFalse((ended / 'overlay').exists())
            self.assertEqual((ended / 'host.log').read_text(), 'logs\n')
            self.assertTrue((ended / 'original.fantome').exists())
            self.assertTrue((active / 'overlay').exists())
            self.assertEqual(report['errors'], [])

    def test_running_game_pid_protects_even_stopped_host_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = self.make_session(root, '20261024T100000Z-abcdef', 'stopped', 12345)
            report = cleanup_finished_sessions(root, [12345])
            self.assertEqual(report['freed_bytes'], 0)
            self.assertTrue((session / 'overlay').exists())

    def test_configured_cache_used_without_moving_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / 'settings.json'
            settings.write_text(json.dumps({'cache_dir': str(root / 'cache')}))
            with patch.dict('os.environ', {'FANTOME_CACHE_DIR': ''}):
                chosen = session_root(root / 'library', settings)
            self.assertEqual(chosen, root / 'cache' / 'sessions')
            self.assertTrue(chosen.exists())
            self.assertFalse((root / 'library').exists())

if __name__ == '__main__':
    unittest.main()
