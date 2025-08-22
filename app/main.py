"""
Main FastAPI Application
"""
import logging
import time
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import slowapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.config.settings import settings
from app.services.storage_service import storage_service
from app.services.llm_service import llm_service
from app.services.external_api_service import search_service, ExternalSearchService
from app.models.schemas import (
    CreateReviewRequest, ReviewMeta, PanelReport, 
    ConsolidatedReport, Message, Room
)
from app.utils.helpers import (
    generate_id, get_current_timestamp, safe_json_parse,
    create_error_response, create_success_response
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount static files
app.mount("/static", StaticFiles(directory="app/frontend"), name="static")

# Initialize external search service
app.state.search = ExternalSearchService()

# Dependency for authentication
async def require_auth(request: Request) -> Dict[str, Any]:
    """Require authentication for protected endpoints"""
    if settings.AUTH_OPTIONAL:
        return {"user_id": "anonymous"}
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # In a real app, validate the token here
    token = auth_header.split(" ")[1]
    return {"user_id": "authenticated_user", "token": token}

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": get_current_timestamp(),
        "version": "2.0.0"
    }

# Debug endpoint
@app.get("/api/debug/env")
async def debug_env():
    """Debug environment variables"""
    return {
        "openai_api_key_set": bool(settings.OPENAI_API_KEY),
        "openai_api_key_length": len(settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else 0,
        "openai_api_key_start": settings.OPENAI_API_KEY[:10] + "..." if settings.OPENAI_API_KEY else None,
        "env_file_loaded": os.path.exists(".env")
    }

# Room endpoints
@app.post("/api/rooms")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def create_room(request: Request, user_info: Dict[str, Any] = Depends(require_auth)):
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
async def get_room(room_id: str, user_info: Dict[str, Any] = Depends(require_auth)):
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
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def send_message(
    room_id: str, 
    request: Request,
    user_info: Dict[str, Any] = Depends(require_auth)
):
    """Send a message to a room"""
    try:
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
            # Intent detection: time, weather, search, wiki, name
            import re
            
            TIME_PAT = re.compile(r"(지금 ?몇시|현재 ?시간|time|몇 시|what.*time)", re.I)
            WEATHER_PAT = re.compile(r"(날씨|weather)", re.I)
            WIKI_PAT = re.compile(r"(위키|wikipedia|wiki)", re.I)
            SEARCH_PAT = re.compile(r"(검색|search|구글)", re.I)
            NAME_SET_PAT = re.compile(r"(내 ?이름은\s*([^\s]+)\s*(이야|이야\.|야|입니다)?)", re.I)
            NAME_GET_PAT = re.compile(r"(내 ?이름|내이름)(은|이|가)?\s*\?*$", re.I)

            # 1) 이름 저장
            if "내 이름은" in content:
                # Extract name after "내 이름은"
                name_part = content.split("내 이름은")[1].strip()
                # Remove common endings
                for ending in ["이야", "입니다", "야", "."]:
                    name_part = name_part.replace(ending, "").strip()
                if name_part:
                    await storage_service.memory_set(room_id, "user_name", name_part)
                    ai_content = f"알겠어요! 앞으로 {name_part}님으로 기억할게요. 😊"
            
            # 2) 이름 조회 질의
            elif "내이름" in content or "내 이름" in content:
                name = await storage_service.memory_get(room_id, "user_name")
                ai_content = f"당신의 이름은 {name}로 기억하고 있어요." if name else "아직 이름을 모르는 걸요. '내 이름은 호건이야'처럼 말해줘요!"
            
            # 3) 시간
            elif TIME_PAT.search(content):
                ai_content = app.state.search.now_kst()
            
            # 4) 날씨
            elif WEATHER_PAT.search(content):
                # Extract location from text if possible
                location = "서울"  # Default
                if "해운대" in content:
                    location = "해운대"
                elif "부산" in content:
                    location = "부산"
                ai_content = app.state.search.weather(location)
            
            # 5) 위키
            elif WIKI_PAT.search(content):
                topic = content.replace("위키", "").replace("wikipedia", "").replace("위키피디아", "").replace("wiki", "").strip()
                if not topic:
                    topic = "인공지능"
                ai_content = await app.state.search.wiki(topic)
            
            # 6) 검색
            elif SEARCH_PAT.search(content):
                query = content
                for keyword in ["검색", "search", "구글", "google"]:
                    query = query.replace(keyword, "").strip()
                if not query:
                    query = "AI"
                
                items = await app.state.search.search(query, 3)
                if items:
                    lines = [f"🔎 '{query}' 검색 결과:"]
                    for i, item in enumerate(items, 1):
                        lines.append(f"{i}. {item['title']}\n{item['link']}\n{item['snippet']}")
                    ai_content = "\n\n".join(lines)
                else:
                    ai_content = f"'{query}'에 대한 검색 결과를 찾을 수 없습니다."
            
            # 7) Default: use LLM for general conversation
            else:
                provider = llm_service.get_provider()
                system_prompt = (
                    "당신은 도움이 되는 AI 어시스턴트입니다. 사용자의 질문에 대해 친근하고 유용한 답변을 제공하세요."
                    " 가능한 경우 최신 정보를 제공하고, 불확실하면 명확히 밝혀주세요."
                )

                user_prompt = f"사용자 메시지: {content}"

                ai_response = await provider.invoke(
                    model=settings.LLM_MODEL,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    request_id=message.message_id,
                    response_format="text"
                )

                ai_content = ai_response["content"]
            
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
async def get_messages(room_id: str, user_info: Dict[str, Any] = Depends(require_auth)):
    """Get all messages for a room"""
    try:
        messages = await storage_service.get_messages(room_id)
        return create_success_response(data=[msg.model_dump() for msg in messages])
    except Exception as e:
        logger.error(f"Error getting messages for room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")

# Review endpoints
@app.post("/api/rooms/{room_id}/reviews")
@limiter.limit("10/minute")
async def create_review(
    request: Request,
    room_id: str,
    review_request: CreateReviewRequest,
    user_info: Dict[str, Any] = Depends(require_auth)
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
    user_info: Dict[str, Any] = Depends(require_auth)
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
async def get_review(review_id: str, user_info: Dict[str, Any] = Depends(require_auth)):
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
    user_info: Dict[str, Any] = Depends(require_auth)
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
async def get_review_report(review_id: str, user_info: Dict[str, Any] = Depends(require_auth)):
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
@limiter.limit("30/minute")
async def search(
    request: Request,
    q: str,
    n: int = 5,
    user_info: Dict[str, Any] = Depends(require_auth)
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
@limiter.limit("30/minute")
async def wiki_search(
    request: Request,
    topic: str,
    user_info: Dict[str, Any] = Depends(require_auth)
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
    user_info: Dict[str, Any] = Depends(require_auth)
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

# Root endpoint
@app.get("/")
async def root():
    """Serve the main application"""
    from fastapi.responses import FileResponse
    return FileResponse("app/frontend/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
