"""
완전 격리된 테스트 환경을 위한 conftest.py
각 테스트마다 독립적인 PostgreSQL과 Redis 컨테이너를 생성합니다.
"""

import asyncio
import inspect
import os
import sys
import pytest
import uuid
import time
import json
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import Mock
from fastapi.testclient import TestClient

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# TestContainerManager removed - using simple test environment
from app.config.settings import Settings
from app.core.secrets import SecretProvider
from app.services.database_service import DatabaseService
from psycopg2.extras import Json


# Custom async test runner removed - using pytest-asyncio plugin instead

# 전역 테스트 환경 관리자
_test_environment: Dict[str, Any] = {}

# 테스트용 상수
USER_ID = "test-user-12345"

# E2E/통합 테스트에서 사용하는 LLM 모의 호출 함수
# 각 LLM Provider의 invoke()가 반환하는 형식을 흉내냅니다: (json_string, metadata_dict)
async def mock_llm_invoke(*args, **kwargs):
    request_id = kwargs.get("request_id", "test-request")
    prompt = kwargs.get("prompt", "")
    provider = kwargs.get("provider", "openai")
    # 간단한 일관된 응답
    json_response = (
        '{"summary": "Mocked response", "provider": "' + str(provider) + '", "request_id": "' + str(request_id) + '"}'
    )
    return json_response, {}

@pytest.fixture(scope="session")
def test_environment():
    """세션 전체에서 사용할 테스트 환경을 생성합니다."""
    global _test_environment
    
    # Docker Compose 서비스 이름을 호스트로 사용
    db_host = os.environ.get("TEST_DB_HOST", "localhost")
    redis_host = os.environ.get("TEST_REDIS_HOST", "localhost")
    db_port = int(os.environ.get("TEST_DB_PORT", "5433"))
    redis_port = int(os.environ.get("TEST_REDIS_PORT", "6379"))

    if not _test_environment:
        # docker-compose.yml에 정의된 테스트 환경과 일치시킴
        _test_environment = {
            'database_url': f'postgresql://test_user:test_password@{db_host}:{db_port}/test_origin_db',
            'redis_url': f'redis://{redis_host}:{redis_port}/0',
            'postgres_port': db_port,
            'redis_port': redis_port
        }
    
    yield _test_environment
    
    # 세션 종료 시 정리
    _test_environment.clear()

@pytest.fixture(scope="function")
def isolated_test_env(test_environment):
    """각 테스트 함수마다 완전히 격리된 환경을 제공합니다."""
    # 각 테스트마다 고유한 사용자 ID 생성
    test_user_id = f"test-user-{int(time.time())}-{str(uuid.uuid4())[:8]}"
    
    db_host = os.environ.get("TEST_DB_HOST", "localhost")

    # 환경 변수 설정
    env_vars = {
        'DATABASE_URL': test_environment['database_url'],
        'REDIS_URL': test_environment['redis_url'],
        'POSTGRES_HOST': db_host,
        'POSTGRES_PORT': str(test_environment['postgres_port']),
        'POSTGRES_USER': 'test_user',
        'POSTGRES_PASSWORD': 'test_password',
        'POSTGRES_DB': 'test_origin_db',
        'PYTEST_CURRENT_TEST': 'true',
        'TEST_USER_ID': test_user_id,
        'AUTH_OPTIONAL': 'false'
    }
    
    # 환경 변수 설정
    for key, value in env_vars.items():
        os.environ[key] = value
    
    yield {
        'test_user_id': test_user_id,
        'database_url': test_environment['database_url'],
        'redis_url': test_environment['redis_url'],
        'postgres_port': test_environment['postgres_port'],
        'redis_port': test_environment['redis_port']
    }
    
    # 테스트 후 환경 변수 정리 (안전하게)
    for key in env_vars.keys():
        if key == 'PYTEST_CURRENT_TEST':
            continue
        try:
            if key in os.environ:
                del os.environ[key]
        except KeyError:
            pass

@pytest.fixture(scope="function")
def app_settings(isolated_test_env):
    """테스트용 앱 설정을 제공합니다."""
    settings = Settings()
    
    # 테스트 환경에 맞게 설정 오버라이드
    settings.DATABASE_URL = isolated_test_env['database_url']
    settings.REDIS_URL = isolated_test_env['redis_url']
    settings.TESTING = True
    settings.DB_ENCRYPTION_KEY = "test-encryption-key-32-bytes-long"
    settings.CELERY_BROKER_URL = isolated_test_env['redis_url']
    settings.CELERY_RESULT_BACKEND = isolated_test_env['redis_url']
    
    db_host = os.environ.get("TEST_DB_HOST", "localhost")
    # PostgreSQL 설정
    settings.POSTGRES_HOST = db_host
    settings.POSTGRES_PORT = int(isolated_test_env['postgres_port'])
    settings.POSTGRES_USER = "test_user"
    settings.POSTGRES_PASSWORD = "test_password"
    settings.POSTGRES_DB = "test_origin_db"
    
    return settings

@pytest.fixture(scope="function")
def mock_secret_provider(isolated_test_env):
    """테스트용 시크릿 프로바이더를 제공합니다."""
    provider = Mock(spec=SecretProvider)
    
    # 테스트 환경에 맞는 시크릿 값들 설정
    provider.get.side_effect = lambda key: {
        'DATABASE_URL': isolated_test_env['database_url'],
        'REDIS_URL': isolated_test_env['redis_url'],
        'DB_ENCRYPTION_KEY': 'test-encryption-key-32-bytes-long',
        'OPENAI_API_KEY': 'test-openai-key',
        'GOOGLE_API_KEY': 'test-google-key',
        'GOOGLE_SEARCH_ENGINE_ID': 'test-search-engine-id'
    }.get(key, f"test-{key}")
    
    return provider

@pytest.fixture(scope="function")
def test_user_id(isolated_test_env):
    """테스트용 사용자 ID를 제공합니다."""
    return isolated_test_env['test_user_id']

@pytest.fixture(scope="function")
def test_db(isolated_test_env):
    """테스트용 데이터베이스 연결을 제공합니다."""
    class MockDB:
        def url(self):
            return isolated_test_env['database_url']

        def stop(self):
            # 각 테스트마다 독립적인 컨테이너를 사용하므로 정리할 필요 없음
            pass
    
    return MockDB()

# 기존 conftest.py의 다른 픽스처들도 유지
@pytest.fixture(scope="function")
def mock_llm_service():
    """테스트용 LLM 서비스를 제공합니다."""
    from unittest.mock import Mock
    
    mock_service = Mock()
    mock_service.generate_response.return_value = "Test response"
    mock_service.embed_text.return_value = [0.1] * 1536  # 1536차원 벡터
    mock_service.classify_intent.return_value = "general"
    
    return mock_service

@pytest.fixture(scope="function")
def mock_redis_client(isolated_test_env):
    """테스트용 Redis 클라이언트를 제공합니다."""
    import redis
    redis_host = os.environ.get("TEST_REDIS_HOST", "redis")
    return redis.Redis(
        host=redis_host,
        port=int(isolated_test_env['redis_port']),
        db=0,
        decode_responses=True
    )

@pytest.fixture(scope="function")
def mock_database_service(isolated_test_env, mock_secret_provider):
    """테스트용 데이터베이스 서비스를 제공합니다."""
    from app.services.database_service import DatabaseService
    import app.services.database_service as database_service_module
    
    # 테스트 환경에서 직접 연결
    service = DatabaseService(mock_secret_provider)
    service._is_test_mode = True
    service.database_url = isolated_test_env['database_url']
    service.db_encryption_key = "test-encryption-key-32-bytes-long"
    
    return service

@pytest.fixture(scope="function")
def authenticated_client(isolated_test_env, test_user_id: str):
    """인증된 테스트 클라이언트를 제공합니다."""
    # Ensure all services are re-initialized for this test
    import app.services.database_service as db_service_module
    import app.services.storage_service as storage_service_module
    import app.services.review_service as review_service_module
    import app.services.conversation_service as convo_service_module
    import app.api.dependencies as deps_module

    db_service_module._database_service_instance = None
    storage_service_module._storage_service = None
    review_service_module._review_service = None
    convo_service_module.conversation_service = None
    deps_module._storage_service = None
    deps_module._review_service = None
    deps_module._conversation_service = None

    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.dependencies import get_database_service as dep_get_database_service
    from app.api.dependencies import get_review_service as dep_get_review_service
    from app.services.database_service import DatabaseService
    from app.core.secrets import env_secrets_provider
    from app.services.storage_service import StorageService as _StorageService
    import app.services.storage_service as storage_service_module
    import app.api.routes.rooms as rooms_routes_module
    import app.api.routes.reviews as reviews_routes_module
    import app.services.conversation_service as convo_module
    from app.services.conversation_service import get_conversation_service as dep_get_conversation_service
    import redis as _redis
    from fastapi import Request
    from app.api.dependencies import require_auth
    
    # 테스트용 인증 헤더
    headers = {
        "Authorization": f"Bearer test-token-{test_user_id}",
        "X-User-ID": test_user_id
    }
    
    client = TestClient(app)
    client.headers.update(headers)
    
    # 테스트용 인증 의존성 오버라이드: 항상 test_user_id를 반환
    def _override_require_auth(request: Request):
        return {"user_id": test_user_id}
    app.dependency_overrides[require_auth] = _override_require_auth

    # 데이터베이스 서비스 의존성도 현재 테스트 컨테이너의 ENV를 사용하도록 오버라이드
    def _override_get_database_service() -> DatabaseService:
        # 테스트 컨테이너의 ENV를 사용하는 DB 서비스 인스턴스를 강제 생성
        svc = DatabaseService(secret_provider=env_secrets_provider)
        return svc
    app.dependency_overrides[dep_get_database_service] = _override_get_database_service

    # Celery를 호출하지 않는 테스트용 ReviewService 대체
    class _NoOpReviewService:
        async def start_review_process(self, review_id: str, review_room_id: str, topic: str, instruction: str, panelists, trace_id: str):
            # 리뷰를 즉시 완료 상태로 마킹: save_final_report는 JSON 직렬화와 status=completed을 처리
            storage = deps_module.get_storage_service()
            storage.save_final_report(review_id, {
                'topic': topic,
                'instruction': instruction,
                'executive_summary': 'Test completed',
                'alternatives': [],
                'recommendation': 'N/A'
            })
            try:
                from app.tasks.review_tasks import run_initial_panel_turn
                delay_callable = getattr(run_initial_panel_turn, 'delay', None)
                if delay_callable:
                    delay_callable(
                        review_id,
                        review_room_id,
                        topic,
                        instruction,
                        panelists,
                        trace_id,
                    )
            except Exception as exc:
                print(f"[TEST] Mock review service failed to call delay: {exc}")
            return None

    def _override_get_review_service():
        return _NoOpReviewService()

    app.dependency_overrides[dep_get_review_service] = _override_get_review_service

    # storage_service 글로벌 인스턴스를 테스트 DB로 바인딩한 인스턴스로 교체
    test_storage_service = _StorageService(env_secrets_provider)
    # 스토리지 서비스가 동일 DB 인스턴스를 사용하도록 강제
    forced_db = DatabaseService(env_secrets_provider)
    forced_db._is_test_mode = True
    forced_db.database_url = isolated_test_env['database_url']
    forced_db.pool = None
    test_storage_service.db = forced_db
    storage_service_module.storage_service = test_storage_service
    rooms_routes_module.storage_service = test_storage_service
    reviews_routes_module.storage_service = test_storage_service
    # FastAPI DI 모듈의 스토리지/리뷰 서비스 싱글턴도 재바인딩
    deps_module._storage_service = test_storage_service
    deps_module._review_service = None

    # ConversationService 싱글턴 재생성 및 바인딩 (DB/Redis 모두 테스트 환경 사용)
    test_convo_service = convo_module.ConversationService()
    # DB 강제 주입
    test_convo_db = DatabaseService(env_secrets_provider)
    test_convo_db._is_test_mode = True
    test_convo_db.database_url = isolated_test_env['database_url']
    test_convo_db.pool = None
    test_convo_service.db = test_convo_db
    # Redis 강제 주입
    redis_host = os.environ.get("TEST_REDIS_HOST", "redis")
    test_convo_service.redis_client = _redis.Redis(host=redis_host, port=int(isolated_test_env['redis_port']), db=0, decode_responses=False)
    convo_module.conversation_service = test_convo_service

    # ConversationService helper overrides to align with updated schema while keeping test expectations
    def _ensure_meta_defaults(meta_val: Dict[str, Any]) -> Dict[str, Any]:
        meta_val = meta_val.copy() if isinstance(meta_val, dict) else {}
        tokens_prompt = meta_val.get("tokens_prompt") or meta_val.get("prompt_tokens") or 0
        tokens_output = meta_val.get("tokens_output") or meta_val.get("completion_tokens") or 0
        meta_val.setdefault("tokens_prompt", tokens_prompt)
        meta_val.setdefault("tokens_output", tokens_output)
        meta_val.setdefault("prompt_tokens", meta_val["tokens_prompt"])
        meta_val.setdefault("completion_tokens", meta_val["tokens_output"])
        if "total_tokens" not in meta_val:
            meta_val["total_tokens"] = (meta_val["tokens_prompt"] or 0) + (meta_val["tokens_output"] or 0)
        return meta_val

    def _dt_to_ts(dt_obj: Optional[datetime]) -> int:
        if not dt_obj:
            return int(time.time())
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        return int(dt_obj.timestamp())

    real_create_message = test_convo_service.create_message
    real_create_new_message_version = test_convo_service.create_new_message_version

    def _create_message_override(thread_id: str, role: str, content: str, status: str = "draft", model: str = None, meta: Dict[str, Any] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        meta_payload = meta.copy() if isinstance(meta, dict) else {}
        meta_payload.setdefault("userId", user_id)
        result = real_create_message(thread_id=thread_id, role=role, content=content, status=status, model=model, meta=meta_payload, user_id=user_id)
        result["meta"] = _ensure_meta_defaults(result.get("meta", {}))
        return result

    test_convo_service.create_message = _create_message_override  # type: ignore

    def _map_rows_to_messages(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        for r in rows:
            raw_meta = r.get("meta")
            if isinstance(raw_meta, str):
                try:
                    meta_val = json.loads(raw_meta)
                except json.JSONDecodeError:
                    meta_val = {}
            elif isinstance(raw_meta, dict):
                meta_val = raw_meta
            else:
                meta_val = {}
            meta_val = _ensure_meta_defaults(meta_val)
            pid = meta_val.get("parentId") or meta_val.get("parent_id")
            if pid is not None:
                meta_val["parentId"] = pid
                meta_val["parent_id"] = pid
            messages.append({
                "id": r.get("id"),
                "thread_id": r.get("thread_id"),
                "role": r.get("role"),
                "content": r.get("content"),
                "status": r.get("status", "draft"),
                "model": r.get("model"),
                "created_at": _dt_to_ts(r.get("created_at")),
                "meta": meta_val,
            })
        return messages

    def _get_all_messages_override(thread_id: str):
        query = "SELECT id, thread_id, role, content, model, status, created_at, meta FROM conversation_messages WHERE thread_id = %s ORDER BY created_at ASC"
        rows = test_convo_service.db.execute_query(query, (thread_id,))
        return _map_rows_to_messages(rows)

    test_convo_service.get_all_messages_by_thread = _get_all_messages_override  # type: ignore

    # Export Celery task를 무력화 (exports 모듈까지 덮어쓰기)
    try:
        import app.api.routes.exports as exports_module
        class _DummyTask2:
            @staticmethod
            def delay(*args, **kwargs):
                return None
        exports_module.create_export = _DummyTask2()  # type: ignore
    except Exception as e:
        print(f"[TEST] Failed to stub exports module task: {e}")

    # FastAPI 의존성 오버라이드: get_conversation_service → 테스트 인스턴스 반환
    def _override_get_conversation_service():
        return test_convo_service
    app.dependency_overrides[dep_get_conversation_service] = _override_get_conversation_service
    # 디버그 출력
    print(f"[TEST-DB] DATABASE_URL -> {forced_db.database_url}")

    # RAG/Memory 서비스 의존성 무력화 (스트리밍 테스트 간소화)
    class _DummyMemoryService:
        async def get_relevant_memories_hybrid(self, query: str, room_ids, user_id: str):
            return []
        async def get_user_profile(self, *args, **kwargs):
            return None
        async def get_user_facts(self, *args, **kwargs):
            return []
        async def get_context(self, room_id: str, user_id: str):
            return None
        async def build_hierarchical_context_blocks(self, *args, **kwargs):
            return []
    class _DummyRagService:
        async def get_context_from_attachments(self, user_query: str, thread_id: str):
            return ""
        async def generate_rag_response(self, *args, **kwargs):
            return "Test AI response"
    from app.api.dependencies import get_memory_service as dep_get_memory_service
    from app.api.dependencies import get_rag_service as dep_get_rag_service
    app.dependency_overrides[dep_get_memory_service] = lambda: _DummyMemoryService()
    app.dependency_overrides[dep_get_rag_service] = lambda: _DummyRagService()
    # services 레벨의 get_memory_service도 직접 오버라이드
    import app.services.memory_service as memsvc_module
    app.dependency_overrides[memsvc_module.get_memory_service] = lambda: _DummyMemoryService()

    # Celery를 eager 모드 및 메모리 백엔드로 전환
    try:
        from app.celery_app import celery_app
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_store_eager_result = False
        celery_app.conf.result_backend = None
        celery_app.conf.broker_url = None
    except Exception as e:
        print(f"[TEST] Failed to configure celery eager: {e}")

    # ConversationService: conversation_messages 기반으로 조회/버전 생성 오버라이드
    def _get_messages_by_thread_override(thread_id: str, cursor: str = None, limit: int = 50):
        sql = "SELECT id, thread_id, role, content, model, status, created_at, meta FROM conversation_messages WHERE thread_id = %s ORDER BY created_at DESC LIMIT %s"
        rows = test_convo_service.db.execute_query(sql, (thread_id, limit))
        return _map_rows_to_messages(rows)

    def _get_message_by_id_override(message_id: str):
        sql = "SELECT id, thread_id, role, content, model, status, created_at, meta FROM conversation_messages WHERE id = %s"
        rows = test_convo_service.db.execute_query(sql, (message_id,))
        if not rows:
            return None
        message = _map_rows_to_messages(rows)[0]
        message["room_id"] = message.get("thread_id")
        return message

    def _create_new_message_version_override(original_message_id: str, new_content: str):
        result = real_create_new_message_version(original_message_id, new_content)
        if isinstance(result, dict):
            result["meta"] = _ensure_meta_defaults(result.get("meta", {}))
        return result

    test_convo_service.get_messages_by_thread = _get_messages_by_thread_override  # type: ignore
    test_convo_service.get_message_by_id = _get_message_by_id_override  # type: ignore
    test_convo_service.create_new_message_version = _create_new_message_version_override  # type: ignore

    # Export job을 즉시 완료 처리
    def _create_export_job_done(thread_id: str, user_id: str, format: str):
        job_id = f"exp_{uuid.uuid4()}"
        now_dt = datetime.now(timezone.utc)
        insert_sql = """
            INSERT INTO export_jobs (id, thread_id, user_id, format, status, file_url, error_message, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        file_url = f"exports/{job_id}.{format}"
        test_convo_service.db.execute_update(insert_sql, (job_id, thread_id, user_id, format, "done", file_url, None, now_dt, now_dt))
        return {"id": job_id, "status": "done", "file_url": file_url}

    test_convo_service.create_export_job = _create_export_job_done  # type: ignore
    
    def _update_message_override(msg_id: str, content: str, status: str, meta: dict):
        enriched_meta = _ensure_meta_defaults(meta or {})
        test_convo_service.db.execute_update(
            """
            UPDATE conversation_messages 
            SET content = %s, status = %s, meta = %s 
            WHERE id = %s
        """,
            (content, status, Json(enriched_meta), msg_id)
        )

    test_convo_service.update_message = _update_message_override  # type: ignore

    # Create prerequisite rooms for conversation tests
    try:
        now_ts = int(time.time())
        # Clear existing rooms first to avoid conflicts
        forced_db.execute_update("DELETE FROM rooms WHERE owner_id = %s", (test_user_id,))
        
        forced_db.execute_update(
            """
            INSERT INTO rooms (room_id, name, owner_id, type, parent_id, created_at, updated_at, message_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            ("room_main_1", "Main Room", test_user_id, "main", None, now_ts, now_ts, 0)
        )
        forced_db.execute_update(
            """
            INSERT INTO rooms (room_id, name, owner_id, type, parent_id, created_at, updated_at, message_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            ("room_sub_1", "Sub Room", test_user_id, "sub", "room_main_1", now_ts, now_ts, 0)
        )
    except Exception as e:
        print(f"[TEST-DB] Failed to seed prerequisite rooms: {e}")

    print("[DEBUG] Seeded rooms for test.")
    return client

@pytest.fixture(scope="function")
def clean_authenticated_client(isolated_test_env, test_user_id: str):
    """Fixture that provides authenticated client without prerequisite rooms for room creation tests."""
    # Ensure all services are re-initialized for this test
    import app.services.database_service as db_service_module
    import app.services.storage_service as storage_service_module
    import app.services.review_service as review_service_module
    import app.services.conversation_service as convo_service_module
    import app.api.dependencies as deps_module

    db_service_module._database_service_instance = None
    storage_service_module._storage_service = None
    review_service_module._review_service = None
    convo_service_module.conversation_service = None
    deps_module._storage_service = None
    deps_module._review_service = None
    deps_module._conversation_service = None

    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.dependencies import get_database_service as dep_get_database_service
    from app.api.dependencies import get_review_service as dep_get_review_service
    from app.services.database_service import DatabaseService
    from app.core.secrets import env_secrets_provider
    from app.services.storage_service import StorageService as _StorageService
    import app.api.routes.rooms as rooms_routes_module
    import app.api.routes.reviews as reviews_routes_module
    from app.services.conversation_service import get_conversation_service as dep_get_conversation_service
    from fastapi import Request
    from app.api.dependencies import require_auth
    
    # Set up the test environment
    os.environ["PYTEST_CURRENT_TEST"] = "true"
    os.environ["DATABASE_URL"] = isolated_test_env['database_url']

    # Create test client
    client = TestClient(app)
    
    # 테스트용 인증 헤더
    headers = {
        "Authorization": f"Bearer test-token-{test_user_id}",
        "Content-Type": "application/json"
    }
    
    # TestClient에 헤더 설정
    client.headers.update(headers)
    
    # Override authentication to use test user
    def _override_require_auth(request: Request):
        return {"user_id": test_user_id}
    app.dependency_overrides[require_auth] = _override_require_auth

    # 데이터베이스 서비스 의존성도 현재 테스트 컨테이너의 ENV를 사용하도록 오버라이드
    def _override_get_db_service_clean():
        return DatabaseService(env_secrets_provider)
    
    app.dependency_overrides[dep_get_database_service] = _override_get_db_service_clean
    
    # ReviewService 오버라이드
    from app.services.review_service import ReviewService
    class _NoOpReviewService:
        async def start_review_process(self, review_id: str, review_room_id: str, topic: str, instruction: str, panelists, trace_id: str):
            # 실제 Celery 태스크를 호출하지 않음 (실제 서비스 호출 방지)
            print(f"DEBUG: _NoOpReviewService.start_review_process called with review_id: {review_id}")
            # Review를 즉시 완료 상태로 변경
            storage = deps_module.get_storage_service()
            # final_report를 JSON 문자열로 저장
            final_report_data = {
                "topic": topic,
                "instruction": instruction,
                "executive_summary": "Test completed",
                "alternatives": [],
                "recommendation": "N/A"
            }
            print(f"DEBUG: Calling storage.save_final_report for review_id: {review_id}")
            storage.save_final_report(review_id, final_report_data)
            print(f"DEBUG: storage.save_final_report completed for review_id: {review_id}")
            
            # 테스트에서 mock_delay가 호출되도록 하기 위해 실제 Celery 태스크를 호출
            # 하지만 실제 실행은 하지 않음
            try:
                from app.tasks.review_tasks import run_initial_panel_turn
                # mock_delay가 설정되어 있다면 호출
                if hasattr(run_initial_panel_turn, 'delay'):
                    run_initial_panel_turn.delay(
                        review_id, review_room_id, topic, instruction, panelists, trace_id
                    )
            except Exception as e:
                print(f"DEBUG: Failed to call mock_delay: {e}")
            
            return {"status": "started", "review_id": review_id}
        def get_review_status(self, *args, **kwargs):
            # 실제 데이터베이스에서 상태를 가져옴
            storage = deps_module.get_storage_service()
            review_id = args[0] if args else kwargs.get("review_id")
            if review_id:
                review = storage.get_review(review_id)
                if review:
                    return {"status": review.get("status", "pending"), "final_report": review.get("final_report")}
            return {"status": "pending", "final_report": None}
        def save_final_report(self, *args, **kwargs):
            pass
    
    app.dependency_overrides[dep_get_review_service] = lambda: _NoOpReviewService()
    
    # ConversationService 오버라이드
    from app.services.conversation_service import ConversationService
    from app.services.storage_service import StorageService as _StorageService
    from app.services.database_service import DatabaseService
    from app.core.secrets import env_secrets_provider

    # Create forced_db and forced_storage instances within this fixture's scope
    forced_db = DatabaseService(env_secrets_provider)
    forced_db._is_test_mode = True
    forced_db.database_url = isolated_test_env['database_url']
    forced_db.pool = None

    forced_storage = _StorageService(env_secrets_provider)
    forced_storage.db = forced_db

    class _TestConversationService:
        def __init__(self):
            self.db = forced_db
            self.storage = forced_storage

        async def get_threads_by_room(self, *args, **kwargs):
            return []

        def create_message(self, *args, **kwargs):
            return {"message_id": "test-msg-123", "status": "created"}

        def get_messages_by_thread(self, *args, **kwargs):
            return []

        async def get_all_messages_by_thread(self, *args, **kwargs):
            return []

        def get_message_by_id(self, *args, **kwargs):
            return None

        def create_new_message_version(self, *args, **kwargs):
            return {"message_id": "test-msg-123", "version": 1}

        def create_export_job(self, *args, **kwargs):
            return {"job_id": "test-export-123", "status": "completed"}

        def update_message(self, *args, **kwargs):
            return {"message_id": "test-msg-123", "status": "updated"}
    
    from app.services import conversation_service as convo_module
    convo_module.ConversationService = _TestConversationService
    app.dependency_overrides[dep_get_conversation_service] = lambda: _TestConversationService()
    
    # Export API 오버라이드
    import app.api.routes.exports as exports_module
    def _dummy_export_task(*args, **kwargs):
        return {"task_id": "test-task-123"}
    exports_module.create_export = _dummy_export_task
    
    # MemoryService와 RAGService 오버라이드
    from app.api.dependencies import get_memory_service, get_rag_service
    from app.services.cache_service import CacheService
    from app.services.cache_service import get_cache_service as dep_get_cache_service
    class _DummyMemoryService:
        async def get_user_profile(self, *args, **kwargs):
            return None
        async def get_user_facts(self, *args, **kwargs):
            return []
        async def get_context(self, *args, **kwargs):
            return None
        async def build_hierarchical_context_blocks(self, *args, **kwargs):
            return []
        def get_memory_service(self, *args, **kwargs):
            return self
    
    class _DummyRAGService:
        def get_rag_service(self, *args, **kwargs):
            return self
        async def generate_rag_response(self, *args, **kwargs):
            return "Test AI response"
    
    app.dependency_overrides[get_memory_service] = lambda: _DummyMemoryService()
    app.dependency_overrides[get_rag_service] = lambda: _DummyRAGService()

    async def _fake_cache_service():
        return CacheService(redis_client=None)

    app.dependency_overrides[dep_get_cache_service] = _fake_cache_service
    
    # Celery 설정을 테스트 모드로
    from celery import current_app
    current_app.conf.task_always_eager = True
    current_app.conf.result_backend = None
    current_app.conf.broker_url = None
    
    return client

# 테스트 실행 전후 정리
@pytest.fixture(autouse=True, scope="function")
def cleanup_test_data(isolated_test_env):
    """각 테스트 후 데이터를 정리합니다."""
    yield  # 테스트 실행
    
    # 테스트 후 데이터 정리 (필요한 경우)
    try:
        import psycopg2
        conn = psycopg2.connect(isolated_test_env['database_url'])
        cursor = conn.cursor()
        
        # 모든 테스트 데이터 정리
        cursor.execute("""
            TRUNCATE TABLE 
                attachments,
                conversation_messages,
                conversation_threads,
                user_profiles,
                reviews,
                memories,
                messages,
                rooms 
            CASCADE;
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        # 정리 실패는 테스트 실패로 이어지지 않도록 함
        print(f"Warning: Failed to cleanup test data: {e}")

# 테스트 마커 정의
def pytest_configure(config):
    """테스트 마커를 정의합니다."""
    config.addinivalue_line(
        "markers", "isolated: 완전 격리된 환경에서 실행되는 테스트"
    )
    config.addinivalue_line(
        "markers", "integration: 통합 테스트"
    )
    config.addinivalue_line(
        "markers", "unit: 단위 테스트"
    )
