"""Basic tests for data collector."""

import unittest


class TestDataCollector(unittest.TestCase):
    """Test data collector basic functionality."""

    def test_import(self):
        """Test that the package can be imported."""
        import yieldex_data_collector

        self.assertIsNotNone(yieldex_data_collector.__version__)


if __name__ == "__main__":
    unittest.main()
