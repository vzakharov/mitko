"""Tests for multi-role support"""

from typing import Any

import pytest

from src.mitko.utils.validation import (
    ProfileValidationError,
    validate_profile_roles,
)


class TestRoleValidation:
    """Test role validation logic"""

    def test_valid_seeker_only(self):
        """Test valid profile with only seeker role"""
        data = {"is_seeker": True, "is_provider": False}
        validate_profile_roles(data)  # Should not raise

    def test_valid_provider_only(self):
        """Test valid profile with only provider role"""
        data = {"is_seeker": False, "is_provider": True}
        validate_profile_roles(data)  # Should not raise

    def test_valid_both_roles(self):
        """Test valid profile with both roles enabled"""
        data = {"is_seeker": True, "is_provider": True}
        validate_profile_roles(data)  # Should not raise

    def test_invalid_no_roles(self):
        """Test that profile with no roles raises error"""
        data = {"is_seeker": False, "is_provider": False}
        with pytest.raises(ProfileValidationError, match="at least one role"):
            validate_profile_roles(data)

    def test_invalid_is_seeker_type(self):
        """Test that non-boolean is_seeker raises error"""
        data = {"is_seeker": "yes", "is_provider": True}
        with pytest.raises(
            ProfileValidationError, match="is_seeker must be boolean"
        ):
            validate_profile_roles(data)

    def test_invalid_is_provider_type(self):
        """Test that non-boolean is_provider raises error"""
        data = {"is_seeker": True, "is_provider": "no"}
        with pytest.raises(
            ProfileValidationError, match="is_provider must be boolean"
        ):
            validate_profile_roles(data)

    def test_missing_fields_default_to_false(self):
        """Test that missing role fields default to False and raise error"""
        data = dict[str, Any]()
        with pytest.raises(ProfileValidationError, match="at least one role"):
            validate_profile_roles(data)


# TODO: Add integration tests for MatcherService with dual-role users
# These would require async test fixtures and database setup
# Example tests to implement:
# - test_seeker_finds_provider()
# - test_dual_role_user_matches_as_seeker()
# - test_dual_role_user_matched_by_seekers()
# - test_provider_only_not_in_seeker_query()
