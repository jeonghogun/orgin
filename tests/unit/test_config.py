import os
import unittest
from unittest.mock import patch

class TestConfig(unittest.TestCase):

    def test_auth_optional_defaults_to_false(self):
        """
        Tests that settings.AUTH_OPTIONAL is False by default, as a security measure.
        """
        # We need to unload the module to force it to be re-evaluated
        # in a controlled environment.
        with patch.dict(os.environ, {}, clear=True):
            # If we import settings fresh with no env vars, it should use defaults
            from app.config import settings
            self.assertFalse(settings.AUTH_OPTIONAL, "AUTH_OPTIONAL should default to False for security.")

    def test_auth_optional_can_be_overridden(self):
        """
        Tests that settings.AUTH_OPTIONAL can be set to True via an environment variable.
        """
        with patch.dict(os.environ, {"AUTH_OPTIONAL": "True"}, clear=True):
            # Need to reload the settings module to pick up the patched env var
            import importlib
            from app.config import settings
            importlib.reload(settings)
            self.assertTrue(settings.AUTH_OPTIONAL, "AUTH_OPTIONAL should be True when set by env var.")

if __name__ == '__main__':
    unittest.main()
