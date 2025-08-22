"""
Storage Service - Unified interface for data persistence
"""
import json
import os
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from collections import defaultdict

from app.config.settings import settings
from app.models.schemas import Room, Message, ReviewMeta, PanelReport, ConsolidatedReport

logger = logging.getLogger(__name__)

# In-memory storage for room-specific data
_room_memory = defaultdict(dict)


class StorageService:
    """Unified storage service for file system and Firebase"""
    
    def __init__(self):
        self.data_dir = Path(settings.DATA_DIR)
        self.data_dir.mkdir(exist_ok=True)
        self.firebase_service = None
        
        # Initialize Firebase if configured (lazy initialization)
        if settings.FIREBASE_SERVICE_ACCOUNT_PATH:
            try:
                from app.services.firebase_service import FirebaseService
                self.firebase_service = FirebaseService()
                logger.info("Firebase storage initialized")
            except Exception as e:
                logger.warning(f"Firebase initialization failed: {e}")
                self.firebase_service = None

    # Memory functions for room-specific data
    async def memory_set(self, room_id: str, key: str, value: str) -> None:
        """Set a value in room memory"""
        _room_memory[room_id][key] = value
        logger.info(f"Memory set: {room_id}.{key} = {value}")

    async def memory_get(self, room_id: str, key: str) -> Optional[str]:
        """Get a value from room memory"""
        value = _room_memory[room_id].get(key)
        logger.info(f"Memory get: {room_id}.{key} = {value}")
        return value

    async def memory_clear(self, room_id: str) -> None:
        """Clear all memory for a room"""
        if room_id in _room_memory:
            del _room_memory[room_id]
            logger.info(f"Memory cleared for room: {room_id}")

    def _get_room_path(self, room_id: str) -> Path:
        """Get room directory path"""
        return self.data_dir / "rooms" / room_id
    
    def _get_review_path(self, review_id: str) -> Path:
        """Get review directory path"""
        return self.data_dir / "reviews" / review_id
    
    def _safe_write_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Safely write JSON data to file"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temporary file first
        temp_path = file_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic rename
        os.rename(temp_path, file_path)
    
    def _safe_read_json(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Safely read JSON data from file"""
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
        return None
    
    # Room operations
    async def create_room(self, room_id: str, name: str) -> Room:
        """Create a new room"""
        room_data = {
            "room_id": room_id,
            "name": name,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "message_count": 0
        }
        
        if self.firebase_service:
            await self.firebase_service.create_room(room_id, room_data)
        else:
            room_path = self._get_room_path(room_id)
            self._safe_write_json(room_path / "meta.json", room_data)
        
        return Room(**room_data)
    
    async def get_room(self, room_id: str) -> Optional[Room]:
        """Get room by ID"""
        if self.firebase_service:
            room_data = await self.firebase_service.get_room(room_id)
        else:
            room_path = self._get_room_path(room_id)
            room_data = self._safe_read_json(room_path / "meta.json")
        
        return Room(**room_data) if room_data else None
    
    async def save_message(self, message: Message) -> None:
        """Save a message"""
        if self.firebase_service:
            await self.firebase_service.save_message(message.room_id, message.model_dump())
        else:
            room_path = self._get_room_path(message.room_id)
            messages_file = room_path / "messages.jsonl"
            
            messages_file.parent.mkdir(parents=True, exist_ok=True)
            with open(messages_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(message.model_dump(), ensure_ascii=False) + '\n')
    
    async def get_messages(self, room_id: str) -> List[Message]:
        """Get all messages for a room"""
        if self.firebase_service:
            messages_data = await self.firebase_service.get_messages(room_id)
        else:
            room_path = self._get_room_path(room_id)
            messages_file = room_path / "messages.jsonl"
            
            messages_data = []
            if messages_file.exists():
                with open(messages_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            messages_data.append(json.loads(line))
        
        return [Message(**msg) for msg in messages_data]
    
    # Review operations
    async def create_review(self, review_meta: ReviewMeta) -> None:
        """Create a new review"""
        if self.firebase_service:
            await self.firebase_service.create_review(review_meta.review_id, review_meta.model_dump())
        else:
            review_path = self._get_review_path(review_meta.review_id)
            self._safe_write_json(review_path / "meta.json", review_meta.model_dump())
    
    async def get_review(self, review_id: str) -> Optional[ReviewMeta]:
        """Get review by ID"""
        if self.firebase_service:
            review_data = await self.firebase_service.get_review(review_id)
        else:
            review_path = self._get_review_path(review_id)
            review_data = self._safe_read_json(review_path / "meta.json")
        
        return ReviewMeta(**review_data) if review_data else None
    
    async def update_review(self, review_id: str, review_data: Dict[str, Any]) -> None:
        """Update review metadata"""
        if self.firebase_service:
            await self.firebase_service.update_review(review_id, review_data)
        else:
            review_path = self._get_review_path(review_id)
            self._safe_write_json(review_path / "meta.json", review_data)
    
    async def save_panel_report(self, review_id: str, round_num: int, persona: str, report: PanelReport) -> None:
        """Save panel report"""
        if self.firebase_service:
            await self.firebase_service.save_panel_report(review_id, round_num, persona, report.model_dump())
        else:
            review_path = self._get_review_path(review_id)
            report_file = review_path / f"panel_report_r{round_num}_{persona}.json"
            self._safe_write_json(report_file, report.model_dump())
    
    async def save_consolidated_report(self, review_id: str, round_num: int, report: ConsolidatedReport) -> None:
        """Save consolidated report"""
        if self.firebase_service:
            await self.firebase_service.save_consolidated_report(review_id, round_num, report.model_dump())
        else:
            review_path = self._get_review_path(review_id)
            report_file = review_path / f"consolidated_report_r{round_num}.json"
            self._safe_write_json(report_file, report.model_dump())
    
    async def save_final_report(self, review_id: str, report_data: Dict[str, Any]) -> None:
        """Save final report"""
        if self.firebase_service:
            await self.firebase_service.save_final_report(review_id, report_data)
        else:
            review_path = self._get_review_path(review_id)
            self._safe_write_json(review_path / "final_report.json", report_data)
    
    async def get_final_report(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Get final report"""
        if self.firebase_service:
            return await self.firebase_service.get_final_report(review_id)
        else:
            review_path = self._get_review_path(review_id)
            return self._safe_read_json(review_path / "final_report.json")
    
    async def log_review_event(self, event_data: Dict[str, Any]) -> None:
        """Log review event"""
        if self.firebase_service:
            await self.firebase_service.log_review_event(event_data)
        else:
            review_path = self._get_review_path(event_data["review_id"])
            events_file = review_path / "events.jsonl"
            
            events_file.parent.mkdir(parents=True, exist_ok=True)
            with open(events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event_data, ensure_ascii=False) + '\n')
    
    async def get_review_events(self, review_id: str, since: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get review events"""
        if self.firebase_service:
            return await self.firebase_service.get_review_events(review_id, since)
        else:
            review_path = self._get_review_path(review_id)
            events_file = review_path / "events.jsonl"
            
            events = []
            if events_file.exists():
                with open(events_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            event = json.loads(line)
                            if since is None or event.get("ts", 0) > since:
                                events.append(event)
            
            return events


# Global storage service instance
storage_service = StorageService()

