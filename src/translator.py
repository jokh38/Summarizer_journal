"""
Translation module providing abstraction for multiple LLM providers.

This module defines a base translator interface and concrete implementations
for various LLM services (Ollama, llama.cpp, OpenAI, etc.).
"""

import time
import logging
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TranslationError(Exception):
    """Exception raised for translation-related errors."""
    pass

class BaseTranslator(ABC):
    """
    Abstract base class for all translators.

    Provides common retry logic and error handling for translation operations.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize translator with configuration.

        Args:
            config: Translator configuration dictionary containing provider
                   settings, retry parameters, and timeouts.
        """
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 2)
        self.session = requests.Session()  # Reuse HTTP session for efficiency

    @abstractmethod
    def translate(self, title: str, abstract: str) -> Dict[str, str]:
        """
        Translate paper title and abstract to Korean.

        Args:
            title: Paper title in English
            abstract: Paper abstract in English

        Returns:
            Dictionary with 'english_abstract' and 'korean_summary' keys
        """
        pass

    def _retry_loop(self, func):
        """
        Execute a function with exponential backoff retry logic.

        Args:
            func: Callable to execute with retries

        Returns:
            Result from successful function execution

        Raises:
            Exception: If all retries are exhausted
        """
        attempt = 0
        while True:
            try:
                return func()
            except Exception as e:
                attempt += 1
                if attempt > self.max_retries:
                    logger.error(f"Translation failed after {attempt} attempts: {e}")
                    raise
                sleep_time = min(self.retry_delay * (2 ** (attempt - 1)), 60)
                logger.warning(f"Translate retry {attempt}/{self.max_retries} in {sleep_time}s due to error: {e}")
                time.sleep(sleep_time)

class OllamaTranslator(BaseTranslator):
    """
    Translator implementation using Ollama API.

    Ollama is a local LLM server that supports various open-source models.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama translator.

        Args:
            config: Configuration containing Ollama-specific settings

        Raises:
            TranslationError: If required configuration is missing
        """
        super().__init__(config)
        self.api_url = config.get('ollama', {}).get('api_url')
        self.model = config.get('ollama', {}).get('model')
        self.num_ctx = config.get('ollama', {}).get('num_ctx', 4096)
        self.temperature = config.get('ollama', {}).get('temperature', 0.6)
        self.num_predict = config.get('ollama', {}).get('num_predict', 2048)
        if not self.api_url or not self.model:
            raise TranslationError("Ollama api_url and model required")

    def translate(self, title: str, abstract: str) -> Dict[str, str]:
        """
        Translate using Ollama API.

        Args:
            title: Paper title
            abstract: Paper abstract

        Returns:
            Dictionary with original abstract and Korean translation
        """
        prompt = (
            "다음 논문의 제목과 초록을 한국어로 요약해줘. "
            "논문의 핵심 내용과 중요한 발견을 모두 포함하도록 자연스럽게 요약할 것:\n\n"
            f"제목: {title}\n\n초록: {abstract}"
        )

        def do_request():
            payload = {
                'model': self.model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'num_ctx': self.num_ctx,
                    'num_predict': self.num_predict,
                    'temperature': self.temperature,
                    'reset': True
                }
            }
            # Use session for connection pooling
            resp = self.session.post(self.api_url, json=payload, timeout=self.config.get('timeout', 60))
            if resp.status_code != 200:
                raise TranslationError(f"Ollama error {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            return {
                'english_abstract': abstract,
                'korean_summary': data.get('response', '요약 실패')
            }

        try:
            return self._retry_loop(do_request)
        except Exception:
            # Fallback: naive truncation
            logger.error(f"Translation failed for '{title[:50]}...', using fallback")
            return {
                'english_abstract': abstract,
                'korean_summary': (abstract[:300] + '...') if len(abstract) > 300 else abstract
            }


def build_translator(app_config) -> BaseTranslator:
    """
    Factory function to create translator instances based on configuration.

    Args:
        app_config: Application configuration object

    Returns:
        Translator instance for the configured provider

    Raises:
        TranslationError: If provider is not supported or not implemented
    """
    tcfg = app_config.get('translator') or {}
    provider = tcfg.get('provider')
    if provider == 'ollama':
        return OllamaTranslator(tcfg)
    raise TranslationError(f"Provider not implemented: {provider}")
