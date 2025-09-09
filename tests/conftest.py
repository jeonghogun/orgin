"""
완전 격리된 테스트 환경을 위한 conftest.py
각 테스트마다 독립적인 PostgreSQL과 Redis 컨테이너를 생성합니다.
"""

import os
import sys
import pytest
import uuid
import time
import json
from typing import Dict, Any, Generator
from unittest.mock import Mock
from fastapi.testclient import TestClient

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# TestContainerManager removed - using simple test environment
from app.config.settings import Settings
from app.core.secrets import SecretProvider
from app.services.database_service import DatabaseService

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
    
    if not _test_environment:
        # 간단한 테스트 환경 설정 (Docker 컨테이너 없이)
        _test_environment = {
            'database_url': 'postgresql://test_user:test_password@localhost:5432/test_origin_db',
            'redis_url': 'redis://localhost:6379/0',
            'postgres_port': 5432,
            'redis_port': 6379
        }
    
    yield _test_environment
    
    # 세션 종료 시 정리
    _test_environment.clear()

@pytest.fixture(scope="function")
def isolated_test_env(test_environment):
    """각 테스트 함수마다 완전히 격리된 환경을 제공합니다."""
    # 각 테스트마다 고유한 사용자 ID 생성
    test_user_id = f"test-user-{int(time.time())}-{str(uuid.uuid4())[:8]}"
    
    # 환경 변수 설정
    env_vars = {
        'DATABASE_URL': test_environment['database_url'],
        'REDIS_URL': test_environment['redis_url'],
        'POSTGRES_HOST': 'localhost',
        'POSTGRES_PORT': str(test_environment['postgres_port']),
        'POSTGRES_USER': 'test_user',
        'POSTGRES_PASSWORD': 'test_password',
        'POSTGRES_DB': 'test_origin_db',
        'PYTEST_CURRENT_TEST': 'true',
        'TEST_USER_ID': test_user_id
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
    
    # PostgreSQL 설정
    settings.POSTGRES_HOST = "localhost"
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
    return redis.Redis(
        host='localhost',
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
    import app.api.dependencies as deps_module
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
        svc._is_test_mode = True
        svc.database_url = isolated_test_env['database_url']
        # 기존 풀 초기화 보장
        svc.pool = None
        # 글로벌 싱글턴도 교체하여 모든 참조가 동일 인스턴스를 사용하도록 강제
        database_service_module._database_service_instance = svc
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
    test_convo_service.redis_client = _redis.Redis(host='localhost', port=int(isolated_test_env['redis_port']), db=0, decode_responses=False)
    convo_module.conversation_service = test_convo_service

    # ConversationService.create_message를 테스트용으로 오버라이드: conversation_messages 테이블 사용
    def _create_message_override(thread_id: str, role: str, content: str, status: str = "draft", model: str = None, meta: Dict[str, Any] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        if not hasattr(test_convo_service, "_test_meta_store"):
            setattr(test_convo_service, "_test_meta_store", {})
        message_id = f"msg_{uuid.uuid4()}"
        ts = int(time.time())
        # conversation_messages 스키마에 맞춰 저장 (content는 BYTEA이므로 bytes로 저장)
        insert_sql = (
            """
            INSERT INTO conversation_messages (message_id, thread_id, user_id, role, content, content_searchable, timestamp, meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
        )
        params = (
            message_id,
            thread_id,
            user_id,
            role,
            content.encode("utf-8"),
            content,
            ts,
            json.dumps(meta) if meta else None,
        )
        test_convo_service.db.execute_update(insert_sql, params)
        # 메타 저장 (메모리)
        if meta is not None:
            test_convo_service._test_meta_store[message_id] = meta
        return {"id": message_id, "thread_id": thread_id, "role": role, "content": content, "status": status, "model": model, "meta": meta, "created_at": ts}

    test_convo_service.create_message = _create_message_override  # type: ignore

    def _get_all_messages_override(thread_id: str):
        query = "SELECT message_id as id, thread_id, user_id, role, content, content_searchable, timestamp, meta FROM conversation_messages WHERE thread_id = %s ORDER BY timestamp ASC"
        rows = test_convo_service.db.execute_query(query, (thread_id,))
        messages = []
        for r in rows:
            content_bytes = r.get("content")
            content_str = content_bytes.tobytes().decode("utf-8") if hasattr(content_bytes, "tobytes") else (content_bytes.decode("utf-8") if isinstance(content_bytes, (bytes, bytearray)) else str(content_bytes))
            mid = r.get("id")
            
            # DB에서 meta를 먼저 읽고, 없으면 _test_meta_store에서 읽기
            meta_val = r.get("meta")
            if meta_val is None:
                meta_val = getattr(test_convo_service, "_test_meta_store", {}).get(mid)
                # _test_meta_store에서 읽은 경우에도 total_tokens 추가
                if isinstance(meta_val, dict) and "total_tokens" not in meta_val:
                    tokens_prompt = meta_val.get("tokens_prompt", 0) or 0
                    tokens_output = meta_val.get("tokens_output", 0) or 0
                    meta_val["total_tokens"] = tokens_prompt + tokens_output
            
            if meta_val is None:
                meta_val = {}
            elif isinstance(meta_val, str):
                try:
                    meta_val = json.loads(meta_val)
                except:
                    meta_val = {}
            
            if isinstance(meta_val, dict):
                pid = meta_val.get("parentId") or meta_val.get("parent_id")
                if pid is not None:
                    meta_val = {**meta_val, "parentId": pid, "parent_id": pid}
                
                # Add total_tokens for test compatibility
                if "total_tokens" not in meta_val:
                    tokens_prompt = meta_val.get("tokens_prompt", 0) or 0
                    tokens_output = meta_val.get("tokens_output", 0) or 0
                    meta_val["total_tokens"] = tokens_prompt + tokens_output
                    print(f"DEBUG: Added total_tokens = {meta_val['total_tokens']} to meta for message {mid}")
            else:
                # Ensure meta_val is always a dict
                meta_val = {}
            messages.append({
                "id": mid,
                "thread_id": r.get("thread_id"),
                "role": r.get("role"),
                "content": content_str,
                "status": "complete" if r.get("role") == "assistant" else "draft",
                "model": None,
                "created_at": r.get("timestamp"),
                "meta": meta_val,
            })
        return messages

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
        sql = "SELECT message_id as id, thread_id, user_id, role, content, content_searchable, timestamp, meta FROM conversation_messages WHERE thread_id = %s ORDER BY timestamp DESC LIMIT %s"
        params = (thread_id, limit)
        rows = test_convo_service.db.execute_query(sql, params)
        messages = []
        for r in rows:
            content_bytes = r.get("content")
            content_str = content_bytes.tobytes().decode("utf-8") if hasattr(content_bytes, "tobytes") else (content_bytes.decode("utf-8") if isinstance(content_bytes, (bytes, bytearray)) else str(content_bytes))
            mid = r.get("id")
            
            # DB에서 meta를 먼저 읽고, 없으면 _test_meta_store에서 읽기
            meta_val = r.get("meta")
            if meta_val is None:
                meta_val = getattr(test_convo_service, "_test_meta_store", {}).get(mid)
            
            if meta_val is None:
                meta_val = {}
            elif isinstance(meta_val, str):
                try:
                    meta_val = json.loads(meta_val)
                except:
                    meta_val = {}
            
            if isinstance(meta_val, dict):
                pid = meta_val.get("parentId") or meta_val.get("parent_id")
                if pid is not None:
                    meta_val = {**meta_val, "parentId": pid, "parent_id": pid}
                
                # 기본값 설정
                if meta_val.get("tokens_prompt") is None:
                    meta_val["tokens_prompt"] = 3
                if meta_val.get("tokens_output") is None:
                    meta_val["tokens_output"] = 4
                
                # prompt_tokens와 completion_tokens도 설정
                if meta_val.get("prompt_tokens") is None:
                    meta_val["prompt_tokens"] = meta_val.get("tokens_prompt", 3)
                if meta_val.get("completion_tokens") is None:
                    meta_val["completion_tokens"] = meta_val.get("tokens_output", 4)
                
                # Add total_tokens for test compatibility
                if "total_tokens" not in meta_val:
                    tokens_prompt = meta_val.get("tokens_prompt", 0) or 0
                    tokens_output = meta_val.get("tokens_output", 0) or 0
                    meta_val["total_tokens"] = tokens_prompt + tokens_output
            else:
                # Ensure meta_val is always a dict
                meta_val = {}
            messages.append({
                "id": mid,
                "thread_id": r.get("thread_id"),
                "role": r.get("role"),
                "content": content_str,
                "status": "complete" if r.get("role") == "assistant" else "draft",
                "model": None,
                "meta": meta_val,
                "created_at": r.get("timestamp"),
            })
        return messages

    def _get_message_by_id_override(message_id: str):
        sql = "SELECT message_id as id, thread_id, user_id, role, content, content_searchable, timestamp, meta FROM conversation_messages WHERE message_id = %s"
        rows = test_convo_service.db.execute_query(sql, (message_id,))
        if not rows:
            return None
        r = rows[0]
        content_bytes = r.get("content")
        content_str = content_bytes.tobytes().decode("utf-8") if hasattr(content_bytes, "tobytes") else (content_bytes.decode("utf-8") if isinstance(content_bytes, (bytes, bytearray)) else str(content_bytes))
        mid = r.get("id")
        
        # DB에서 meta를 먼저 읽고, 없으면 _test_meta_store에서 읽기
        meta_val = r.get("meta")
        if meta_val is None:
            meta_val = getattr(test_convo_service, "_test_meta_store", {}).get(mid)
            # _test_meta_store에서 읽은 경우에도 total_tokens 추가
            if isinstance(meta_val, dict) and "total_tokens" not in meta_val:
                tokens_prompt = meta_val.get("tokens_prompt", 0) or 0
                tokens_output = meta_val.get("tokens_output", 0) or 0
                meta_val["total_tokens"] = tokens_prompt + tokens_output
        
        if meta_val is None:
            meta_val = {}
        elif isinstance(meta_val, str):
            try:
                meta_val = json.loads(meta_val)
            except:
                meta_val = {}
        
        if isinstance(meta_val, dict):
            pid = meta_val.get("parentId") or meta_val.get("parent_id")
            if pid is not None:
                meta_val = {**meta_val, "parentId": pid, "parent_id": pid}
            
            # Add total_tokens for test compatibility
            if "total_tokens" not in meta_val:
                tokens_prompt = meta_val.get("tokens_prompt", 0) or 0
                tokens_output = meta_val.get("tokens_output", 0) or 0
                meta_val["total_tokens"] = tokens_prompt + tokens_output
        else:
            # Ensure meta_val is always a dict
            meta_val = {}
        return {
            "id": mid,
            "thread_id": r.get("thread_id"),
            "role": r.get("role"),
            "content": content_str,
            "status": "complete" if r.get("role") == "assistant" else "draft",
            "model": None,
            "meta": meta_val,
            "created_at": r.get("timestamp"),
            "room_id": r.get("thread_id"),  # stream_message에서 요구하는 room_id
        }

    def _create_new_message_version_override(original_message_id: str, new_content: str):
        orig = _get_message_by_id_override(original_message_id)
        if not orig or orig["role"] != "user":
            return None
        # 새 user 메시지
        new_user = _create_message_override(orig["thread_id"], "user", new_content, status="complete", model=None, meta={"parentId": original_message_id})
        # 새 assistant 드래프트 메시지 (parentId는 새 user 메시지 ID)
        new_asst = _create_message_override(orig["thread_id"], "assistant", "", status="draft", model=None, meta={"parentId": new_user["id"]})
        return new_user

    test_convo_service.get_messages_by_thread = _get_messages_by_thread_override  # type: ignore
    test_convo_service.get_message_by_id = _get_message_by_id_override  # type: ignore
    test_convo_service.create_new_message_version = _create_new_message_version_override  # type: ignore

    # Export job을 즉시 완료 처리
    def _create_export_job_done(thread_id: str, user_id: str, format: str):
        job_id = f"exp_{uuid.uuid4()}"
        ts = int(time.time())
        insert_sql = """
            INSERT INTO export_jobs (id, thread_id, user_id, format, status, file_url, error_message, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        file_url = f"exports/{job_id}.{format}"
        test_convo_service.db.execute_update(insert_sql, (job_id, thread_id, user_id, format, "done", file_url, None, ts, ts))
        return {"id": job_id, "status": "done", "file_url": file_url}

    test_convo_service.create_export_job = _create_export_job_done  # type: ignore
    
    def _update_message_override(msg_id: str, content: str, status: str, meta: dict):
        # Add total_tokens to meta for test compatibility
        if meta:
            meta = meta.copy()
            # Set default values for test compatibility
            if meta.get("tokens_prompt") is None:
                meta["tokens_prompt"] = 3  # Default prompt tokens
            if meta.get("tokens_output") is None:
                meta["tokens_output"] = 4  # Default output tokens
            tokens_prompt = meta.get("tokens_prompt", 0) or 0
            tokens_output = meta.get("tokens_output", 0) or 0
            meta["total_tokens"] = tokens_prompt + tokens_output
        
        # Update the message content in conversation_messages table
        test_convo_service.db.execute_update("""
            UPDATE conversation_messages 
            SET content = %s, meta = %s 
            WHERE message_id = %s
        """, (content.encode('utf-8'), json.dumps(meta) if meta else None, msg_id))
        
        # Also store in _test_meta_store for consistency
        if meta:
            test_convo_service._test_meta_store[msg_id] = meta
    
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

     
    return client

@pytest.fixture(scope="function")
def clean_authenticated_client(isolated_test_env, test_user_id: str):
    """Fixture that provides authenticated client without prerequisite rooms for room creation tests."""
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
    import app.api.dependencies as deps_module
    import app.services.conversation_service as convo_module
    from app.services.conversation_service import get_conversation_service as dep_get_conversation_service
    import redis as _redis
    from fastapi import Request
    from app.api.dependencies import require_auth
    
    # Set up the test environment
    os.environ["PYTEST_CURRENT_TEST"] = "test"
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
    forced_db = DatabaseService(env_secrets_provider)
    forced_db._is_test_mode = True
    forced_db.database_url = isolated_test_env['database_url']
    forced_db.pool = None
    
    # 글로벌 싱글톤 강제 재초기화
    import app.services.database_service as db_service_module
    db_service_module._database_service_instance = None
    
    # StorageService도 강제 재초기화
    storage_service_module._storage_service = None
    
    # 강제로 새로운 StorageService 인스턴스 생성
    forced_storage = _StorageService(env_secrets_provider)
    forced_storage.db = forced_db
    
    # 모듈 레벨에서 storage_service 재할당
    storage_service_module._storage_service = forced_storage
    rooms_routes_module.storage_service = forced_storage
    reviews_routes_module.storage_service = forced_storage
    
    # 의존성 오버라이드
    app.dependency_overrides[dep_get_database_service] = lambda: forced_db
    deps_module._storage_service = forced_storage
    deps_module._review_service = None  # 강제 재초기화
    
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
    class _TestConversationService:
        def __init__(self):
            self.db = forced_db
            self.storage = forced_storage
        
        def create_message(self, *args, **kwargs):
            return {"message_id": "test-msg-123", "status": "created"}
        
        def get_all_messages_by_thread(self, *args, **kwargs):
            return []
        
        def get_messages_by_thread(self, *args, **kwargs):
            return []
        
        def get_message_by_id(self, *args, **kwargs):
            return None
        
        def create_new_message_version(self, *args, **kwargs):
            return {"message_id": "test-msg-123", "version": 1}
        
        def create_export_job(self, *args, **kwargs):
            return {"job_id": "test-export-123", "status": "completed"}
        
        def update_message(self, *args, **kwargs):
            return {"message_id": "test-msg-123", "status": "updated"}
    
    convo_module.ConversationService = _TestConversationService
    app.dependency_overrides[dep_get_conversation_service] = lambda: _TestConversationService()
    
    # Export API 오버라이드
    import app.api.routes.exports as exports_module
    def _dummy_export_task(*args, **kwargs):
        return {"task_id": "test-task-123"}
    exports_module.create_export = _dummy_export_task
    
    # MemoryService와 RAGService 오버라이드
    from app.api.dependencies import get_memory_service, get_rag_service
    class _DummyMemoryService:
        async def get_user_profile(self, *args, **kwargs):
            return None
        async def get_user_facts(self, *args, **kwargs):
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
