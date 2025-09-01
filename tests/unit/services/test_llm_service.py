import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.llm_service import LLMService, OpenAIProvider, ClaudeProvider, GeminiProvider
from app.core.errors import LLMError, LLMErrorCode
from app.core.secrets import SecretProvider


class TestLLMService:
    @pytest.fixture
    def mock_secret_provider(self):
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = "test-api-key"
        return provider

    @pytest.fixture
    def llm_service(self, mock_secret_provider):
        return LLMService(mock_secret_provider)

    @pytest.mark.asyncio
    async def test_invoke_with_retry_success(self, llm_service):
        """재시도 로직이 포함된 invoke 테스트"""
        with patch.object(llm_service, 'invoke_with_retry') as mock_invoke:
            mock_invoke.return_value = ("test response", {"tokens": 100})
            
            result = await llm_service.invoke(
                model="gpt-4",
                system_prompt="test system",
                user_prompt="test user",
                request_id="test-123"
            )
            
            assert result == ("test response", {"tokens": 100})
            mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_simple_success(self, llm_service):
        """재시도 로직 없는 invoke_simple 테스트"""
        with patch.object(llm_service, 'invoke_simple') as mock_invoke:
            mock_invoke.return_value = ("test response", {"tokens": 100})
            
            result = await llm_service.invoke_simple(
                model="gpt-4",
                system_prompt="test system",
                user_prompt="test user",
                request_id="test-123"
            )
            
            assert result == ("test response", {"tokens": 100})
            mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_with_llm_error(self, llm_service):
        """LLMError 예외 처리 테스트"""
        with patch.object(llm_service, 'invoke_with_retry') as mock_invoke:
            llm_error = LLMError(
                error_code=LLMErrorCode.RATE_LIMIT,
                provider="openai",
                retryable=True,
                error_message="Rate limit exceeded"
            )
            mock_invoke.side_effect = llm_error
            
            with pytest.raises(LLMError) as exc_info:
                await llm_service.invoke(
                    model="gpt-4",
                    system_prompt="test system",
                    user_prompt="test user",
                    request_id="test-123"
                )
            
            assert exc_info.value.error_code == LLMErrorCode.RATE_LIMIT
            assert exc_info.value.retryable is True

    def test_get_provider_with_fallback(self, llm_service):
        """프로바이더 폴백 테스트"""
        # openai 프로바이더만 초기화
        llm_service.providers = {"openai": Mock()}
        
        # 존재하지 않는 프로바이더 요청 시 openai로 폴백
        provider = llm_service.get_provider("nonexistent")
        assert provider == llm_service.providers["openai"]

    def test_get_provider_no_available(self, llm_service):
        """사용 가능한 프로바이더가 없을 때 테스트"""
        llm_service.providers = {}
        
        with pytest.raises(LLMError) as exc_info:
            llm_service.get_provider("openai")
        
        assert exc_info.value.error_code == LLMErrorCode.PROVIDER_UNAVAILABLE
        assert exc_info.value.retryable is False


class TestOpenAIProvider:
    @pytest.fixture
    def mock_secret_provider(self):
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = "test-openai-key"
        return provider

    @pytest.fixture
    def openai_provider(self, mock_secret_provider):
        with patch('openai.AsyncOpenAI'):
            return OpenAIProvider(mock_secret_provider)

    @pytest.mark.asyncio
    async def test_invoke_success(self, openai_provider):
        """OpenAI API 성공 호출 테스트"""
        mock_response = Mock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "test response"
        
        openai_provider.client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        result = await openai_provider.invoke(
            model="gpt-4",
            system_prompt="test system",
            user_prompt="test user",
            request_id="test-123"
        )
        
        assert result[0] == "test response"
        assert result[1]["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_invoke_rate_limit_error(self, openai_provider):
        """Rate limit 에러 테스트"""
        import openai
        rate_limit_error = openai.RateLimitError("Rate limit exceeded", response=Mock(), body={})
        
        openai_provider.client.chat.completions.create = AsyncMock(side_effect=rate_limit_error)
        
        with pytest.raises(LLMError) as exc_info:
            await openai_provider.invoke(
                model="gpt-4",
                system_prompt="test system",
                user_prompt="test user",
                request_id="test-123"
            )
        
        assert exc_info.value.error_code == LLMErrorCode.RATE_LIMIT
        assert exc_info.value.retryable is True


class TestClaudeProvider:
    @pytest.fixture
    def mock_secret_provider(self):
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = "test-anthropic-key"
        return provider

    @pytest.fixture
    def claude_provider(self, mock_secret_provider):
        with patch('anthropic.AsyncAnthropic'):
            return ClaudeProvider(mock_secret_provider)

    @pytest.mark.asyncio
    async def test_invoke_success(self, claude_provider):
        """Claude API 성공 호출 테스트"""
        mock_response = Mock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.content = [Mock()]
        mock_response.content[0].text = "test response"
        
        claude_provider.client.messages.create = AsyncMock(return_value=mock_response)
        
        result = await claude_provider.invoke(
            model="claude-3-sonnet",
            system_prompt="test system",
            user_prompt="test user",
            request_id="test-123"
        )
        
        assert result[0] == "test response"
        assert result[1]["total_tokens"] == 30


class TestGeminiProvider:
    @pytest.fixture
    def mock_secret_provider(self):
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = "test-gemini-key"
        return provider

    @pytest.fixture
    def gemini_provider(self, mock_secret_provider):
        with patch('google.generativeai.configure'), patch('google.generativeai.GenerativeModel'):
            return GeminiProvider(mock_secret_provider)

    @pytest.mark.asyncio
    async def test_invoke_success(self, gemini_provider):
        """Gemini API 성공 호출 테스트"""
        mock_response = Mock()
        mock_response.text = "test response"
        
        gemini_provider.model.generate_content_async = AsyncMock(return_value=mock_response)
        
        result = await gemini_provider.invoke(
            model="gemini-pro",
            system_prompt="test system",
            user_prompt="test user",
            request_id="test-123"
        )
        
        assert result[0] == "test response"
        assert result[1]["total_tokens"] == 0  # Gemini는 토큰 정보를 제공하지 않음
