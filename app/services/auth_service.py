"""
Authentication service for Origin Project
"""
import logging
from typing import Dict, Any, Optional
from app.config.settings import settings

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service for handling user authentication"""
    
    def __init__(self):
        super().__init__()  # Add super call for parent class
    
    async def verify_token(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Verify authentication token"""
        if not token:
            return None
        
        # Check AUTH_OPTIONAL setting dynamically
        if settings.AUTH_OPTIONAL:
            return {"user_id": "anonymous"}
        
        # In a real implementation, verify the token here
        # For now, return a mock user for any non-empty token
        return {"user_id": "authenticated_user", "token": token}
    
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """Get current user from token"""
        return await self.verify_token(token)
    
    def is_authenticated(self, user_info: Optional[Dict[str, Any]]) -> bool:
        """Check if user is authenticated"""
        return user_info is not None and user_info.get("user_id") != "anonymous"




