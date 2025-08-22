import pytest
import asyncio
import sys
import os


from app.services.auth_service import AuthService
from app.config.settings import settings

class TestAuthService:
    def setup_method(self):
        self.auth_service = AuthService()
    
    @pytest.mark.asyncio
    async def test_dummy_token_when_auth_optional_true(self):
        """Test that dummy token is accepted when AUTH_OPTIONAL=True"""
        # Temporarily set AUTH_OPTIONAL to True
        original_value = settings.AUTH_OPTIONAL
        settings.AUTH_OPTIONAL = True
        
        try:
            result = await self.auth_service.verify_token("dummy-id-token")
            assert result is not None
            assert result["uid"] == "dummy_user"
            assert result["email"] == "dummy@example.com"
        finally:
            settings.AUTH_OPTIONAL = original_value
    
    @pytest.mark.asyncio
    async def test_dummy_token_when_auth_optional_false(self):
        """Test that dummy token is rejected when AUTH_OPTIONAL=False"""
        # Temporarily set AUTH_OPTIONAL to False
        original_value = settings.AUTH_OPTIONAL
        settings.AUTH_OPTIONAL = False
        
        try:
            result = await self.auth_service.verify_token("dummy-id-token")
            assert result is None
        finally:
            settings.AUTH_OPTIONAL = original_value
    
    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """Test that invalid tokens are rejected"""
        result = await self.auth_service.verify_token("invalid-token")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_empty_token(self):
        """Test that empty tokens are rejected"""
        result = await self.auth_service.verify_token("")
        assert result is None
        result = await self.auth_service.verify_token(None)
        assert result is None

if __name__ == "__main__":
    pytest.main([__file__])
