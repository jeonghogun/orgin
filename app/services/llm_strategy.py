"""
Service for managing LLM provider strategies from a configuration file.
"""
import yaml
import logging
from typing import Iterable, List, Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

CONFIG_PATH = "config/providers.yml"

class ProviderPanelistConfig(BaseModel):
    """Pydantic model for a single panelist's configuration from providers.yml."""
    provider: str
    persona: str
    model: str
    system_prompt: Optional[str] = None
    timeout_s: int = Field(60, gt=0)
    max_retries: int = Field(2, ge=0)

class StrategyConfig(BaseModel):
    """Pydantic model for the entire provider strategy configuration."""
    panelists: List[ProviderPanelistConfig]


class LLMStrategyService:
    """
    Loads, validates, and provides access to the LLM provider strategy.
    """
    def __init__(self, config_path: str = CONFIG_PATH):
        self._config: Optional[StrategyConfig] = None
        self._load_config(config_path)

    def _load_config(self, config_path: str):
        """Loads and validates the provider configuration from a YAML file."""
        try:
            with open(config_path, "r") as f:
                raw_config = yaml.safe_load(f)
            self._config = StrategyConfig(**raw_config)
            logger.info(f"Successfully loaded and validated LLM provider strategy from {config_path}")
        except FileNotFoundError:
            logger.error(f"Provider config file not found at {config_path}. Using empty defaults.")
            self._config = StrategyConfig(panelists=[])
        except ValidationError as e:
            logger.error(f"Invalid provider config file at {config_path}: {e}")
            raise ValueError(f"Invalid provider config: {e}")
        except Exception as e:
            logger.error(f"Error loading provider config file at {config_path}: {e}")
            raise

    def get_default_panelists(self) -> List[ProviderPanelistConfig]:
        """Returns the default list of panelist configurations."""
        if not self._config:
            return []
        return self._config.panelists

    def _build_mock_panelists(self) -> List[ProviderPanelistConfig]:
        """Return deterministic mock panelists when only the mock provider is available."""

        return [
            ProviderPanelistConfig(
                provider="mock",
                persona="GPT-4o (모의 패널)",
                model="mock-conversation",
                system_prompt=(
                    "분석가의 시선으로 핵심 수치를 짚고 실행 플랜을 제안합니다."
                ),
                timeout_s=30,
                max_retries=0,
            ),
            ProviderPanelistConfig(
                provider="mock",
                persona="Claude 3 Haiku (모의 패널)",
                model="mock-conversation",
                system_prompt=(
                    "리스크와 거버넌스를 중시하며 균형감을 갖춘 조언을 제공합니다."
                ),
                timeout_s=30,
                max_retries=0,
            ),
            ProviderPanelistConfig(
                provider="mock",
                persona="Gemini 1.5 Flash (모의 패널)",
                model="mock-conversation",
                system_prompt=(
                    "확장 가능성과 실험을 강조하며 낙관적 관점을 유지합니다."
                ),
                timeout_s=30,
                max_retries=0,
            ),
        ]

    def get_panelists_for_providers(
        self, provider_names: Iterable[str]
    ) -> List[ProviderPanelistConfig]:
        """Return panelist configs filtered to the requested providers.

        If no default configuration matches but the deterministic mock provider is
        available, we synthesise a trio of mock panelists so that the rest of the
        review pipeline can proceed without falling back to a scripted transcript.
        """

        provider_list = [name for name in provider_names if name]
        if not provider_list:
            return self.get_default_panelists()

        provider_set = {name.strip().lower() for name in provider_list if name}
        if not provider_set:
            return []

        base_configs = self.get_default_panelists()
        matched = [config for config in base_configs if config.provider in provider_set]
        if matched:
            return matched

        if "mock" in provider_set:
            return self._build_mock_panelists()

        return []

# Singleton instance for easy access
llm_strategy_service = LLMStrategyService()
