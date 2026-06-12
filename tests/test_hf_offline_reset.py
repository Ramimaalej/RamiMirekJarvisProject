import importlib
import os
import sys
import unittest


class ResetOfflineFlagsTest(unittest.TestCase):
    def test_reset_hf_offline_flags_clears_cached_state(self):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

        import huggingface_hub.constants as hf_constants

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"

        importlib.reload(hf_constants)

        self.assertTrue(hf_constants.HF_HUB_OFFLINE)

        from core.hf_utils import reset_hf_offline_flags

        reset_hf_offline_flags()

        self.assertIsNone(os.environ.get("HF_HUB_OFFLINE"))
        self.assertIsNone(os.environ.get("TRANSFORMERS_OFFLINE"))
        self.assertIsNone(os.environ.get("HF_DATASETS_OFFLINE"))
        self.assertFalse(hf_constants.HF_HUB_OFFLINE)


if __name__ == "__main__":
    unittest.main()
