"""
Message-related API endpoints
"""

import logging
from typing import Dict
from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import AUTH_DEPENDENCY
from app.services.storage_service import storage_service
from app.services.context_llm_service import context_llm_service
from app.services.rag_service import rag_service
from app.services.memory_service import memory_service
from app.services.external_api_service import ExternalSearchService
from app.utils.helpers import (
    generate_id,
    get_current_timestamp,
    create_success_response,
)
from app.models.schemas import Message

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["messages"])


# External search service instance
external_search_service = ExternalSearchService()


@router.get("/{room_id}/messages")
async def get_messages(room_id: str, user_info: Dict[str, str] = AUTH_DEPENDENCY):
    """Get messages for a room"""
    try:
        # Validate user_info
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")

        messages = await storage_service.get_messages(room_id)
        return create_success_response(data=messages)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages for room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.post("/{room_id}/messages")
async def send_message(
    room_id: str, request: Request, user_info: Dict[str, str] = AUTH_DEPENDENCY
):
    """Send a message to a room"""
    try:
        body = await request.json()
        content = body.get("content", "").strip()

        if not content:
            raise HTTPException(status_code=400, detail="Message content is required")

        # Validate user_info
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")

        # Create message
        message = Message(
            message_id=generate_id(),
            room_id=room_id,
            user_id=user_info["user_id"],
            content=content,
            timestamp=get_current_timestamp(),
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

            intent_result = await intent_service.classify_intent(
                content, message.message_id
            )
            intent = intent_result["intent"]
            entities = intent_result.get("entities", {})

            logger.info(f"Intent: {intent}, Entities: {entities}")

            # Handle different intents with context awareness
            if intent == "time":
                ai_content = external_search_service.now_kst()

            elif intent == "weather":
                location = entities.get("location") or "서울"
                ai_content = external_search_service.weather(location)

            elif intent == "wiki":
                topic = entities.get("topic") or "인공지능"
                ai_content = await external_search_service.wiki(topic)

            elif intent == "search":
                query = entities.get("query") or "AI"
                items = await external_search_service.search(query, 3)
                if items:
                    lines = [f"🔎 '{query}' 검색 결과:"]
                    for i, item in enumerate(items, 1):
                        lines.append(
                            f"{i}. {item['title']}\n{item['link']}\n{item['snippet']}"
                        )
                    ai_content = "\n\n".join(lines)
                else:
                    ai_content = f"'{query}'에 대한 검색 결과를 찾을 수 없습니다."

            elif intent == "name_set":
                name = entities.get("name")
                if name:
                    # Save to memory with context
                    await memory_service.set_memory(
                        room_id, user_info["user_id"], "user_name", name
                    )
                    ai_content = f"알겠어요! 앞으로 {name}님으로 기억할게요. 😊"
                else:
                    ai_content = "이름을 제대로 인식하지 못했어요. 다시 말해주세요."

            elif intent == "name_get":
                name = await memory_service.get_memory(
                    room_id, user_info["user_id"], "user_name"
                )
                if name:
                    ai_content = f"당신의 이름은 {name}로 기억하고 있어요."
                else:
                    ai_content = (
                        "아직 이름을 모르는 걸요. '내 이름은 호건이야'처럼 말해주세요!"
                    )

            else:
                # RAG-based intelligent response
                ai_content = await rag_service.generate_rag_response(
                    room_id,
                    user_info["user_id"],
                    content,
                    intent,
                    entities,
                    message.message_id,
                )

            # Save AI response
            ai_message = Message(
                message_id=generate_id(),
                room_id=room_id,
                user_id="ai",
                content=ai_content,
                timestamp=get_current_timestamp(),
                role="ai",
            )
            await storage_service.save_message(ai_message)

            return create_success_response(
                data={
                    "message": message.model_dump(),
                    "ai_response": ai_message.model_dump(),
                    "intent": intent,
                    "entities": entities,
                },
                message="Message sent successfully",
            )

        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            # Still return the user message even if AI response fails
            return create_success_response(
                data={"message": message.model_dump()},
                message="Message sent, but AI response failed",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")
