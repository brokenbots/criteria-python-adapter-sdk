"""Tests for handshake validation."""

import os
import sys
from unittest.mock import patch

import pytest

from criteria_adapter_sdk.plugin.handshake import (
    MAGIC_COOKIE_KEY,
    MAGIC_COOKIE_VALUE,
    is_plugin_invocation,
    validate_and_exit_on_failure,
    validate_handshake,
)


class TestValidateHandshake:
    def test_missing_cookie_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="Missing"):
                validate_handshake()

    def test_invalid_cookie_raises(self):
        with patch.dict(os.environ, {MAGIC_COOKIE_KEY: "wrong"}):
            with pytest.raises(RuntimeError, match="Invalid"):
                validate_handshake()

    def test_valid_cookie_returns_true(self):
        with patch.dict(os.environ, {MAGIC_COOKIE_KEY: MAGIC_COOKIE_VALUE}):
            assert validate_handshake() is True


class TestIsPluginInvocation:
    def test_no_cookie_returns_false(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_plugin_invocation() is False

    def test_invalid_cookie_returns_false(self):
        with patch.dict(os.environ, {MAGIC_COOKIE_KEY: "wrong"}):
            assert is_plugin_invocation() is False

    def test_valid_cookie_returns_true(self):
        with patch.dict(os.environ, {MAGIC_COOKIE_KEY: MAGIC_COOKIE_VALUE}):
            assert is_plugin_invocation() is True


class TestValidateAndExitOnFailure:
    def test_exits_on_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr"):
                with pytest.raises(SystemExit) as exc:
                    validate_and_exit_on_failure()
                assert exc.value.code == 1

    def test_does_not_exit_on_success(self):
        with patch.dict(os.environ, {MAGIC_COOKIE_KEY: MAGIC_COOKIE_VALUE}):
            validate_and_exit_on_failure()
