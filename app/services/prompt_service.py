"""
Service for loading and formatting prompts from a central YAML file.
"""
import os
import logging
import yaml
from typing import Dict, Any, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

PROMPTS_FILE = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'prompts.yml')

class PromptService:
    """
    Loads, caches, and formats prompt templates from a central YAML file.
    Supports versioning and default versions for A/B testing.
    """

    @lru_cache(maxsize=1)
    def _load_all_prompts(self) -> Dict[str, Any]:
        """
        Loads the entire YAML file into a dictionary.
        Uses lru_cache to ensure the file is read from disk only once.
        """
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Prompts YAML file not found at {PROMPTS_FILE}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing prompts YAML file at {PROMPTS_FILE}: {e}")
            raise

    def get_prompt(self, name: str, version: Optional[str] = None, **kwargs: Any) -> str:
        """
        Gets a specific version of a prompt template, formats it, and returns it.

        Args:
            name: The top-level key for the prompt (e.g., 'review_initial_analysis').
            version: The specific version to use (e.g., 'v1', 'v2_experimental').
                     If None, the 'default_version' for that prompt is used.
            **kwargs: Keyword arguments to format the template string.

        Returns:
            The formatted prompt string.
        """
        all_prompts = self._load_all_prompts()

        prompt_config = all_prompts.get(name)
        if not prompt_config:
            raise ValueError(f"Prompt '{name}' not found in prompts.yml")

        if version is None:
            version = prompt_config.get('default_version')
            if not version:
                raise ValueError(f"Prompt '{name}' does not have a default_version defined.")

        template = prompt_config.get('versions', {}).get(version, {}).get('template')
        if not template:
            raise ValueError(f"Version '{version}' for prompt '{name}' not found or has no template.")

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing keyword argument for prompt '{name}' (version: {version}): {e}")
            raise ValueError(f"Missing data for prompt '{name}': {e}")


# Singleton instance for easy access throughout the application
prompt_service = PromptService()
