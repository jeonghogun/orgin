"""Database repository helpers for room persistence logic."""

from __future__ import annotations

import time
from typing import Iterable, List, Optional

from psycopg2.extensions import cursor as Cursor

from app.models.enums import RoomType
from app.models.schemas import Room
from app.services.database_service import DatabaseService


class RoomRepository:
    """Encapsulates SQL queries for room level operations."""

    def __init__(self, db_service: DatabaseService) -> None:
        self._db = db_service

    def create_room(
        self,
        room_id: str,
        name: str,
        owner_id: str,
        room_type: RoomType,
        parent_id: Optional[str] = None,
    ) -> Room:
        timestamp = int(time.time())
        query = (
            "INSERT INTO rooms (room_id, name, owner_id, type, parent_id, created_at, updated_at, message_count) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (
            room_id,
            name,
            owner_id,
            room_type,
            parent_id,
            timestamp,
            timestamp,
            0,
        )
        self._db.execute_update(query, params)
        return Room(
            room_id=room_id,
            name=name,
            owner_id=owner_id,
            type=room_type,
            parent_id=parent_id,
            created_at=timestamp,
            updated_at=timestamp,
            message_count=0,
        )

    def get_room(self, room_id: str) -> Optional[Room]:
        query = "SELECT * FROM rooms WHERE room_id = %s"
        results = self._db.execute_query(query, (room_id,))
        if not results:
            return None
        return Room(**results[0])

    def delete_room_and_dependencies(self, room_id: str) -> bool:
        cleanup_statements: Iterable[tuple[str, tuple[str, ...]]] = (
            (
                "DELETE FROM conversation_messages WHERE thread_id IN (SELECT id FROM conversation_threads WHERE sub_room_id = %s)",
                (room_id,),
            ),
            ("DELETE FROM conversation_threads WHERE sub_room_id = %s", (room_id,)),
            ("DELETE FROM messages WHERE room_id = %s", (room_id,)),
            ("DELETE FROM memories WHERE room_id = %s", (room_id,)),
            ("DELETE FROM reviews WHERE room_id = %s", (room_id,)),
        )

        with self._db.transaction(query_type="delete_room") as cursor:
            for statement, params in cleanup_statements:
                cursor.execute(statement, params)
            cursor.execute("DELETE FROM rooms WHERE room_id = %s", (room_id,))
            affected = cursor.rowcount or 0
        return affected > 0

    def list_rooms_for_owner(self, owner_id: str) -> List[Room]:
        query = "SELECT * FROM rooms WHERE owner_id = %s"
        results = self._db.execute_query(query, (owner_id,))
        return [Room(**row) for row in results]

    def list_all_rooms(self) -> List[Room]:
        query = "SELECT * FROM rooms"
        results = self._db.execute_query(query)
        return [Room(**row) for row in results]

    def update_room_name(self, room_id: str, new_name: str) -> bool:
        query = "UPDATE rooms SET name = %s, updated_at = %s WHERE room_id = %s"
        params = (new_name, int(time.time()), room_id)
        return self._db.execute_update(query, params) > 0

    def increment_message_count(self, room_id: str, cursor: Optional[Cursor] = None) -> None:
        query = "UPDATE rooms SET message_count = message_count + 1, updated_at = %s WHERE room_id = %s"
        params = (int(time.time()), room_id)
        if cursor is not None:
            cursor.execute(query, params)
        else:
            self._db.execute_update(query, params)


def get_room_repository() -> RoomRepository:
    from app.services.database_service import get_database_service

    return RoomRepository(get_database_service())
