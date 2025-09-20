"""Utilities for constructing domain objects via public APIs in tests."""
from __future__ import annotations
"""Factory helpers that compose business scenarios for integration tests."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from app.api.dependencies import get_storage_service
from app.models.enums import RoomType
from app.models.schemas import Room


@dataclass
class CreatedRoom:
    room_id: str
    name: str
    owner_id: str
    type: str
    parent_id: Optional[str]

    @classmethod
    def from_response(cls, payload: Dict[str, Any]) -> "CreatedRoom":
        return cls(
            room_id=payload["room_id"],
            name=payload.get("name", ""),
            owner_id=payload.get("owner_id", ""),
            type=payload.get("type", ""),
            parent_id=payload.get("parent_id"),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "owner_id": self.owner_id,
            "type": self.type,
            "parent_id": self.parent_id,
        }


@dataclass
class CreatedReview:
    review_id: str
    room_id: str
    topic: str
    instruction: str

    @classmethod
    def from_response(cls, payload: Dict[str, Any]) -> "CreatedReview":
        return cls(
            review_id=payload["review_id"],
            room_id=payload["room_id"],
            topic=payload.get("topic", ""),
            instruction=payload.get("instruction", ""),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "room_id": self.room_id,
            "topic": self.topic,
            "instruction": self.instruction,
        }


class TestDataBuilder:
    """Helper that drives the HTTP API to create domain scenarios for tests."""

    def __init__(self, client: TestClient, user_id: str) -> None:
        self._client = client
        self._user_id = user_id
        self._created_rooms: List[str] = []
        self._created_reviews: List[str] = []

    @property
    def storage_service(self):
        """Return the storage service bound to the current test dependency overrides."""
        return get_storage_service()

    def ensure_main_room(self, name: str = "Main Room") -> CreatedRoom:
        """Return an existing main room for the user or create one via the API."""
        storage = self.storage_service
        existing: List[Room] = storage.get_rooms_by_owner(self._user_id)
        for room in existing:
            if room.type == RoomType.MAIN:
                payload = room.model_dump()
                return CreatedRoom.from_response(payload)

        response = self._client.post(
            "/api/rooms",
            json={"name": name, "type": RoomType.MAIN.value, "parent_id": None},
        )
        response.raise_for_status()
        data = CreatedRoom.from_response(response.json())
        self._created_rooms.append(data.room_id)
        return data

    def create_sub_room(self, name: str, parent_id: str) -> CreatedRoom:
        """Create a sub room attached to a main room."""
        response = self._client.post(
            "/api/rooms",
            json={"name": name, "type": RoomType.SUB.value, "parent_id": parent_id},
        )
        response.raise_for_status()
        data = CreatedRoom.from_response(response.json())
        self._created_rooms.append(data.room_id)
        return data

    def create_review(self, room_id: str, topic: str, instruction: str) -> CreatedReview:
        """Kick off a review process for a given sub room."""
        response = self._client.post(
            f"/api/rooms/{room_id}/reviews",
            json={"topic": topic, "instruction": instruction},
        )
        response.raise_for_status()
        payload = CreatedReview.from_response(response.json())
        # The review endpoint creates a dedicated review room. Track it for clean-up.
        self._created_reviews.append(payload.review_id)
        self._created_rooms.append(payload.room_id)
        return payload

    def cleanup(self) -> None:
        """Remove all data created by the builder using storage service APIs."""
        storage = self.storage_service
        for review_id in list(self._created_reviews):
            try:
                storage.purge_review_artifacts(review_id)
            except Exception:
                pass
        for room_id in reversed(self._created_rooms):
            try:
                storage.delete_room(room_id)
            except Exception:
                pass
        self._created_reviews.clear()
        self._created_rooms.clear()

    def __enter__(self) -> "TestDataBuilder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context manager convenience
        self.cleanup()
