import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import LLMService, OpenAIProvider
from app.config.settings import settings

class TestOpenAIProvider:
    """Test OpenAI provider implementation"""

    @pytest.mark.asyncio
    async def test_invoke_success(self, monkeypatch):
        """Test successful LLM invocation"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-api-key")
        provider = OpenAIProvider()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await provider.invoke("gpt-4o", "system", "user", "req-123")
        assert result["content"] == "Test response"

    @pytest.mark.asyncio
    async def test_invoke_with_json_format(self, monkeypatch):
        """Test LLM invocation with JSON response format"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-api-key")
        provider = OpenAIProvider()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"key": "value"}'
        provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await provider.invoke("gpt-4o", "system", "user", "req-123", response_format="json")
        call_args = provider.client.chat.completions.create.call_args
        assert call_args[1]["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_invoke_api_error(self, monkeypatch):
        """Test LLM invocation with API error"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-api-key")
        provider = OpenAIProvider()
        provider.client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
        with pytest.raises(Exception, match="API Error"):
            await provider.invoke("gpt-4o", "system", "user", "req-123")

    def test_init_without_api_key(self, monkeypatch):
        """Test initialization without API key"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        with pytest.raises(ValueError, match="OpenAI API key is not configured"):
            OpenAIProvider()

class TestLLMService:
    """Test main LLM service orchestrator"""

    @pytest.fixture
    def service(self):
        return LLMService()

    @patch("app.services.llm_service.OpenAIProvider")
    def test_initialize_providers_success(self, mock_provider_class, monkeypatch, service):
        """Test successful provider initialization"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-api-key")
        mock_provider = MagicMock()
        mock_provider_class.return_value = mock_provider
        service._initialize_providers()
        assert service._initialized is True
        assert "openai" in service.providers

    def test_initialize_providers_no_api_key(self, monkeypatch, service):
        """Test provider initialization without API key"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        service._initialize_providers()
        assert service._initialized is True
        assert service.providers == {}

    @patch("app.services.llm_service.OpenAIProvider")
    def test_get_provider_success(self, mock_provider_class, monkeypatch, service):
        """Test getting provider successfully"""
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-api-key")
        mock_provider = MagicMock()
        mock_provider_class.return_value = mock_provider
        provider = service.get_provider("openai")
        assert provider == mock_provider

    def test_get_provider_not_found(self, service):
        """Test getting non-existent provider"""
        service._initialized = True
        with pytest.raises(ValueError, match="Unsupported provider: unknown"):
            service.get_provider("unknown")
