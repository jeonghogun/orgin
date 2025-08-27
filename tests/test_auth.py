from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from typing import Dict, Any
from unittest.mock import patch
import firebase_admin

from app.api.dependencies import require_auth
from app.config.settings import settings

from firebase_admin import credentials

# Initialize a dummy Firebase app for testing if not already initialized
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        'projectId': 'test-project-id',
    })

# Create a dummy app to test the dependency
test_app = FastAPI()

@test_app.get("/test-auth")
async def get_test_auth(user_info: Dict[str, Any] = Depends(require_auth)):
    return user_info

client = TestClient(test_app)


class TestAuthDependency:

    def test_auth_optional_true(self, monkeypatch):
        """Test that any token works when AUTH_OPTIONAL=True"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", True)
        response = client.get("/test-auth", headers={"Authorization": "Bearer dummy-token"})
        assert response.status_code == 200
        assert response.json() == {"user_id": "anonymous"}

    def test_auth_optional_false_no_token(self, monkeypatch):
        """Test that no token fails when AUTH_OPTIONAL=False"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)
        response = client.get("/test-auth")
        assert response.status_code == 401

    @patch("firebase_admin.auth.verify_id_token")
    def test_auth_optional_false_valid_token(self, mock_verify, monkeypatch):
        """Test that a valid token succeeds when AUTH_OPTIONAL=False"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)
        mock_verify.return_value = {"uid": "real-user"}

        # Re-inject the dependency with the mocked auth
        test_app.dependency_overrides[require_auth] = require_auth
        
        response = client.get("/test-auth", headers={"Authorization": "Bearer real-token"})
        
        assert response.status_code == 200
        # The dependency now returns the validated user ID
        assert response.json()["user_id"] == "real-user"
        mock_verify.assert_called_once_with("real-token")
        
        # Clean up dependency overrides
        test_app.dependency_overrides = {}

    @patch("firebase_admin.auth.verify_id_token")
    def test_auth_optional_false_invalid_token(self, mock_verify, monkeypatch):
        """Test that an invalid token fails when AUTH_OPTIONAL=False"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)
        mock_verify.side_effect = Exception("Invalid token")

        # Re-inject the dependency with the mocked auth
        test_app.dependency_overrides[require_auth] = require_auth

        response = client.get("/test-auth", headers={"Authorization": "Bearer invalid-token"})

        assert response.status_code == 401
        assert "Invalid token" in response.json()["detail"]

        # Clean up dependency overrides
        test_app.dependency_overrides = {}
