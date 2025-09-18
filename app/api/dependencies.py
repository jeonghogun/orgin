"""
Shared API Dependencies
"""

import logging
from typing import Dict, Optional, Any, Callable, Type
from fastapi import HTTPException, Request, Depends, WebSocket, WebSocketDisconnect, status
from firebase_admin import auth

from app.config.settings import get_effective_redis_url, settings
from app.services.storage_service import StorageService
from app.services.database_service import get_database_service, DatabaseService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.intent_service import IntentService
from app.services.external_api_service import ExternalSearchService
from app.services.context_llm_service import ContextLLMService
from app.services.audit_service import AuditService
from app.services.admin_service import AdminService
from app.services.user_fact_service import UserFactService
from app.services.fact_extractor_service import FactExtractorService
from app.services.cache_service import CacheService
from app.services.intent_classifier_service import IntentClassifierService
from app.services.background_task_service import BackgroundTaskService
from app.core.secrets import SecretProvider, env_secrets_provider
import redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


# --- Service Singletons ---
_admin_service: Optional[AdminService] = None
_audit_service: Optional[AuditService] = None
_cache_service: Optional[CacheService] = None
_redis_client: Optional[redis.Redis] = None
_redis_url_signature: Optional[str] = None
_secret_provider: Optional[SecretProvider] = None
_storage_service: Optional[StorageService] = None
_llm_service: Optional[LLMService] = None
_review_service: Optional["ReviewService"] = None
_memory_service: Optional[MemoryService] = None
_rag_service: Optional[RAGService] = None
_intent_service: Optional[IntentService] = None
_search_service: Optional[ExternalSearchService] = None
_context_llm_service: Optional["ContextLLMService"] = None
_user_fact_service: Optional[UserFactService] = None
_fact_extractor_service: Optional[FactExtractorService] = None
_intent_classifier_service: Optional[IntentClassifierService] = None
_background_task_service: Optional[BackgroundTaskService] = None


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

def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService(secret_provider=get_secret_provider())
    return _llm_service

def get_user_fact_service() -> UserFactService:
    global _user_fact_service
    if _user_fact_service is None:
        _user_fact_service = UserFactService(
            db_service=get_database_service(),
            audit_service=get_audit_service(),
            secret_provider=get_secret_provider()
        )
    return _user_fact_service

def get_fact_extractor_service() -> FactExtractorService:
    global _fact_extractor_service
    if _fact_extractor_service is None:
        _fact_extractor_service = FactExtractorService(
            llm_service=get_llm_service()
        )
    return _fact_extractor_service

def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService(secret_provider=get_secret_provider())
    return _storage_service

def get_review_service() -> "ReviewService":
    """Dependency to get the ReviewService instance, breaking circular import."""
    global _review_service
    if _review_service is None:
        from app.services.review_service import ReviewService
        _review_service = ReviewService(storage_service=get_storage_service())
    return _review_service

def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService(
            db_service=get_database_service(),
            llm_service=get_llm_service(),
            secret_provider=get_secret_provider(),
            user_fact_service=get_user_fact_service()
        )
    return _memory_service

def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
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

def get_admin_service() -> AdminService:
    """Dependency to get the AdminService instance."""
    global _admin_service
    if _admin_service is None:
        from app.services.admin_service import get_admin_service as get_admin_service_from_module
        _admin_service = get_admin_service_from_module()
    return _admin_service

def get_redis_client() -> Optional[redis.Redis]:
    """Dependency to get the Redis client instance."""
    global _redis_client, _redis_url_signature

    redis_url = get_effective_redis_url()
    if not redis_url:
        if _redis_client is not None:
            try:
                _redis_client.close()
            except Exception:
                pass
        _redis_client = None
        _redis_url_signature = None
        logger.warning("REDIS_URL is not configured; cache features are disabled.")
        return None

    if _redis_client is None or _redis_url_signature != redis_url:
        if _redis_client is not None:
            try:
                _redis_client.close()
            except Exception:
                pass
        try:
            _redis_client = redis.from_url(redis_url)
            _redis_url_signature = redis_url
        except RedisError as redis_error:
            logger.warning(
                "Failed to initialize Redis client from %s: %s",
                redis_url,
                redis_error,
                exc_info=True,
            )
            _redis_client = None
            _redis_url_signature = None
    return _redis_client

def get_cache_service() -> CacheService:
    """Dependency to get the CacheService instance."""
    global _cache_service
    if _cache_service is None:
        redis_client = get_redis_client()
        _cache_service = CacheService(redis_client=redis_client)
    return _cache_service


def get_intent_classifier_service() -> IntentClassifierService:
    """Dependency to get the current intent classifier service."""
    global _intent_classifier_service
    if _intent_classifier_service is None:
        _intent_classifier_service = IntentClassifierService(get_llm_service())

    return _intent_classifier_service


def get_background_task_service() -> BackgroundTaskService:
    """Dependency to get the current background task service."""
    global _background_task_service
    if _background_task_service is None:
        _background_task_service = BackgroundTaskService()

    return _background_task_service


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

from app.services.conversation_service import get_conversation_service

AUTH_DEPENDENCY = Depends(require_auth)

def check_budget(user_info: Dict[str, Any] = AUTH_DEPENDENCY):
    """
    A dependency that checks if the user has exceeded their daily token budget.
    """
    if not settings.DAILY_TOKEN_BUDGET:
        return # If no budget is set, do nothing.

    user_id = user_info.get("user_id")
    if not user_id or user_id == "anonymous":
        return # Don't check budget for anonymous users

    convo_service = get_conversation_service()
    current_usage = convo_service.get_today_usage(user_id)

    if current_usage >= settings.DAILY_TOKEN_BUDGET:
        raise HTTPException(
            status_code=429,
            detail=f"Daily token budget of {settings.DAILY_TOKEN_BUDGET} exceeded. Please try again tomorrow."
        )

async def require_auth_ws(websocket: WebSocket) -> str:
    """Authenticate WebSocket requests with support for multiple token sources."""

    if settings.AUTH_OPTIONAL:
        return "anonymous"

    token: Optional[str] = None
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if not token:
        query_token = websocket.query_params.get("token")
        if query_token:
            token = query_token

    if not token and websocket.scope.get("subprotocols"):
        for subprotocol in websocket.scope["subprotocols"]:
            if subprotocol.lower().startswith("bearer "):
                token = subprotocol.split(" ", 1)[1]
                break
            if subprotocol.count(".") == 2:  # looks like a JWT
                token = subprotocol
                break

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect("Missing auth token")

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
