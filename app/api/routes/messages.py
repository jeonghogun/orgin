"""
Message-related API endpoints
"""

import logging
import time
import uuid
import shutil
import json
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile

from app.api.dependencies import (
    AUTH_DEPENDENCY,
    get_storage_service,
    get_rag_service,
    get_memory_service,
    get_search_service,
    get_intent_service,
    get_review_service,
    get_llm_service,
)
from app.services.storage_service import StorageService
from app.services.rag_service import RAGService
from app.services.memory_service import MemoryService
from app.services.external_api_service import ExternalSearchService
from app.services.intent_service import IntentService
from app.services.review_service import ReviewService
from app.services.llm_service import LLMService
from app.utils.helpers import (
    generate_id,
    get_current_timestamp,
    create_success_response,
)
from typing import List
from app.models.enums import RoomType
from app.models.schemas import Message, ReviewMeta
from app.api.routes.websockets import manager

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="", tags=["messages"])


from app.models.schemas import Message

@router.get("/{room_id}/messages", response_model=List[Message])
async def get_messages(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),  # pyright: ignore[reportCallInDefaultInitializer]
):
    """Get messages for a room"""
    try:
        # Validate user_info
        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")

        messages = storage_service.get_messages(room_id)
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages for room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")


async def _check_and_suggest_review(
    room_id: str,
    user_id: str,
    storage_service: StorageService,
    memory_service: MemoryService,
    llm_service: LLMService,
) -> Optional[str]:
    """Checks if conditions are met to suggest a review and returns a suggestion message if so."""
    try:
        room = storage_service.get_room(room_id)
        if not room or room.type != RoomType.SUB or room.message_count < 10:
            return None

        # Check if a suggestion was made recently
        suggestion_key = f'review_suggested_at:{room_id}'
        recent_suggestions = await memory_service.get_user_facts(user_id, kind='suggestion_state', key=suggestion_key)
        if recent_suggestions:
            last_suggestion_time = recent_suggestions[0]['value_json'].get('timestamp', 0)
            if time.time() - last_suggestion_time < 3600:  # 1 hour cooldown
                return None

        # Use LLM to check for conversation coherency
        messages = storage_service.get_messages(room_id)
        last_10_messages = "\n".join([f"{m.role}: {m.content}" for m in messages[-10:]])
        
        prompt = f"""
        다음 대화는 하나의 주제에 대해 집중적이고 깊이 있게 진행되고 있습니까?
        새로운 '검토룸'을 생성하여 이 주제에 대해 AI 패널 토론을 시작할 만큼 가치가 있습니까?
        'yes' 또는 'no'로만 대답하세요.
        
        대화 내용:
        {last_10_messages}
        """
        
        coherency_response, _ = await llm_service.get_provider().invoke(
            user_prompt=prompt,
            system_prompt="You are a helpful assistant that analyzes conversations.",
            model="gpt-3.5-turbo", # Use a fast model for this check
        )

        if "yes" in coherency_response.lower():
            # Mark that a suggestion has been made
            await memory_service.upsert_user_fact(
                user_id,
                kind='suggestion_state',
                key=suggestion_key,
                value={'timestamp': time.time()},
                confidence=1.0
            )
            return "이 주제에 대해 깊이 있는 논의가 진행된 것 같네요. 검토룸을 만들어 AI 토론을 시작해볼까요?"

    except Exception as e:
        logger.error(f"Error checking for review suggestion: {e}")
    
    return None


@router.post("/{room_id}/messages")
async def send_message(
    room_id: str,
    request: Request,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    storage_service: StorageService = Depends(get_storage_service),  # pyright: ignore[reportCallInDefaultInitializer]
    rag_service: RAGService = Depends(get_rag_service),  # pyright: ignore[reportCallInDefaultInitializer]
    memory_service: MemoryService = Depends(get_memory_service),  # pyright: ignore[reportCallInDefaultInitializer]
    search_service: ExternalSearchService = Depends(get_search_service),  # pyright: ignore[reportCallInDefaultInitializer]
    intent_service: IntentService = Depends(get_intent_service),  # pyright: ignore[reportCallInDefaultInitializer]
    review_service: ReviewService = Depends(get_review_service),  # pyright: ignore[reportCallInDefaultInitializer]
    llm_service: LLMService = Depends(get_llm_service),  # pyright: ignore[reportCallInDefaultInitializer]
):
    """Send a message to a room"""
    try:
        body = await request.json()
        content = body.get("content", "").strip()

        if not content:
            raise HTTPException(status_code=400, detail="Message content is required")

        if not user_info or "user_id" not in user_info:
            logger.error(f"Invalid user_info: {user_info}")
            raise HTTPException(status_code=400, detail="Invalid user information")

        message = Message(
            message_id=generate_id(),
            room_id=room_id,
            user_id=user_info["user_id"],
            content=content,
            timestamp=get_current_timestamp(),
        )

        storage_service.save_message(message)
        # Broadcast the user's message
        await manager.broadcast(json.dumps({
            "type": "new_message",
            "payload": message.model_dump()
        }), room_id)

        try:
            current_room = await storage_service.get_room(room_id)
            if current_room and current_room.type == RoomType.REVIEW:
                review_meta = storage_service.get_review_meta(room_id)
                if not review_meta or review_meta.status != 'completed':
                    ai_content = "AI 토론이 아직 진행 중입니다. 완료된 후에 관측자와 대화할 수 있습니다."
                else:
                    final_report = storage_service.get_final_report(room_id)
                    if not final_report:
                        ai_content = "최종 보고서를 찾을 수 없습니다."
                    else:
                        ai_content = await rag_service.generate_observer_qa_response(content, final_report)
                
                ai_message = Message(
                    message_id=generate_id(), room_id=room_id, user_id="ai",
                    content=ai_content, timestamp=get_current_timestamp(), role="ai"
                )
                storage_service.save_message(ai_message)
                await manager.broadcast(json.dumps({
                    "type": "new_message",
                    "payload": ai_message.model_dump()
                }), room_id)
                return create_success_response(data={"message": message.model_dump(), "ai_response": ai_message.model_dump()})

            user_id = user_info["user_id"]
            pending_action_key = f"pending_action:{room_id}"
            pending_action_facts = await memory_service.get_user_facts(user_id, kind='conversation_state', key=pending_action_key)

            intent_from_client = body.get("intent")
            
            if pending_action_facts:
                pending_action = pending_action_facts[0]['value_json'].get('action')
                if pending_action == 'promote_memory_confirmation':
                    if not current_room or not current_room.parent_id:
                        ai_content = "오류: 현재 룸의 상위 룸을 찾을 수 없습니다."
                        await memory_service.delete_user_fact(user_id, 'conversation_state', pending_action_key)
                    else:
                        main_room_id = current_room.parent_id
                        summary = await memory_service.promote_memories(
                            sub_room_id=room_id,
                            main_room_id=main_room_id,
                            criteria_text=content,
                            user_id=user_id
                        )
                        ai_content = summary
                        await memory_service.delete_user_fact(user_id, 'conversation_state', pending_action_key)

                    intent = "memory_promotion_confirmation"
                    entities = {"user_response": content}
                else:
                    intent = intent_from_client or "general"
                    entities = {}
            
            elif intent_from_client:
                intent = intent_from_client
                entities = {}

            else:
                intent_result = await intent_service.classify_intent(
                    content, message.message_id
                )
                intent = intent_result["intent"]
                entities = intent_result.get("entities", {})

            logger.info(f"Intent: {intent}, Entities: {entities}")

            if intent == "time":
                ai_content = search_service.now_kst()
            elif intent == "weather":
                location = entities.get("location") or "서울"
                ai_content = search_service.weather(location)
            elif intent == "wiki":
                topic = entities.get("topic") or "인공지능"
                ai_content = await search_service.wiki(topic)
            elif intent == "search":
                query = entities.get("query") or "AI"
                items = await search_service.search(query, 3)
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
                    ai_content = "아직 이름을 모르는 걸요. '내 이름은 호건이야'처럼 말해주세요!"
            elif intent == "review":
                if not current_room or current_room.type != RoomType.SUB:
                    ai_content = "검토 기능은 서브룸에서만 시작할 수 있습니다."
                else:
                    user_id = user_info["user_id"]
                    topic = content.replace("검토해보자", "").replace("리뷰해줘", "").strip()
                    if not topic:
                        topic = f"'{current_room.name}'에 대한 검토"
                    new_review_room = storage_service.create_room(
                        room_id=generate_id(),
                        name=f"검토: {topic}",
                        owner_id=user_id,
                        room_type=RoomType.REVIEW,
                        parent_id=room_id,
                    )
                    instruction = "이 주제에 대해 3 라운드에 걸쳐 심도 있게 토론해주세요."
                    review_meta = ReviewMeta(
                        review_id=new_review_room.room_id,
                        room_id=new_review_room.room_id,
                        topic=topic,
                        instruction=instruction,
                        total_rounds=3,
                        created_at=get_current_timestamp(),
                    )
                    storage_service.save_review_meta(review_meta)
                    await review_service.start_review_process(
                        review_id=new_review_room.room_id,
                        topic=topic,
                        instruction=instruction,
                        panelists=None,
                        trace_id=message.message_id,
                    )
                    ai_content = f"알겠습니다. '{topic}'에 대한 검토를 시작하겠습니다. '{new_review_room.name}' 룸에서 토론을 확인하세요."
            elif intent == "start_memory_promotion":
                await memory_service.upsert_user_fact(
                    user_id, 
                    kind='conversation_state', 
                    key=pending_action_key, 
                    value={'action': 'promote_memory_confirmation'}, 
                    confidence=1.0
                )
                ai_content = "어떤 대화를 상위 룸으로 올릴까요? '어제 대화 전부' 또는 'AI 윤리에 대한 내용만'과 같이 구체적으로 말씀해주세요."
            else:
                ai_content = await rag_service.generate_rag_response(
                    room_id,
                    user_info["user_id"],
                    content,
                    intent,
                    entities,
                    message.message_id,
                )

            ai_message = Message(
                message_id=generate_id(),
                room_id=room_id,
                user_id="ai",
                content=ai_content,
                timestamp=get_current_timestamp(),
                role="ai",
            )
            storage_service.save_message(ai_message)
            await manager.broadcast(json.dumps({
                "type": "new_message",
                "payload": ai_message.model_dump()
            }), room_id)

            suggestion = None
            if intent in ["general", "memory_promotion_confirmation"]:
                 suggestion = await _check_and_suggest_review(
                    room_id, user_id, storage_service, memory_service, llm_service
                 )

            return create_success_response(
                data={
                    "message": message.model_dump(),
                    "ai_response": ai_message.model_dump(),
                    "intent": intent,
                    "entities": entities,
                    "suggestion": suggestion,
                },
                message="Message sent successfully",
            )

        except Exception as e:
            logger.error(f"Error generating AI response: {e}", exc_info=True)
            return create_success_response(
                data={"message": message.model_dump()},
                message="Message sent, but AI response failed",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@router.post("/{room_id}/upload", response_model=Message)
async def upload_file(
    room_id: str,
    user_info: Dict[str, str] = AUTH_DEPENDENCY,
    file: UploadFile = File(...),
    storage_service: StorageService = Depends(get_storage_service),
):
    """Upload a file to a room, creating a special message for it."""
    user_id = user_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user information")

    room = storage_service.get_room(room_id)
    if not room or room.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Room not found or access denied.")

    try:
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = f"uploads/{unique_filename}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        message_content = {
            "type": "file",
            "url": f"/{file_path}",
            "name": file.filename,
            "size": file.size,
            "content_type": file.content_type,
        }

        new_message = Message(
            message_id=generate_id(),
            room_id=room_id,
            user_id=user_id,
            content=json.dumps(message_content),
            timestamp=get_current_timestamp(),
            role="user",
        )
        storage_service.save_message(new_message)

        return new_message

    except Exception as e:
        logger.error(f"Failed to upload file to room {room_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="File upload failed.")
