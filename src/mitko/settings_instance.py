"""
Global SETTINGS instance for convenience.

IMPORTANT: This file imports SETTINGS at module level, so it should NOT be imported
during Docker build phase. Use get_settings() instead in files that run during build.
"""

from .config import get_settings

SETTINGS = get_settings()
