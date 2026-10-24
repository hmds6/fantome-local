import unittest
from loader import opted_out_warning, host_failure

class HostStatusTests(unittest.TestCase):
    def test_opted_out_warning_does_not_stop_loader(self):
        line = 'dll 159 27424 5084 WARN ltk_patcher_dll::verify: AH wad scan failed c0000229 for yasuo (opted out):skin0 is another skin'
        self.assertTrue(opted_out_warning(line))
        self.assertFalse(host_failure(line))

    def test_real_refusals_remain_fatal(self):
        self.assertTrue(host_failure('dll 43 1 2 ERROR verify: host verification failed, refusing overlay: [VRF00000008]'))
        self.assertTrue(host_failure('dll 43 1 2 ERROR verify: WAD scan failed status with c0000229 for Yasuo.wad.client'))

if __name__ == '__main__':
    unittest.main()
