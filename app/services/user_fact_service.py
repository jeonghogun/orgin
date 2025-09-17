import logging
import json
from typing import List, Dict, Any, Optional, Set
from prometheus_client import Counter

from app.services.database_service import DatabaseService
from app.services.fact_types import FactType
from app.services.audit_service import AuditService
from app.core.secrets import SecretProvider, get_secret_provider
from app.tasks.fact_tasks import request_user_clarification_task
from app.utils.helpers import generate_id, get_current_timestamp
from app.models.memory_schemas import UserProfile

logger = logging.getLogger(__name__)

# Prometheus Metrics
FACTS_SAVED = Counter("facts_saved_total", "Total number of user facts saved.", ["fact_type"])
FACT_CONFLICTS = Counter("fact_conflicts_total", "Total number of fact conflicts detected.", ["fact_type"])
FACTS_PENDING_REVIEW = Counter("facts_pending_review_total", "Total number of facts marked as pending review.", ["fact_type"])

class UserFactService:
    """
    Service for managing the lifecycle of user facts and user profiles.
    """
    SINGLE_VALUE_FACTS: Set[FactType] = {FactType.MBTI}
    CONFIDENCE_SIMILARITY_THRESHOLD = 0.1

    def __init__(self, db_service: DatabaseService, audit_service: AuditService, secret_provider: SecretProvider):
        self.db = db_service
        self.audit_service = audit_service
        self.secret_provider = secret_provider
        self.db_encryption_key = self.secret_provider.get("DB_ENCRYPTION_KEY")

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        key = self.db_encryption_key
        try:
            query = "SELECT user_id, role, pgp_sym_decrypt(name, %s::text) as name, pgp_sym_decrypt(preferences, %s::text) as preferences, auto_fact_extraction_enabled, conversation_style, interests, created_at, updated_at FROM user_profiles WHERE user_id = %s"
            params = (key, key, user_id)
            results = self.db.execute_query(query, params)
            if results:
                profile_data = results[0]
                profile_data['preferences'] = json.loads(profile_data['preferences']) if profile_data.get('preferences') else {}
                profile_data['interests'] = profile_data.get('interests') or []
                return UserProfile(**profile_data)

            logger.info(f"No profile found for user '{user_id}'. Creating a default one.")
            new_profile = UserProfile(user_id=user_id, created_at=get_current_timestamp(), updated_at=get_current_timestamp())
            insert_query = "INSERT INTO user_profiles (user_id, role, name, preferences, auto_fact_extraction_enabled, conversation_style, interests, created_at, updated_at) VALUES (%s, %s, pgp_sym_encrypt(%s, %s::text), pgp_sym_encrypt(%s, %s::text), %s, %s, %s, %s, %s)"
            # Corrected INSERT statement with 10 values for 10 columns
            insert_params = (
                new_profile.user_id, new_profile.role, new_profile.name, key,
                json.dumps(new_profile.preferences), key, new_profile.auto_fact_extraction_enabled,
                new_profile.conversation_style, new_profile.interests, new_profile.created_at, new_profile.updated_at
            )
            self.db.execute_update(insert_query, insert_params)
            return new_profile
        except Exception as e:
            logger.error(f"Failed to get or create user profile for '{user_id}': {e}", exc_info=True)
            return None

    async def update_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> Optional[UserProfile]:
        key = self.db_encryption_key
        if not profile_data: return await self.get_user_profile(user_id)
        profile_data["updated_at"] = get_current_timestamp()
        set_clauses, params, encrypted_fields = [], [], {"name", "preferences"}
        for field, value in profile_data.items():
            if field in encrypted_fields:
                value_to_encrypt = json.dumps(value) if field == "preferences" else value
                if value_to_encrypt is not None:
                    set_clauses.append(f"{field} = pgp_sym_encrypt(%s, %s)")
                    params.extend([value_to_encrypt, key])
                else: set_clauses.append(f"{field} = NULL")
            else:
                set_clauses.append(f"{field} = %s")
                params.append(value)
        if not set_clauses: return await self.get_user_profile(user_id)
        query = f"UPDATE user_profiles SET {', '.join(set_clauses)} WHERE user_id = %s"
        params.append(user_id)
        try:
            self.db.execute_update(query, tuple(params))
            return await self.get_user_profile(user_id)
        except Exception as e:
            logger.error(f"Failed to update profile for user '{user_id}': {e}", exc_info=True)
            return None

    async def _insert_fact(self, user_id: str, fact: Dict[str, Any], normalized_value: str, source_message_id: str, sensitivity: str, is_latest: bool, pending_review: bool = False) -> str:
        new_fact_id = generate_id()
        query = "INSERT INTO user_facts (id, user_id, fact_type, value_json, normalized_value, source_message_id, confidence, latest, pending_review, sensitivity, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"
        params = (
            new_fact_id, user_id, fact['type'], json.dumps(fact['value']), normalized_value,
            source_message_id, fact.get('confidence', 0.8), is_latest, pending_review, sensitivity
        )
        self.db.execute_update(query, params)
        FACTS_SAVED.labels(fact_type=fact['type']).inc()
        await self.audit_service.log('fact_saved', {'fact_id': new_fact_id, 'user_id': user_id, 'fact_type': fact['type']})
        return new_fact_id

    async def save_fact(self, user_id: str, fact: Dict[str, Any], normalized_value: str, source_message_id: str, sensitivity: str, room_id: str):
        fact_type = FactType(fact['type'])
        if fact_type == FactType.USER_NAME:
            await self.update_user_profile(user_id, {'name': fact['value']})
            return

        existing_fact_query = "SELECT id FROM user_facts WHERE user_id = %s AND fact_type = %s AND normalized_value = %s"
        if self.db.execute_query(existing_fact_query, (user_id, fact_type.value, normalized_value)):
            logger.info(f"Duplicate fact detected for user {user_id}, type {fact_type.value}. Ignoring.")
            return

        if fact_type in self.SINGLE_VALUE_FACTS:
            conflict_query = "SELECT id, confidence FROM user_facts WHERE user_id = %s AND fact_type = %s AND latest = TRUE"
            conflicting_facts = self.db.execute_query(conflict_query, (user_id, fact_type.value))
            if conflicting_facts:
                old_fact = conflicting_facts[0]
                new_confidence = fact.get('confidence', 0.8)
                if abs(new_confidence - old_fact['confidence']) <= self.CONFIDENCE_SIMILARITY_THRESHOLD:
                    FACT_CONFLICTS.labels(fact_type=fact_type.value).inc()
                    self.db.execute_update("UPDATE user_facts SET pending_review = TRUE WHERE id = %s", (old_fact['id'],))
                    new_fact_id = await self._insert_fact(user_id, fact, normalized_value, source_message_id, sensitivity, is_latest=False, pending_review=True)
                    FACTS_PENDING_REVIEW.labels(fact_type=fact_type.value).inc()
                    request_user_clarification_task.delay(user_id=user_id, room_id=room_id, fact_type=fact_type.value, fact_ids=[str(old_fact['id']), new_fact_id])
                    return
                elif new_confidence > old_fact['confidence']:
                    self.db.execute_update("UPDATE user_facts SET latest = FALSE WHERE id = %s", (old_fact['id'],))
                else:
                    await self._insert_fact(user_id, fact, normalized_value, source_message_id, sensitivity, is_latest=False)
                    return

        await self._insert_fact(user_id, fact, normalized_value, source_message_id, sensitivity, is_latest=True)

    async def list_facts(self, user_id: str, fact_type: Optional[FactType] = None, latest_only: bool = False) -> List[Dict[str, Any]]:
        formatted_results = []
        
        # USER_NAME인 경우 user_profiles 테이블에서 조회
        if fact_type == FactType.USER_NAME:
            logger.info(f"=== CHECKING USER_PROFILES FOR NAME === User: {user_id}")
            profile = await self.get_user_profile(user_id)
            if profile and profile.name:
                formatted_results.append({
                    "type": "user_name",
                    "value": profile.name,
                    "confidence": 1.0,
                    "created_at": profile.created_at,
                    "updated_at": profile.updated_at
                })
                logger.info(f"=== FOUND NAME IN PROFILE === {profile.name}")
            else:
                logger.info(f"=== NO NAME FOUND IN PROFILE ===")
            return formatted_results
        
        # 다른 사실들은 user_facts 테이블에서 조회
        query = "SELECT * FROM user_facts WHERE user_id = %s"
        params = [user_id]
        if fact_type:
            query += " AND fact_type = %s"
            params.append(fact_type.value)
        if latest_only:
            query += " AND latest = TRUE"
        query += " ORDER BY fact_type, updated_at DESC"
        
        logger.info(f"=== LIST_FACTS QUERY === {query}")
        logger.info(f"=== LIST_FACTS PARAMS === {params}")
        
        results = self.db.execute_query(query, tuple(params))
        logger.info(f"=== LIST_FACTS RESULTS === {results}")
        
        # 결과를 올바른 형식으로 변환
        for fact in results:
            # value_json에서 실제 값을 추출
            value_json = fact.get("value_json")
            if value_json:
                try:
                    if isinstance(value_json, str):
                        value_data = json.loads(value_json)
                    else:
                        value_data = value_json
                    actual_value = value_data.get("value", "") if isinstance(value_data, dict) else str(value_data)
                except (json.JSONDecodeError, TypeError):
                    actual_value = str(value_json)
            else:
                actual_value = ""

            formatted_fact = {
                "type": fact.get("fact_type"),
                "value": actual_value,
                "content": actual_value,
                "confidence": fact.get("confidence", 1.0),
                "created_at": fact.get("created_at"),
                "updated_at": fact.get("updated_at")
            }
            formatted_results.append(formatted_fact)
        
        logger.info(f"=== LIST_FACTS FORMATTED === {formatted_results}")
        return formatted_results

    async def get_facts_pending_review(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        query = "SELECT * FROM user_facts WHERE pending_review = TRUE ORDER BY updated_at DESC LIMIT %s OFFSET %s"
        return self.db.execute_query(query, (limit, offset))

    async def resolve_fact_conflict(self, winning_fact_id: str, losing_fact_id: str):
        self.db.execute_update("UPDATE user_facts SET latest = TRUE, pending_review = FALSE WHERE id = %s", (winning_fact_id,))
        self.db.execute_update("DELETE FROM user_facts WHERE id = %s", (losing_fact_id,))
        if hasattr(self.audit_service, "log"):
            await self.audit_service.log(
                "fact_conflict_resolved",
                {"winning_fact_id": winning_fact_id, "losing_fact_id": losing_fact_id}
            )
        logger.info("Resolved fact conflict.", extra={"winner": winning_fact_id, "loser": losing_fact_id})


_user_fact_service_instance: Optional[UserFactService] = None


def get_user_fact_service() -> UserFactService:
    """Return a singleton instance of UserFactService."""
    global _user_fact_service_instance
    if _user_fact_service_instance is None:
        from app.services.database_service import get_database_service
        from app.services.audit_service import get_audit_service

        _user_fact_service_instance = UserFactService(
            db_service=get_database_service(),
            audit_service=get_audit_service(),
            secret_provider=get_secret_provider()
        )
    return _user_fact_service_instance
