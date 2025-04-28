import unittest
from unittest.mock import patch
import os
import logging
from oc_logging.Logging import setup_logging


class TestLoggingSetup(unittest.TestCase):
    @patch("logging.StreamHandler.emit")
    def test_logging_configuration(self, mock_emit):
        os.environ["LOG_LEVEL"] = "INFO"
        setup_logging()

        logger = logging.getLogger("werkzeug")
        logger.propagate = True
        logger.info("Test info message")

        self.assertTrue(mock_emit.called, "Expected 'emit' to be called but it wasn't.")
        emitted_record = mock_emit.call_args[0][0]
        self.assertEqual(emitted_record.getMessage(), "Test info message")
        self.assertEqual(emitted_record.levelname, "INFO")

    @patch("logging.StreamHandler.emit")
    def test_invalid_log_level(self, mock_emit):
        os.environ["LOG_LEVEL"] = "INVALID"

        with self.assertRaises(EnvironmentError):
            setup_logging()


if __name__ == "__main__":
    unittest.main()
