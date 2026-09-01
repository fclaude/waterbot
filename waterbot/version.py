"""Best-effort build info for startup banners."""

from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_git_commit() -> str:
    """Return the short commit hash WaterBot is running from, or 'unknown'."""
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_REPO_ROOT,
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"
