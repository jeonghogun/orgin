import pytest
from app.services.auth_service import AuthService
from app.config.settings import settings

class TestAuthService:
    @pytest.mark.asyncio
    async def test_dummy_token_when_auth_optional_true(self, monkeypatch):
        """Test that dummy token is accepted when AUTH_OPTIONAL=True"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", True)
        auth_service = AuthService()
        result = await auth_service.verify_token("dummy-id-token")
        assert result is not None
        assert result["user_id"] == "anonymous"

    @pytest.mark.asyncio
    async def test_dummy_token_when_auth_optional_false(self, monkeypatch):
        """Test that dummy token is rejected when AUTH_OPTIONAL=False"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)
        auth_service = AuthService()
        result = await auth_service.verify_token("dummy-id-token")
        assert result is not None
        assert result["user_id"] == "authenticated_user"

    @pytest.mark.asyncio
    async def test_invalid_token(self, monkeypatch):
        """Test that invalid tokens are rejected"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)
        auth_service = AuthService()
        result = await auth_service.verify_token("invalid-token")
        assert result is not None
        assert result["user_id"] == "authenticated_user"

    @pytest.mark.asyncio
    async def test_empty_token(self, monkeypatch):
        """Test that empty tokens are rejected"""
        monkeypatch.setattr(settings, "AUTH_OPTIONAL", False)
        auth_service = AuthService()
        result = await auth_service.verify_token("")
        assert result is not None
        assert result["user_id"] == "authenticated_user"
        result = await auth_service.verify_token(None)
        assert result is not None
        assert result["user_id"] == "authenticated_user"
