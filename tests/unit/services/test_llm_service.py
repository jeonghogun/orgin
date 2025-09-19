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
    async def test_invoke_success(self, llm_service):
        """Test that the main async invoke method calls the retry logic."""
        with patch.object(llm_service, 'invoke_with_retry') as mock_invoke_retry:
            mock_invoke_retry.return_value = ("test response", {"tokens": 100})
            
            result = await llm_service.invoke(
                model="gpt-4",
                system_prompt="test system",
                user_prompt="test user",
                request_id="test-123"
            )
            
            assert result == ("test response", {"tokens": 100})
            mock_invoke_retry.assert_called_once()

    def test_invoke_sync_success(self, llm_service):
        """Test that the main sync invoke method calls the sync retry logic."""
        with patch.object(llm_service, 'invoke_with_retry_sync') as mock_invoke_retry_sync:
            mock_invoke_retry_sync.return_value = ("test sync response", {"tokens": 10})
            
            result = llm_service.invoke_sync(
                provider_name="openai",
                model="gpt-4",
                system_prompt="test system",
                user_prompt="test user",
                request_id="test-sync-123"
            )
            
            assert result == ("test sync response", {"tokens": 10})
            mock_invoke_retry_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_with_llm_error(self, llm_service):
        """Test that LLMError exceptions are propagated correctly."""
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

    def test_get_provider_with_fallback(self, llm_service):
        """Test that get_provider falls back to a default if the requested one is unavailable."""
        llm_service.providers = {"openai": Mock()}
        
        provider = llm_service.get_provider("nonexistent_provider")
        assert provider == llm_service.providers["openai"]

    def test_get_provider_no_available(self, mock_secret_provider):
        """Test that an error is raised if no providers can be initialized."""
        # Arrange: mock the secret provider to return no keys
        mock_secret_provider.get.return_value = None
        service_with_no_keys = LLMService(mock_secret_provider)
        
        # Act & Assert
        with pytest.raises(LLMError) as exc_info:
            service_with_no_keys.get_provider("openai")
        
        assert exc_info.value.error_code == LLMErrorCode.PROVIDER_UNAVAILABLE


class TestOpenAIProvider:
    @pytest.fixture
    def mock_secret_provider(self):
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = "test-openai-key"
        return provider

    @pytest.fixture
    def openai_provider(self, mock_secret_provider):
        # We patch the clients to avoid actual instantiation
        with patch('openai.AsyncOpenAI'), patch('openai.OpenAI'):
            return OpenAIProvider(mock_secret_provider)

    @pytest.mark.asyncio
    async def test_invoke_success(self, openai_provider):
        """Test OpenAI async API success call."""
        mock_response = Mock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "test response"
        
        # Fix: mock async_client, not client
        openai_provider.async_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        result = await openai_provider.invoke(
            model="gpt-4", system_prompt="test system", user_prompt="test user", request_id="test-123"
        )
        
        assert result[0] == "test response"
        assert result[1]["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_invoke_rate_limit_error(self, openai_provider):
        """Test OpenAI async rate limit error handling."""
        import openai
        rate_limit_error = openai.RateLimitError("Rate limit exceeded", response=Mock(), body={})
        
        # Fix: mock async_client, not client
        openai_provider.async_client.chat.completions.create = AsyncMock(side_effect=rate_limit_error)
        
        with pytest.raises(LLMError) as exc_info:
            await openai_provider.invoke(
                model="gpt-4", system_prompt="test system", user_prompt="test user", request_id="test-123"
            )
        
        assert exc_info.value.error_code == LLMErrorCode.RATE_LIMIT


class TestClaudeProvider:
    @pytest.fixture
    def mock_secret_provider(self):
        provider = Mock(spec=SecretProvider)
        provider.get.return_value = "test-anthropic-key"
        return provider

    @pytest.fixture
    def claude_provider(self, mock_secret_provider):
        with patch('anthropic.AsyncAnthropic'), patch('anthropic.Anthropic'):
            return ClaudeProvider(mock_secret_provider)

    @pytest.mark.asyncio
    async def test_invoke_success(self, claude_provider):
        """Test Claude async API success call."""
        mock_response = Mock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.content = [Mock()]
        mock_response.content[0].text = "test response"
        
        # Fix: mock async_client, not client
        claude_provider.async_client.messages.create = AsyncMock(return_value=mock_response)
        
        result = await claude_provider.invoke(
            model="claude-3-sonnet", system_prompt="test system", user_prompt="test user", request_id="test-123"
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
        """Test Gemini async API success call."""
        mock_response = Mock()
        mock_response.text = "test response"
        
        mock_model = Mock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        gemini_provider._model_cache["gemini-pro"] = mock_model

        result = await gemini_provider.invoke(
            model="gemini-pro", system_prompt="test system", user_prompt="test user", request_id="test-123"
        )
        
        assert result[0] == "test response"
        assert result[1]["total_tokens"] == 0
