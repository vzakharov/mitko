"""Type-safe internationalization module for Mitko bot"""

from functools import lru_cache

from ..config import SETTINGS
from .base import Locale
from .en import EnglishLocale
from .ru import RussianLocale


# Singleton factory
@lru_cache(maxsize=1)
def get_locale() -> Locale:
    """Get locale instance based on MITKO_LANGUAGE env variable"""
    if SETTINGS.mitko_language == "ru":
        return RussianLocale()
    return EnglishLocale()


# Singleton instance - short name for convenience
L = get_locale()

__all__ = ["Locale", "EnglishLocale", "RussianLocale", "get_locale", "L"]
