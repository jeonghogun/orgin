"""
Main FastAPI Application
"""
# pyright: reportUntypedFunctionDecorator=false
# pyright: reportUnknownMemberType=false
import logging
import time
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, Callable, TypeVar, Awaitable, cast, Optional, List

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, JSONResponse
# slowapi import removed - not directly used
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.config.settings import settings
from app.services.storage_service import storage_service
from app.services.external_api_service import ExternalSearchService
from app.services.memory_service import memory_service
from app.services.context_llm_service import context_llm_service
from app.services.rag_service import rag_service
from app.models.schemas import (
    CreateReviewRequest, ReviewMeta, Message
)
from app.utils.helpers import (
    generate_id, get_current_timestamp, create_success_response
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Type wrapper for slowapi limiter
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])

def limit_typed(
    limit_value: str,
    *,
    key_func: Optional[Callable[[Request], str]] = None,
    per_method: bool = False,
    methods: Optional[List[str]] = None,
    error_message: Optional[str] = None,
) -> Callable[[F], F]:
    """
    A typed wrapper for slowapi's limiter that can be disabled via an environment variable.
    """
    if os.environ.get("RATE_LIMITING_DISABLED", "false").lower() == "true":
        # If rate limiting is disabled, return a decorator that does nothing.
        def no_op_decorator(func: F) -> F:
            return func
        return no_op_decorator

    # Otherwise, return the actual rate-limiting decorator.
    return cast(Callable[[F], F], limiter.limit(
        limit_value,
        key_func=key_func,
        per_method=per_method,
        methods=methods,
        error_message=error_message,
    ))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info("Starting application...")
    yield
    logger.info("Shutting down application...")

# Create FastAPI app
app = FastAPI(
    title="Origin Project API",
    description="AI-powered review and analysis platform",
    version="2.0.0",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.state.limiter = limiter
# Rate limit exception handler
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Mount static files
app.mount("/static", StaticFiles(directory="app/frontend"), name="static")

# Initialize external search service
app.state.search = ExternalSearchService()

# Dependency for authentication
async def require_auth(request: Request) -> Dict[str, str]:
    """Require authentication for protected endpoints"""
    if settings.AUTH_OPTIONAL:
        return {"user_id": "anonymous"}
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # In a real app, validate the token here
    token = auth_header.split(" ")[1]
    return {"user_id": "authenticated_user", "token": token}

# Create dependency instance to avoid function calls in default values
AUTH_DEPENDENCY = Depends(require_auth)

# Health check endpoint
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": get_current_timestamp(),
        "version": "2.0.0"
    }

# Debug endpoint
@app.get("/api/debug/env")
async def debug_env() -> Dict[str, Any]:
    """Debug environment variables"""
    return {
        "openai_api_key_set": bool(settings.OPENAI_API_KEY),
        "openai_api_key_length": len(settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else 0,
        "openai_api_key_start": settings.OPENAI_API_KEY[:10] + "..." if settings.OPENAI_API_KEY else None,
        "env_file_loaded": os.path.exists(".env")
    }

# Room endpoints
@app.post("/api/rooms")
async def create_room(request: Request, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Create a new chat room"""
    try:
        room_id = generate_id()
        room_name = f"Room {room_id[:8]}"
        
        room = await storage_service.create_room(room_id, room_name)
        
        return create_success_response(
            data={"room_id": room_id, "name": room_name},
            message="Room created successfully"
        )
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        raise HTTPException(status_code=500, detail="Failed to create room")

@app.get("/api/rooms/{room_id}")
async def get_room(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get room information"""
    try:
        room = await storage_service.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        return create_success_response(data=room.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get room")

@app.post("/api/rooms/{room_id}/messages")
async def send_message(
    room_id: str, 
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Send a message to a room"""
    try:
        # Check if room exists first
        room = await storage_service.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        body = await request.json()
        content = body.get("content", "").strip()
        
        if not content:
            raise HTTPException(status_code=400, detail="Message content is required")
        
        # Create message
        message = Message(
            message_id=generate_id(),
            room_id=room_id,
            user_id=user_info["user_id"],
            content=content,
            timestamp=get_current_timestamp()
        )
        
        # Save message
        await storage_service.save_message(message)
        
        # Generate AI response
        try:
            # Update user profile from message
            await context_llm_service.update_user_profile_from_message(
                user_info["user_id"], content
            )
            
            # LLM-based intent classification
            from app.services.intent_service import intent_service
            
            intent_result = await intent_service.classify_intent(content, message.message_id)
            intent = intent_result["intent"]
            entities = intent_result.get("entities", {})
            
            logger.info(f"Intent: {intent}, Entities: {entities}")
            
            # Handle different intents with context awareness
            if intent == "time":
                ai_content = app.state.search.now_kst()
                
            elif intent == "weather":
                location = entities.get("location") or "서울"
                ai_content = app.state.search.weather(location)
                
            elif intent == "wiki":
                topic = entities.get("topic") or "인공지능"
                ai_content = await app.state.search.wiki(topic)
                
            elif intent == "search":
                query = entities.get("query") or "AI"
                items = await app.state.search.search(query, 3)
                if items:
                    lines = [f"🔎 '{query}' 검색 결과:"]
                    for i, item in enumerate(items, 1):
                        lines.append(f"{i}. {item['title']}\n{item['link']}\n{item['snippet']}")
                    ai_content = "\n\n".join(lines)
                else:
                    ai_content = f"'{query}'에 대한 검색 결과를 찾을 수 없습니다."
                    
            elif intent == "name_set":
                name = entities.get("name")
                if name:
                    # Save to memory with context
                    await memory_service.set_memory(room_id, user_info["user_id"], "user_name", name)
                    ai_content = f"알겠어요! 앞으로 {name}님으로 기억할게요. 😊"
                else:
                    ai_content = "이름을 제대로 인식하지 못했어요. 다시 말해주세요."
                    
            elif intent == "name_get":
                name = await memory_service.get_memory(room_id, user_info["user_id"], "user_name")
                if name:
                    ai_content = f"당신의 이름은 {name}로 기억하고 있어요."
                else:
                    ai_content = "아직 이름을 모르는 걸요. '내 이름은 호건이야'처럼 말해주세요!"
                    
            else:
                # RAG-based intelligent response
                ai_content = await rag_service.generate_rag_response(
                    room_id, user_info["user_id"], content, intent, entities, message.message_id
                )
            
            # Save AI response
            ai_message = Message(
                message_id=generate_id(),
                room_id=room_id,
                user_id="ai",
                content=ai_content,
                timestamp=get_current_timestamp(),
                role="ai"
            )
            await storage_service.save_message(ai_message)
            
            return create_success_response(
                data={"ai_response": ai_content},
                message="Message sent successfully"
            )
            
        except Exception as ai_error:
            logger.error(f"AI response generation failed: {ai_error}")
            
            # Provide more specific error message based on the error type
            if "API key" in str(ai_error) or "not configured" in str(ai_error):
                error_message = "OpenAI API 키가 설정되지 않았습니다. 환경 변수 OPENAI_API_KEY를 설정해주세요."
            elif "authentication" in str(ai_error).lower():
                error_message = "OpenAI API 인증에 실패했습니다. API 키를 확인해주세요."
            else:
                error_message = f"AI 응답 생성 중 오류가 발생했습니다: {str(ai_error)}"
            
            return create_success_response(
                data={"ai_response": error_message},
                message="Message sent but AI response failed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message")

@app.get("/api/rooms/{room_id}/messages")
async def get_messages(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get all messages for a room"""
    try:
        messages = await storage_service.get_messages(room_id)
        return create_success_response(data=[msg.model_dump() for msg in messages])
    except Exception as e:
        logger.error(f"Error getting messages for room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")

from fastapi import WebSocket, WebSocketDisconnect

# Dummy WebSocket endpoint for testing
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "hello":
                await websocket.send_json({
                    "type": "presence_join",
                    "user_id": "anonymous", # Hardcoded for now
                    "client_id": data.get("client_id")
                })
            elif message_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "ts": data.get("ts")
                })
            elif message_type in ["typing_start", "typing_stop"]:
                # In a real app, this would be broadcast.
                # For this test, we'll just echo it back.
                await websocket.send_json(data)
            else:
                # Echo back any other message types
                await websocket.send_json(data)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from room {room_id}")

# Review endpoints
@app.post("/api/rooms/{room_id}/reviews")
async def create_review(
    request: Request,
    room_id: str,
    review_request: CreateReviewRequest,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Create a new review"""
    try:
        review_id = generate_id()
        
        review_meta = ReviewMeta(
            review_id=review_id,
            room_id=room_id,
            topic=review_request.topic,
            total_rounds=len(review_request.rounds),
            created_at=get_current_timestamp()
        )
        
        await storage_service.create_review(review_meta)
        
        return create_success_response(
            data={"review_id": review_id},
            message="Review created successfully"
        )
    except Exception as e:
        logger.error(f"Error creating review: {e}")
        raise HTTPException(status_code=500, detail="Failed to create review")

@app.post("/api/reviews/{review_id}/generate")
async def generate_review(
    review_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Generate review analysis"""
    try:
        review_meta = await storage_service.get_review(review_id)
        if not review_meta:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # Start review generation (this would be a background task in production)
        await storage_service.update_review(review_id, {
            **review_meta.model_dump(),
            "started_at": get_current_timestamp(),
            "status": "in_progress"
        })
        
        # Log start event
        await storage_service.log_review_event({
            "ts": get_current_timestamp(),
            "type": "review_start",
            "review_id": review_id,
            "round": 0,
            "actor": "system",
            "provider": "system",
            "model": "system",
            "role": "system",
            "content": "Review generation started"
        })
        
        return create_success_response(
            data={"status": "started"},
            message="Review generation started"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating review {review_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate review")

@app.get("/api/reviews/{review_id}")
async def get_review(review_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get review information"""
    try:
        review = await storage_service.get_review(review_id)
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        return create_success_response(data=review.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting review {review_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get review")

@app.get("/api/reviews/{review_id}/events")
async def get_review_events(
    review_id: str,
    since: int = 0,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Get review events"""
    try:
        events = await storage_service.get_review_events(review_id, since)
        
        # Calculate next_since
        next_since = since
        if events:
            next_since = max(event.get("ts", 0) for event in events)
        
        return create_success_response(data={
            "events": events,
            "next_since": next_since
        })
    except Exception as e:
        logger.error(f"Error getting events for review {review_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get events")

@app.get("/api/reviews/{review_id}/report")
async def get_review_report(review_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get final review report"""
    try:
        report = await storage_service.get_final_report(review_id)
        if not report:
            raise HTTPException(status_code=404, detail="Review report not found")
        
        return create_success_response(data=report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report for review {review_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get report")

# Search endpoints
@app.get("/api/search")
async def search(
    request: Request,
    q: str,
    n: int = 5,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Search external sources"""
    try:
        results = await app.state.search.web_search(q, n)
        return create_success_response(data={
            "query": q,
            "results": results
        })
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")

@app.get("/api/search/wiki")
async def wiki_search(
    request: Request,
    topic: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Get Wikipedia summary"""
    try:
        summary = await app.state.search.wiki_summary(topic)
        return create_success_response(data={
            "topic": topic,
            "summary": summary
        })
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}")
        raise HTTPException(status_code=500, detail="Wikipedia search failed")

# Export endpoints
@app.get("/api/rooms/{room_id}/export")
async def export_room_data(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Export room data as markdown"""
    try:
        # Get room and messages
        room = await storage_service.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        messages = await storage_service.get_messages(room_id)
        
        # Generate markdown content
        content = f"# {room.name}\n\n"
        content += f"생성일: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(room.created_at))}\n\n"
        
        for msg in messages:
            role = "사용자" if msg.role == "user" else "AI"
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.timestamp))
            content += f"## {role} ({timestamp})\n\n{msg.content}\n\n"
        
        filename = f"대화기록_{room_id}_{time.strftime('%Y%m%d_%H%M%S')}.md"
        
        return create_success_response(data={
            "content": content,
            "filename": filename
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export error for room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Export failed")

# Memory and Context endpoints
@app.get("/api/context/{room_id}")
async def get_context(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY) -> Dict[str, Any]:
    """Get conversation context"""
    try:
        context = await memory_service.get_context(room_id, user_info["user_id"])
        return create_success_response(data=context.model_dump() if context else None)
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        raise HTTPException(status_code=500, detail="Failed to get context")

@app.get("/api/profile")
async def get_user_profile(user_info: Dict[str, str] = AUTH_DEPENDENCY) -> Dict[str, Any]:
    """Get user profile"""
    try:
        profile = await memory_service.get_user_profile(user_info["user_id"])
        return create_success_response(data=profile.model_dump() if profile else None)
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user profile")

@app.post("/api/memory")
async def set_memory(
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
) -> Dict[str, Any]:
    """Set a memory entry"""
    try:
        body = await request.json()
        room_id = body.get("room_id")
        key = body.get("key")
        value = body.get("value")
        importance = body.get("importance", 1.0)
        ttl = body.get("ttl")
        
        if not all([room_id, key, value]):
            raise HTTPException(status_code=400, detail="room_id, key, and value are required")
        
        success = await memory_service.set_memory(
            room_id, user_info["user_id"], key, value, importance, ttl
        )
        
        if success:
            return create_success_response(data={"success": True}, message="Memory set successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to set memory")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to set memory")

@app.get("/api/memory/{room_id}/{key}")
async def get_memory(
    room_id: str, 
    key: str, 
    user_info: Dict[str, str] = AUTH_DEPENDENCY
) -> Dict[str, Any]:
    """Get a memory entry"""
    try:
        value = await memory_service.get_memory(room_id, user_info["user_id"], key)
        return create_success_response(data={"value": value})
    except Exception as e:
        logger.error(f"Error getting memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to get memory")

# RAG endpoints
@app.post("/api/rag/query")
async def rag_query(
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY
) -> Dict[str, Any]:
    """RAG 기반 질의응답"""
    try:
        body = await request.json()
        room_id = body.get("room_id")
        query = body.get("query")
        
        if not all([room_id, query]):
            raise HTTPException(status_code=400, detail="room_id and query are required")
        
        # 의도 감지
        from app.services.intent_service import intent_service
        intent_result = await intent_service.classify_intent(query, "rag_query")
        intent = intent_result["intent"]
        entities = intent_result.get("entities", {})
        
        # RAG 응답 생성
        response = await rag_service.generate_rag_response(
            room_id, user_info["user_id"], query, intent, entities, "rag_query"
        )
        
        return create_success_response(data={
            "query": query,
            "intent": intent,
            "entities": entities,
            "response": response
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG query error: {e}")
        raise HTTPException(status_code=500, detail="RAG query failed")

# Root endpoint
@app.get("/")
async def root():
    """Serve the main application"""
    from fastapi.responses import FileResponse
    return FileResponse("app/frontend/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
