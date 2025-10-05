"""
Configuration loading and validation module.

Handles:
- Loading YAML configuration files
- Environment variable overrides
- Configuration validation
- Providing immutable configuration objects
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class ConfigError(Exception):
    """Exception raised for configuration-related errors."""
    pass


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_yaml_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f) or {}
            return data
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse YAML: {e}")


def apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    # Simple env overrides for top-level keys and known nested ones
    env_map = {
        'LOG_LEVEL': ('log_level',),
        'OUTPUT_FORMAT': ('output_format',),
    }
    for env_key, path in env_map.items():
        if env_key in os.environ and os.environ[env_key]:
            ref = config
            *parents, last = path
            for p in parents:
                ref = ref.setdefault(p, {})
            ref[last] = os.environ[env_key]
    return config


def validate_config(config: Dict[str, Any]) -> None:
    """Validate configuration file structure and values."""
    # Translator section
    if 'translator' not in config:
        raise ConfigError("'translator' section missing in config")

    provider = config['translator'].get('provider')
    if provider not in ('ollama', 'llama_cpp', 'openai', 'anthropic'):
        raise ConfigError(f"Unsupported translator provider: {provider}")

    # Provider-specific validation
    if provider == 'ollama':
        ollama = config['translator'].get('ollama', {})
        if not ollama.get('api_url'):
            raise ConfigError("translator.ollama.api_url required")
        if not ollama.get('model'):
            raise ConfigError("translator.ollama.model required")
        # Validate URL format
        api_url = ollama.get('api_url', '')
        if not api_url.startswith(('http://', 'https://')):
            raise ConfigError(f"Invalid API URL format: {api_url}")

    # Timeout validation
    timeout = config.get('translator', {}).get('timeout', 60)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError(f"translator.timeout must be positive number, got: {timeout}")

    max_retries = config.get('translator', {}).get('max_retries', 3)
    if not isinstance(max_retries, int) or max_retries < 0:
        raise ConfigError(f"translator.max_retries must be non-negative integer, got: {max_retries}")

    # Journal section validation
    if 'journals' in config:
        request_delay = config['journals'].get('request_delay', 1)
        if not isinstance(request_delay, (int, float)) or request_delay < 0:
            raise ConfigError(f"journals.request_delay must be non-negative number, got: {request_delay}")

        journal_timeout = config['journals'].get('timeout', 30)
        if not isinstance(journal_timeout, (int, float)) or journal_timeout <= 0:
            raise ConfigError(f"journals.timeout must be positive number, got: {journal_timeout}")

    # Progress section validation
    if 'progress' in config:
        backup_count = config['progress'].get('backup_count', 5)
        if not isinstance(backup_count, int) or backup_count < 0:
            raise ConfigError(f"progress.backup_count must be non-negative integer, got: {backup_count}")

        retention_days = config['progress'].get('retention_days', 90)
        if not isinstance(retention_days, int) or retention_days < 0:
            raise ConfigError(f"progress.retention_days must be non-negative integer, got: {retention_days}")

    # Output format validation
    output_format = config.get('output_format', 'html')
    if output_format not in ('html', 'md', 'json'):
        raise ConfigError(f"Invalid output_format: {output_format}. Must be html, md, or json")


@dataclass(frozen=True)
class AppConfig:
    data: Dict[str, Any] = field(default_factory=dict)

    def get(self, *path: str, default: Optional[Any] = None) -> Any:
        ref: Any = self.data
        for p in path:
            if not isinstance(ref, dict) or p not in ref:
                return default
            ref = ref[p]
        return ref


def load_config(explicit_path: Optional[str] = None) -> AppConfig:
    path = explicit_path or os.environ.get('CONFIG_PATH') or 'config.yaml'
    base = load_yaml_config(path)
    base = apply_env_overrides(base)
    validate_config(base)
    return AppConfig(data=base)
