"""
Service for managing LLM provider strategies from a configuration file.
"""
import yaml
import logging
from typing import List, Optional, Dict, Any
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

# Singleton instance for easy access
llm_strategy_service = LLMStrategyService()
