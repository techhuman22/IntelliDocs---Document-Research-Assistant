"""
Unit tests for security utilities — JWT lifecycle and password hashing.

These tests do not touch the database or Redis.
They are pure function tests that run in milliseconds.
"""

import time
import uuid
from datetime import timedelta

import pytest
from jose import jwt

from app.config.settings import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_jti,
    refresh_token_redis_key,
    verify_password,
)
from app.core.exceptions import InvalidTokenException, TokenExpiredException


# ── Password Hashing ──────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("MyStr0ng!Pass")
        assert hashed != "MyStr0ng!Pass"
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_correct_password_verifies(self):
        hashed = hash_password("MyStr0ng!Pass")
        assert verify_password("MyStr0ng!Pass", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("MyStr0ng!Pass")
        assert verify_password("WrongPass1!", hashed) is False

    def test_verify_with_invalid_hash_returns_false(self):
        # Should not raise — must return False for safety
        assert verify_password("anything", "not-a-valid-hash") is False

    def test_same_password_produces_different_hashes(self):
        # bcrypt uses random salt — each hash is unique
        h1 = hash_password("MyStr0ng!Pass")
        h2 = hash_password("MyStr0ng!Pass")
        assert h1 != h2
        # But both should verify
        assert verify_password("MyStr0ng!Pass", h1)
        assert verify_password("MyStr0ng!Pass", h2)


# ── Access Token ──────────────────────────────────────────────────────────────

class TestAccessToken:
    def test_creates_valid_jwt(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # header.payload.signature

    def test_payload_contains_correct_claims(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_decode_valid_access_token(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == user_id

    def test_wrong_type_raises_invalid_token(self):
        user_id = str(uuid.uuid4())
        access_token = create_access_token(user_id)
        # Try to use an access token where a refresh token is expected
        with pytest.raises(InvalidTokenException):
            decode_token(access_token, expected_type="refresh")

    def test_tampered_token_raises_invalid_token(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(InvalidTokenException):
            decode_token(tampered, expected_type="access")


# ── Refresh Token ─────────────────────────────────────────────────────────────

class TestRefreshToken:
    def test_returns_token_and_jti(self):
        user_id = str(uuid.uuid4())
        token, jti = create_refresh_token(user_id)
        assert isinstance(token, str)
        assert isinstance(jti, str)
        assert len(jti) == 36  # UUID format

    def test_jti_in_payload(self):
        user_id = str(uuid.uuid4())
        token, jti = create_refresh_token(user_id)
        payload = decode_token(token, expected_type="refresh")
        assert payload["jti"] == jti

    def test_type_is_refresh(self):
        user_id = str(uuid.uuid4())
        token, _ = create_refresh_token(user_id)
        payload = decode_token(token, expected_type="refresh")
        assert payload["type"] == "refresh"

    def test_refresh_cannot_be_used_as_access(self):
        user_id = str(uuid.uuid4())
        token, _ = create_refresh_token(user_id)
        with pytest.raises(InvalidTokenException):
            decode_token(token, expected_type="access")


# ── JTI Hashing ──────────────────────────────────────────────────────────────

class TestJTIHashing:
    def test_same_jti_produces_same_hash(self):
        jti = str(uuid.uuid4())
        assert hash_jti(jti) == hash_jti(jti)

    def test_different_jtis_produce_different_hashes(self):
        assert hash_jti(str(uuid.uuid4())) != hash_jti(str(uuid.uuid4()))

    def test_hash_is_64_hex_chars(self):
        h = hash_jti(str(uuid.uuid4()))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_redis_key_format(self):
        jti = "test-jti-value"
        key = refresh_token_redis_key(jti)
        assert key == f"refresh_token:{jti}"


# ── Password Schema Validation ────────────────────────────────────────────────

class TestPasswordStrengthValidation:
    """Test the schema-level password validator."""

    from app.schemas.auth import validate_password_strength

    @pytest.mark.parametrize("password,should_raise", [
        ("MyStr0ng!Pass", False),
        ("short1!A",      False),   # exactly 8 chars — valid
        ("short",         True),    # too short
        ("alllowercase1!", True),   # no uppercase
        ("ALLUPPERCASE1!", True),   # no lowercase
        ("NoDigitsHere!",  True),   # no digit
        ("NoSpecial123",   True),   # no special char
    ])
    def test_password_strength(self, password: str, should_raise: bool):
        from app.schemas.auth import validate_password_strength
        if should_raise:
            with pytest.raises(ValueError):
                validate_password_strength(password)
        else:
            result = validate_password_strength(password)
            assert result == password
