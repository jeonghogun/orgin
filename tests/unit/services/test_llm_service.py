import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import LLMService, OpenAIProvider, GeminiProvider, ClaudeProvider
from app.config.settings import settings

class TestOpenAIProvider:
    """Test OpenAI provider implementation"""

    @pytest.mark.asyncio
    async def test_invoke_success(self):
        """Test successful LLM invocation"""
        mock_client = MagicMock()
        mock_response = AsyncMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage.total_tokens = 100
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        provider = OpenAIProvider(client=mock_client)
        content, metrics = await provider.invoke("gpt-4o", "system", "user", "req-123")

        assert content == "Test response"
        assert metrics["total_tokens"] == 100

    @pytest.mark.asyncio
    async def test_invoke_with_json_format(self):
        """Test LLM invocation with JSON response format"""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock()

        provider = OpenAIProvider(client=mock_client)
        await provider.invoke("gpt-4o", "system", "user", "req-123", response_format="json")

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_invoke_api_error(self):
        """Test LLM invocation with API error"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        provider = OpenAIProvider(client=mock_client)
        with pytest.raises(Exception, match="API Error"):
            await provider.invoke("gpt-4o", "system", "user", "req-123")

    def test_init_without_api_key(self, monkeypatch):
        """Test real initialization without API key"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        with pytest.raises(ValueError, match="OpenAI API key is not configured"):
            OpenAIProvider()

class TestGeminiProvider:
    @pytest.mark.asyncio
    @patch("google.generativeai.GenerativeModel")
    async def test_invoke_success(self, mock_genai_model, monkeypatch):
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-api-key")
        mock_model_instance = mock_genai_model.return_value
        mock_model_instance.generate_content_async.return_value.text = "Gemini response"

        provider = GeminiProvider()
        # We need to patch the instance's model attribute after it's created
        provider.model = mock_model_instance
        content, _ = await provider.invoke("gemini-pro", "system", "user", "req-123")
        assert content == "Gemini response"

class TestClaudeProvider:
    @pytest.mark.asyncio
    @patch("anthropic.AsyncAnthropic")
    async def test_invoke_success(self, mock_anthropic_class, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-api-key")
        mock_client_instance = mock_anthropic_class.return_value
        mock_response = AsyncMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Claude response"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_client_instance.messages.create.return_value = mock_response

        provider = ClaudeProvider()
        content, metrics = await provider.invoke("claude-3", "system", "user", "req-123")
        assert content == "Claude response"
        assert metrics["total_tokens"] == 30

class TestLLMService:
    """Test main LLM service orchestrator"""

    @pytest.fixture
    def service(self):
        return LLMService()

    @patch("app.services.llm_service.OpenAIProvider")
    @patch("app.services.llm_service.GeminiProvider")
    @patch("app.services.llm_service.ClaudeProvider")
    def test_initialize_all_providers(self, mock_claude, mock_gemini, mock_openai, monkeypatch, service):
        """Test that all providers are initialized when all keys are present."""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "key")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "key")
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "key")

        service._initialize_providers()
        assert "openai" in service.providers
        assert "gemini" in service.providers
        assert "claude" in service.providers
        assert mock_openai.called
        assert mock_gemini.called
        assert mock_claude.called

    def test_initialize_no_providers(self, monkeypatch, service):
        """Test that no providers are initialized when no keys are present."""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
        monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

        service._initialize_providers()
        assert service.providers == {}
