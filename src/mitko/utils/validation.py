"""Validation utilities for multi-role support"""

from typing import Any


class ProfileValidationError(ValueError):
    """Raised when profile data is invalid"""
    pass


def validate_profile_roles(profile_data: dict[str, Any]) -> None:
    """
    Validate that profile has at least one valid role.

    Args:
        profile_data: Dictionary with is_seeker and/or is_provider fields

    Raises:
        ProfileValidationError: If no valid role is set
    """
    is_seeker = profile_data.get("is_seeker", False)
    is_provider = profile_data.get("is_provider", False)

    if not isinstance(is_seeker, bool):
        raise ProfileValidationError(f"is_seeker must be boolean, got {type(is_seeker).__name__}")

    if not isinstance(is_provider, bool):
        raise ProfileValidationError(f"is_provider must be boolean, got {type(is_provider).__name__}")

    if not (is_seeker or is_provider):
        raise ProfileValidationError("Profile must have at least one role enabled")
