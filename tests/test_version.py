"""Tests for waterbot/version.py."""

import subprocess
from unittest.mock import MagicMock, patch

from waterbot.version import get_git_commit


def test_get_git_commit_returns_hash_on_success():
    """A clean git invocation should return the trimmed short hash."""
    completed = MagicMock(returncode=0, stdout="abc1234\n")
    with patch("waterbot.version.subprocess.run", return_value=completed) as mock_run:
        assert get_git_commit() == "abc1234"
    mock_run.assert_called_once()


def test_get_git_commit_falls_back_on_nonzero_exit():
    """A non-git checkout (or any git failure) should not crash the caller."""
    completed = MagicMock(returncode=128, stdout="")
    with patch("waterbot.version.subprocess.run", return_value=completed):
        assert get_git_commit() == "unknown"


def test_get_git_commit_falls_back_on_blank_output():
    """An empty stdout on success should still report 'unknown'."""
    completed = MagicMock(returncode=0, stdout="   \n")
    with patch("waterbot.version.subprocess.run", return_value=completed):
        assert get_git_commit() == "unknown"


def test_get_git_commit_falls_back_when_git_missing():
    """A missing git binary or timeout should not crash the caller."""
    with patch("waterbot.version.subprocess.run", side_effect=FileNotFoundError):
        assert get_git_commit() == "unknown"
    with patch("waterbot.version.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
        assert get_git_commit() == "unknown"
