"""
Shared API Dependencies
"""

from typing import Dict, Optional, Any, Callable
from fastapi import HTTPException, Request, Depends, WebSocket, WebSocketDisconnect, status
from firebase_admin import auth

from app.config.settings import settings
from app.services.storage_service import StorageService
from app.services.database_service import get_database_service
from app.services.llm_service import LLMService
from app.services.review_service import ReviewService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.intent_service import IntentService
from app.services.external_api_service import ExternalSearchService
from app.services.firebase_service import FirebaseService
from app.services.context_llm_service import ContextLLMService


# --- Service Singletons ---
_storage_service: Optional[StorageService] = None
_llm_service: Optional[LLMService] = None
_review_service: Optional[ReviewService] = None
_memory_service: Optional[MemoryService] = None
_rag_service: Optional[RAGService] = None
_intent_service: Optional[IntentService] = None
_search_service: Optional[ExternalSearchService] = None
_firebase_service: Optional[FirebaseService] = None
_context_llm_service: Optional["ContextLLMService"] = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service

def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

def get_review_service() -> ReviewService:
    global _review_service
    if _review_service is None:
        _review_service = ReviewService(storage_service=get_storage_service())
    return _review_service

def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService(
            db_service=get_database_service(),
            llm_service=get_llm_service()
        )
    return _memory_service

def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService(
            search_service=get_search_service(),
            llm_service=get_llm_service(),
            memory_service=get_memory_service(),
            storage_service=get_storage_service(),
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

def get_firebase_service() -> FirebaseService:
    global _firebase_service
    if _firebase_service is None:
        _firebase_service = FirebaseService()
    return _firebase_service


def get_context_llm_service() -> "ContextLLMService":
    from app.services.context_llm_service import ContextLLMService
    global _context_llm_service
    if _context_llm_service is None:
        _context_llm_service = ContextLLMService(
            llm_service=get_llm_service(), memory_service=get_memory_service()
        )
    return _context_llm_service


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
    """
    # The token is expected to be the second element in the subprotocols list
    # e.g., ['graphql-ws', 'your_jwt_here']
    token = None
    if websocket.scope.get("subprotocols"):
        for subprotocol in websocket.scope["subprotocols"]:
            # A simple heuristic to find what looks like a JWT
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
            # This should not happen if AUTH_DEPENDENCY is working
            raise HTTPException(status_code=401, detail="Not authenticated")

        user_profile = await memory_service.get_user_profile(user_id)
        if not user_profile or user_profile.role != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Requires '{required_role}' role.",
            )
        return user_info

    return role_checker
