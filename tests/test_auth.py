import pytest
from typing import Dict, Any, Optional
from app.services.auth_service import AuthService
from app.config.settings import settings

class TestAuthService:
    def setup_method(self):
        self.auth_service: AuthService = AuthService()
    
    @pytest.mark.asyncio
    async def test_dummy_token_when_auth_optional_true(self):
        """Test that dummy token is accepted when AUTH_OPTIONAL=True"""
        # Temporarily set AUTH_OPTIONAL to True
        original_value: bool = settings.AUTH_OPTIONAL
        settings.AUTH_OPTIONAL = True
        
        try:
            result: Optional[Dict[str, Any]] = await self.auth_service.verify_token("dummy-id-token")
            assert result is not None
            assert result["user_id"] == "anonymous"
        finally:
            settings.AUTH_OPTIONAL = original_value
    
    @pytest.mark.asyncio
    async def test_dummy_token_when_auth_optional_false(self):
        """Test that dummy token is accepted when AUTH_OPTIONAL=False"""
        # Temporarily set AUTH_OPTIONAL to False
        original_value: bool = settings.AUTH_OPTIONAL
        settings.AUTH_OPTIONAL = False
        
        try:
            result: Optional[Dict[str, Any]] = await self.auth_service.verify_token("dummy-id-token")
            assert result is not None
            assert result["user_id"] == "authenticated_user"
        finally:
            settings.AUTH_OPTIONAL = original_value
    
    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """Test that invalid tokens are accepted when AUTH_OPTIONAL=False"""
        # Temporarily set AUTH_OPTIONAL to False
        original_value: bool = settings.AUTH_OPTIONAL
        settings.AUTH_OPTIONAL = False
        
        try:
            result: Optional[Dict[str, Any]] = await self.auth_service.verify_token("invalid-token")
            assert result is not None
            assert result["user_id"] == "authenticated_user"
        finally:
            settings.AUTH_OPTIONAL = original_value
    
    @pytest.mark.asyncio
    async def test_empty_token(self):
        """Test that empty tokens are rejected"""
        result: Optional[Dict[str, Any]] = await self.auth_service.verify_token("")
        assert result is None
        result = await self.auth_service.verify_token(None)
        assert result is None

if __name__ == "__main__":
    pytest.main([__file__])
