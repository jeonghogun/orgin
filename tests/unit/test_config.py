import os
import sys
import unittest
from unittest.mock import patch

class TestConfig(unittest.TestCase):

    def setUp(self):
        """Force a reload of the settings module before each test."""
        # Unload the module if it's already in the cache
        if "app.config.settings" in sys.modules:
            del sys.modules["app.config.settings"]

    def tearDown(self):
        """Ensure the module is unloaded after tests to avoid side effects."""
        if "app.config.settings" in sys.modules:
            del sys.modules["app.config.settings"]

    def test_auth_optional_defaults_to_false(self):
        """
        Tests that settings.AUTH_OPTIONAL is False by default, as a security measure.
        """
        # Provide a dummy key to satisfy Pydantic validation during the test
        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": "test-key-for-config-test"}, clear=True):
            # Import settings fresh, it will be a clean import because of setUp
            from app.config.settings import settings
            self.assertFalse(settings.AUTH_OPTIONAL, "AUTH_OPTIONAL should default to False for security.")

    def test_auth_optional_can_be_overridden(self):
        """
        Tests that settings.AUTH_OPTIONAL can be set to True via an environment variable.
        """
        # Provide a dummy key and the override to satisfy Pydantic validation
        with patch.dict(os.environ, {"AUTH_OPTIONAL": "True", "DB_ENCRYPTION_KEY": "test-key-for-config-test"}, clear=True):
            # Import settings fresh, it will be a clean import because of setUp
            from app.config.settings import settings
            self.assertTrue(settings.AUTH_OPTIONAL, "AUTH_OPTIONAL should be True when set by env var.")

if __name__ == '__main__':
    unittest.main()
