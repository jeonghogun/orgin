"""
Shared API Dependencies
"""

from typing import Dict, Optional, Any, Callable
from fastapi import HTTPException, Request, Depends, WebSocket, WebSocketDisconnect, status
from firebase_admin import auth
import redis

from app.config.settings import settings
from app.core.secrets import SecretProvider, env_secrets_provider
from app.services.storage_service import StorageService
from app.services.database_service import get_database_service
from app.services.llm_service import LLMService
from app.services.review_service import ReviewService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.intent_service import IntentService
from app.services.external_api_service import ExternalSearchService
from app.services.context_llm_service import ContextLLMService
from app.services.audit_service import AuditService
from app.services.admin_service import AdminService
from app.services.cache_service import CacheService, get_cache_service


# --- Service Singletons ---
_admin_service: Optional[AdminService] = None
_audit_service: Optional[AuditService] = None
_redis_client: Optional[redis.Redis] = None
_secret_provider: Optional[SecretProvider] = None
_storage_service: Optional[StorageService] = None
_llm_service: Optional[LLMService] = None
_review_service: Optional[ReviewService] = None
_memory_service: Optional[MemoryService] = None
_rag_service: Optional[RAGService] = None
_intent_service: Optional[IntentService] = None
_search_service: Optional[ExternalSearchService] = None
_context_llm_service: Optional["ContextLLMService"] = None


async def get_storage_service() -> StorageService:
    """Async provider for StorageService, required to inject CacheService."""
    global _storage_service
    if _storage_service is None:
        cache_service = await get_cache_service()
        _storage_service = StorageService(
            db_service=get_database_service(),
            secret_provider=get_secret_provider(),
            cache_service=cache_service
        )
    return _storage_service

def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService(secret_provider=get_secret_provider())
    return _llm_service

async def get_review_service() -> ReviewService:
    """Async provider for ReviewService."""
    global _review_service
    if _review_service is None:
        storage_service = await get_storage_service()
        _review_service = ReviewService(storage_service=storage_service)
    return _review_service

def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService(
            db_service=get_database_service(),
            llm_service=get_llm_service(),
            secret_provider=get_secret_provider()
        )
    return _memory_service

async def get_rag_service() -> RAGService:
    """Async provider for RAGService."""
    global _rag_service
    if _rag_service is None:
        storage_service = await get_storage_service()
        _rag_service = RAGService(
            search_service=get_search_service(),
            llm_service=get_llm_service(),
            memory_service=get_memory_service(),
            storage_service=storage_service,
        )
    return _rag_service

def get_intent_service() -> IntentService:
    global _intent_service
    if _intent_service is None:
        _intent_service = IntentService(llm_service=get_llm_service())
    return _intent_service

def get_search_service() -> ExternalSearchService:
    global _search_service
    if _search_service is None:
        _search_service = ExternalSearchService()
    return _search_service


def get_context_llm_service() -> "ContextLLMService":
    from app.services.context_llm_service import ContextLLMService
    global _context_llm_service
    if _context_llm_service is None:
        _context_llm_service = ContextLLMService(
            llm_service=get_llm_service(), memory_service=get_memory_service()
        )
    return _context_llm_service


def get_secret_provider() -> SecretProvider:
    """Dependency to get the current secrets provider."""
    global _secret_provider
    if _secret_provider is None:
        _secret_provider = env_secrets_provider
    return _secret_provider

def get_audit_service() -> AuditService:
    """Dependency to get the AuditService instance."""
    global _audit_service
    if _audit_service is None:
        from app.services.audit_service import get_audit_service as get_audit_service_from_module
        _audit_service = get_audit_service_from_module()
    return _audit_service

def get_admin_service() -> AdminService:
    """Dependency to get the AdminService instance."""
    global _admin_service
    if _admin_service is None:
        from app.services.admin_service import get_admin_service as get_admin_service_from_module
        _admin_service = get_admin_service_from_module()
    return _admin_service


def get_redis_client() -> redis.Redis:
    """Dependency to get the Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL)
    return _redis_client


# --- Auth Dependency ---
async def require_auth(request: Request) -> Dict[str, str]:
    """Require authentication for protected endpoints"""
    if settings.AUTH_OPTIONAL:
        return {"user_id": "anonymous"}

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = auth_header.split(" ")[1]
    try:
        decoded_token: Dict[str, Any] = auth.verify_id_token(token)
        return {"user_id": decoded_token["uid"]}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


AUTH_DEPENDENCY = Depends(require_auth)

async def require_auth_ws(websocket: WebSocket) -> str:
    """
    Dependency for authenticating WebSockets.
    Reads a JWT from the 'sec-websocket-protocol' header.
    Respects the AUTH_OPTIONAL setting.
    """
    if settings.AUTH_OPTIONAL:
        return "anonymous"

    token = None
    if websocket.scope.get("subprotocols"):
        for subprotocol in websocket.scope["subprotocols"]:
            if "ey" in subprotocol:
                token = subprotocol
                break

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect("Missing auth token in subprotocol")

    try:
        decoded_token: Dict[str, Any] = auth.verify_id_token(token)
        return decoded_token["uid"]
    except Exception as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect(f"Invalid token: {e}")


def require_role(required_role: str) -> Callable:
    """
    Factory for creating a dependency that checks for a specific user role.
    """
    async def role_checker(
        user_info: Dict[str, str] = AUTH_DEPENDENCY,
        memory_service: MemoryService = Depends(get_memory_service),
    ) -> Dict[str, str]:
        """
        Dependency that checks if the authenticated user has the required role.
        """
        user_id = user_info.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        user_profile = await memory_service.get_user_profile(user_id)
        if not user_profile or user_profile.role != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Requires '{required_role}' role.",
            )
        return user_info

    return role_checker
