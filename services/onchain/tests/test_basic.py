"""Basic tests for onchain module."""

import unittest


class TestOnchain(unittest.TestCase):
    """Test onchain basic functionality."""

    def test_import(self):
        """Test that the package can be imported."""
        import yieldex_onchain
        self.assertIsNotNone(yieldex_onchain.__version__)


if __name__ == "__main__":
    unittest.main()
